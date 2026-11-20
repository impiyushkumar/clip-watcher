#!/usr/bin/env python3
"""Watch ONE channel: count chat, clip every spike, render + queue/post each clip.

Started by scripts/watch-channel.sh (which records the stream into --rec):
    python3 -m clipwatcher.capture.channel_watcher <channel> --platform twitch --rec rec/<dir>
Defaults for every flag come from config.txt (see clipwatcher/settings.py).
Press Enter in the terminal to clip the current moment yourself.
It exits once the stream has ended and every pending clip is finished.
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

from clipwatcher import settings
from clipwatcher.capture import chat
from clipwatcher.capture.clip_cutter import cut_raw_clip
from clipwatcher.capture.recording_buffer import delete_old_segments_forever, wait_for_first_segment
from clipwatcher.capture.spike_detector import SpikeDetector
from clipwatcher.heavy_job import heavy_job_slot
from clipwatcher.log import log
from clipwatcher import paths

MANUAL_CLIP_SCORE = 10 ** 6  # your own Enter-key picks are posted first


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("channel")
    parser.add_argument("--platform", default="twitch", choices=sorted(chat.CHAT_READERS))
    parser.add_argument("--rec", required=True, help="recording folder written by watch-channel.sh")
    parser.add_argument("--min", type=int, default=settings.SPIKE_MIN_MESSAGES,
                        help="min messages in a 10s bucket")
    parser.add_argument("--factor", type=float, default=settings.SPIKE_FACTOR)
    parser.add_argument("--cooldown", type=int, default=settings.CLIP_COOLDOWN_S,
                        help="min seconds between clips")
    parser.add_argument("--length", type=int, default=settings.CLIP_LENGTH_S,
                        help="clip length in seconds (2/3 before the spike)")
    parser.add_argument("--model", default=settings.WHISPER_MODEL, help="whisper model")
    parser.add_argument("--upload", default=settings.UPLOAD_TARGETS,
                        help="none, or any of youtube,instagram,facebook (comma separated)")
    parser.add_argument("--privacy", default=settings.PRIVACY, choices=["public", "unlisted", "private"])
    parser.add_argument("--tags", default=settings.HASHTAGS)
    parser.add_argument("--hook", default="wait for it...", help="hook text when nobody talks")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--queue", action="store_true",
                        help="don't post now; add to clips/queue/ for the scheduler")
    return parser.parse_args()


def fetch_stream_info(stream_url, channel):
    """{"creator": ..., "game": ...} from streamlink, used for captions and hashtags."""
    stream_info = {"creator": channel.lstrip("@"), "game": ""}
    if not stream_url:
        return stream_info
    try:
        output = subprocess.run(["streamlink", "--json", stream_url],
                                capture_output=True, text=True, timeout=40).stdout
        metadata = json.loads(output or "{}").get("metadata") or {}
        stream_info["creator"] = metadata.get("author") or stream_info["creator"]
        stream_info["game"] = metadata.get("category") or ""
    except Exception:
        pass
    return stream_info


class PendingCounter:
    """Clips cut or being rendered. The watcher only exits when this is 0."""

    def __init__(self):
        self.count = 0
        self.lock = threading.Lock()

    def change(self, delta):
        with self.lock:
            self.count += delta


def main():
    from clipwatcher.render.pipeline import ClipJob, process_clip

    args = parse_args()
    channel = args.channel if args.platform == "youtube" else args.channel.lower().lstrip("#")
    safe_channel = "".join(char for char in channel if char.isalnum() or char in "_-")[-40:] or "clip"
    before_s = max(3, round(args.length * 2 / 3))
    after_s = max(2, args.length - before_s)
    source_url = args.source_url or f"{args.platform}: {channel}"
    stream_info = fetch_stream_info(args.source_url, channel)
    log(f"stream: {stream_info.get('creator')} | {stream_info.get('game') or '?'}")
    log(f"clips: {before_s}s before + {after_s}s after each spike; upload: {args.upload}")

    pending = PendingCounter()
    render_queue = queue.Queue()  # (raw_path, clip_name, score), rendered one at a time

    def render_worker():
        while True:
            raw_path, clip_name, score = render_queue.get()
            try:
                job = ClipJob(clip_name=clip_name, raw_path=raw_path, source_url=source_url,
                              stream_info=stream_info, hashtags=args.tags, hook_fallback=args.hook,
                              length_s=before_s + after_s, spike_at_s=before_s, score=score,
                              whisper_model=args.model, upload_targets=args.upload,
                              privacy=args.privacy, queue_for_schedule=args.queue)
                with heavy_job_slot():
                    process_clip(job)
            except Exception as error:
                log(f"post-processing failed for {clip_name}: {error}")
            finally:
                pending.change(-1)

    threading.Thread(target=render_worker, daemon=True).start()

    recording_start_ts = wait_for_first_segment(args.rec)
    threading.Thread(target=delete_old_segments_forever,
                     args=(args.rec, settings.BUFFER_MINUTES * 60), daemon=True).start()

    def cut_and_enqueue(spike_ts, clip_name, score):
        raw_path = cut_raw_clip(args.rec, recording_start_ts, spike_ts, clip_name, before_s, after_s)
        if raw_path:
            render_queue.put((raw_path, clip_name, score))
        else:
            pending.change(-1)

    def make_clip(spike_ts, score=0):
        clip_name = f"{args.platform}_{safe_channel}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(spike_ts))}"
        log(f"clipping -> {clip_name}")
        pending.change(+1)
        threading.Thread(target=cut_and_enqueue, args=(spike_ts, clip_name, score), daemon=True).start()

    detector = SpikeDetector(min_messages=args.min, factor=args.factor,
                             min_gap_s=max(before_s + after_s, args.cooldown),
                             start_ts=time.time(), debug=settings.DEBUG)
    detector_lock = threading.Lock()

    def handle_spikes(spikes):
        for bucket_end_ts, count, median in spikes:
            log(f"SPIKE {count} msgs (median {median:.1f})")
            make_clip(bucket_end_ts, score=count)

    def tick_forever():
        """Close buckets while chat is silent, and exit when the stream is over."""
        while True:
            time.sleep(1)
            with detector_lock:
                handle_spikes(detector.close_buckets(time.time()))
            if os.path.exists(paths.stream_ended_marker(args.rec)) and pending.count <= 0:
                log("stream over and all clips finished - stopping")
                os._exit(0)

    def read_enter_key_forever():
        for _line in sys.stdin:
            with detector_lock:
                detector.last_clip_ts = time.time()
            log("MANUAL clip")
            make_clip(time.time(), score=MANUAL_CLIP_SCORE)

    threading.Thread(target=tick_forever, daemon=True).start()
    if sys.stdin.isatty():
        threading.Thread(target=read_enter_key_forever, daemon=True).start()
        log("tip: press Enter any time to clip the moment yourself")

    for message_ts in chat.message_times(args.platform, channel):
        with detector_lock:
            handle_spikes(detector.add_message(message_ts))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
