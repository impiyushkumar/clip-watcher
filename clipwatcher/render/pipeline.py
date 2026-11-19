"""Turn one raw 9:16 clip into a post-ready Short, then queue or post it.

    raw clip -> Whisper transcript -> .srt + hook -> captions/zoom burned in
             -> optional meme cutaway -> caption .txt -> optional Drive sync
             -> clips/queue/<name>.json (scheduled mode) or post right now

Queue item format (clips/queue/<clip>.json). These keys are stored on disk, so never
rename them; add new keys instead:
    clip        clip name, e.g. "twitch_xqc_20250101_120000"
    final       path of the finished .mp4, relative to the repo root
    caption     default caption text
    hook        hook text
    score       chat messages in the spike bucket (manual clips: 1000000)
    created     "YYYY-MM-DD HH:MM";  created_ts: unix seconds
    source      credit, e.g. "https://twitch.tv/xqc"
    length_s    clip length in seconds
    meta        stream info {"creator": ..., "game": ...}
    posted_to   {platform: url or "failed"}, added by the scheduler
"""
import json
import os
import subprocess
import time
from dataclasses import dataclass, field

from clipwatcher import paths, settings
from clipwatcher.log import log
from clipwatcher.render.hook import make_hook
from clipwatcher.render.memes import pick_meme
from clipwatcher.render.subtitles import caption_chunks, write_srt
from clipwatcher.render.transcriber import transcribe
from clipwatcher.render.video_effects import burn_captions, insert_meme

MEME_DELAY_AFTER_SPIKE_S = 0.4


@dataclass
class ClipJob:
    """Everything needed to render (and maybe post) one clip."""
    clip_name: str
    raw_path: str
    source_url: str
    stream_info: dict = field(default_factory=dict)   # {"creator": ..., "game": ...}
    hashtags: str = settings.HASHTAGS
    hook_fallback: str = "wait for it..."
    length_s: int = 30
    spike_at_s: float = None                          # seconds into the clip; None = no zoom/meme
    score: int = 0
    whisper_model: str = settings.WHISPER_MODEL
    upload_targets: str = "none"                      # used only when queue_for_schedule is False
    privacy: str = settings.PRIVACY
    queue_for_schedule: bool = True


def repo_relative(path):
    return os.path.relpath(os.path.abspath(path), paths.ROOT_DIR)


def process_clip(job):
    """Render `job`. Returns the queue item dict, or None if rendering failed."""
    from clipwatcher.publish.post_text import build_caption

    os.makedirs(paths.READY_CLIPS_DIR, exist_ok=True)
    log(f"transcribing {job.clip_name} ...")
    transcript = transcribe(job.raw_path, job.whisper_model)
    transcript_text = transcript.get("text") or ""
    caption_line_count = write_srt(transcript, os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".srt"))
    hook = make_hook(transcript, job.hook_fallback, job.stream_info)

    final_path = os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".mp4")
    if not burn_captions(job.raw_path, hook, final_path, caption_chunks(transcript), job.spike_at_s):
        log(f"caption burn failed for {job.clip_name}; keeping raw clip only")
        return None

    meme_name = pick_meme(transcript_text, job.stream_info)
    if meme_name and job.spike_at_s is not None:
        temporary_path = final_path + ".meme.mp4"
        if insert_meme(final_path, meme_name, job.spike_at_s + MEME_DELAY_AFTER_SPIKE_S, temporary_path):
            os.replace(temporary_path, final_path)
            log(f"meme cutaway: {meme_name}")
        else:
            log(f"meme insert failed ({meme_name}) - posting without it")
            if os.path.exists(temporary_path):
                os.remove(temporary_path)

    try:
        os.remove(job.raw_path)  # the finished clip replaces the raw cut (~15-20 MB saved)
    except OSError:
        pass

    caption = build_caption(hook, job.source_url, job.hashtags, job.stream_info)
    with open(os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".txt"), "w", encoding="utf-8") as caption_file:
        caption_file.write(caption)
    log(f"READY: {final_path}  (hook: {hook!r}, {caption_line_count} caption lines)")

    if settings.RCLONE_DEST:
        for extension in (".mp4", ".txt"):
            subprocess.run(["rclone", "copy", os.path.join(paths.READY_CLIPS_DIR, job.clip_name + extension),
                            settings.RCLONE_DEST])
        log(f"synced to {settings.RCLONE_DEST}")

    queue_item = {"clip": job.clip_name, "final": repo_relative(final_path), "caption": caption,
                  "hook": hook, "score": job.score, "created": time.strftime("%Y-%m-%d %H:%M"),
                  "created_ts": time.time(), "source": job.source_url, "length_s": job.length_s,
                  "meta": job.stream_info}
    if job.queue_for_schedule:
        os.makedirs(paths.QUEUE_DIR, exist_ok=True)
        with open(os.path.join(paths.QUEUE_DIR, job.clip_name + ".json"), "w", encoding="utf-8") as queue_file:
            json.dump(queue_item, queue_file, indent=1)
        log(f"queued for posting: {job.clip_name} (score {job.score})")
    else:
        from clipwatcher.publish.poster import post_clip, usable_targets
        targets = ",".join(usable_targets(job.upload_targets, explain=True))
        post_clip(queue_item, targets, job.hashtags, job.privacy)
    return queue_item
