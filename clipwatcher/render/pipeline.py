"""Turn one raw 9:16 search-window clip into a post-ready Short, then queue or post it.

    raw window -> find the loudest moment (moment_finder) -> choose a LENGTH-second window
    ending AFTER_PEAK seconds after it -> Whisper on that window -> Gemini WATCHES frames
    around the peak and picks hook/title/sounds/emoji/meme/comment from the full kit
    (copywriting) -> one video pass: trim + colour + zoom/shake/flash + emoji pop-up on the
    peak + hook box + captions + source credit (video_effects) -> optional meme cutaway ->
    sound design: chosen sound on the peak, reaction sound after it, whoosh into the meme,
    ducked music, -14 LUFS (sound_design) -> clips/ready/<name>.mp4
    -> caption .txt -> optional Drive sync -> clips/queue/<name>.json or post right now

Queue item format (clips/queue/<clip>.json). These keys are stored on disk, so never
rename them; add new keys instead:
    clip        clip name, e.g. "twitch_xqc_20250101_120000"
    final       path of the finished .mp4, relative to the repo root
    caption     default caption text
    hook        on-screen hook text
    title       post title with emojis (newer clips only; older ones fall back to the hook)
    comment     first comment to post under the video (newer clips only)
    score       chat messages in the spike bucket (manual clips: 1000000)
    created     "YYYY-MM-DD HH:MM";  created_ts: unix seconds
    source      credit, e.g. "https://twitch.tv/xqc"
    length_s    clip length in seconds
    meta        stream info {"creator": ..., "game": ...}
    posted_to   {platform: url or "failed"}, added by the scheduler
"""
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from clipwatcher import paths, settings
from clipwatcher.log import log
from clipwatcher.render import moment_finder, sound_design
from clipwatcher.render.copywriting import describe, write_copy
from clipwatcher.render.emojis import emoji_path, list_emojis
from clipwatcher.render.memes import list_memes, pick_meme
from clipwatcher.render.subtitles import caption_chunks, write_srt
from clipwatcher.render.transcriber import transcribe_window
from clipwatcher.render.video_effects import edit_video, insert_meme

MEME_DELAY_AFTER_PEAK_S = 0.6
REACTION_DELAY_AFTER_PEAK_S = 0.5
FALLBACK_PEAK_BEFORE_SPIKE_S = 3   # no audio: assume the moment was 3 s before chat reacted


@dataclass
class ClipJob:
    """Everything needed to render (and maybe post) one clip."""
    clip_name: str
    raw_path: str
    source_url: str
    stream_info: dict = field(default_factory=dict)   # {"creator": ..., "game": ...}
    hashtags: str = settings.HASHTAGS
    length_s: int = settings.CLIP_LENGTH_S             # final clip length
    spike_at_s: float = None                           # chat spike, seconds into the raw clip
    seam_y: int = None                                 # split layout: y of the facecam/gameplay seam
    score: int = 0
    whisper_model: str = settings.WHISPER_MODEL
    upload_targets: str = "none"                       # used only when queue_for_schedule is False
    privacy: str = settings.PRIVACY
    queue_for_schedule: bool = True


@dataclass
class ClipTiming:
    start_s: float    # window start in the raw clip
    length_s: float
    peak_s: float     # in the final clip
    onset_s: float    # in the final clip: where the impact sound and zoom land


def repo_relative(path):
    return os.path.relpath(os.path.abspath(path), paths.ROOT_DIR)


def find_timing(raw_path, length_s, spike_at_s):
    """Where the real moment is, and which window of the raw clip to keep."""
    raw_duration_s = sound_design.media_duration_s(raw_path)
    spike_s = spike_at_s if spike_at_s is not None else raw_duration_s * 0.7
    envelope = moment_finder.loudness_envelope(raw_path)
    peak_s = moment_finder.find_peak_s(envelope, max(0.0, spike_s - settings.SEARCH_BEFORE_S),
                                       spike_s + settings.SEARCH_AFTER_S)
    if peak_s is None:
        peak_s = max(0.0, spike_s - FALLBACK_PEAK_BEFORE_SPIKE_S)
    onset_s = moment_finder.find_onset_s(envelope, peak_s)
    start_s, end_s = moment_finder.choose_window(raw_duration_s, peak_s, length_s, settings.AFTER_PEAK_S)
    return ClipTiming(start_s=start_s, length_s=round(end_s - start_s, 2),
                      peak_s=round(peak_s - start_s, 2), onset_s=round(max(0.0, onset_s - start_s), 2))


def source_credit(source_url):
    """"https://www.twitch.tv/xqc" -> "SOURCE: TWITCH.TV/XQC"."""
    cleaned = re.sub(r"^https?://(www\.)?", "", source_url or "").rstrip("/")
    return f"SOURCE: {cleaned.upper()}" if cleaned else ""


def remove_quietly(*file_paths):
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


def process_clip(job):
    """Render `job`. Returns the queue item dict, or None if rendering failed."""
    from clipwatcher.publish.post_text import build_caption, creator_display_name

    os.makedirs(paths.READY_CLIPS_DIR, exist_ok=True)
    timing = find_timing(job.raw_path, job.length_s, job.spike_at_s)
    log(f"{job.clip_name}: peak at {timing.start_s + timing.peak_s:.1f}s of the raw cut, "
        f"keeping {timing.start_s:.1f}-{timing.start_s + timing.length_s:.1f}s")

    log(f"transcribing {job.clip_name} ...")
    vocabulary = ", ".join(filter(None, [creator_display_name(job.stream_info), settings.WHISPER_VOCABULARY]))
    transcript = transcribe_window(job.raw_path, job.whisper_model, timing.start_s, timing.length_s, vocabulary)
    transcript_text = (transcript.get("text") or "").strip()
    write_srt(transcript, os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".srt"))
    copy = write_copy(transcript_text, job.stream_info, video_path=job.raw_path,
                      peak_s=timing.start_s + timing.peak_s, length_s=timing.length_s,
                      sound_menu=sound_design.load_sound_menu(), emoji_names=list_emojis(),
                      meme_names=list_memes())
    log(f"{job.clip_name}: {describe(copy)}")

    final_path = os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".mp4")
    edited_path = final_path + ".edit.mp4"
    meme_path = final_path + ".meme.mp4"
    if not edit_video(job.raw_path, edited_path, timing.start_s, timing.length_s, caption_chunks(transcript),
                      copy.hook, copy.emphasis, job.seam_y, timing.peak_s, timing.onset_s,
                      emoji_file=emoji_path(copy.emoji), credit=source_credit(job.source_url)):
        log(f"video edit failed for {job.clip_name}; keeping raw clip only")
        remove_quietly(edited_path)
        return None

    sound_events = [(sound_design.resolve_sound(copy.peak_sound, transcript_text), timing.onset_s,
                     settings.SFX_VOLUME)]
    meme_name = pick_meme(copy.meme, transcript_text)
    if meme_name:
        meme_at_s = min(timing.peak_s + MEME_DELAY_AFTER_PEAK_S, max(0.5, timing.length_s - 0.5))
        if insert_meme(edited_path, meme_name, meme_at_s, meme_path):
            os.replace(meme_path, edited_path)
            sound_events.append((sound_design.whoosh_sound(), max(0.0, meme_at_s - sound_design.WHOOSH_LEAD_S), 0.7))
            log(f"meme cutaway: {meme_name}")
        else:
            log(f"meme insert failed ({meme_name}) - posting without it")
            remove_quietly(meme_path)
            meme_name = None
    if copy.reaction_sound and not meme_name:  # a meme already has its own reaction audio
        sound_events.append((sound_design.resolve_sound(copy.reaction_sound),
                             min(timing.peak_s + REACTION_DELAY_AFTER_PEAK_S, max(0.0, timing.length_s - 1.0)),
                             settings.SFX_VOLUME * 0.85))

    if not sound_design.mix_audio(edited_path, final_path, sound_events, sound_design.pick_music()):
        os.replace(edited_path, final_path)  # still a good clip, just without the sound design
    remove_quietly(edited_path, job.raw_path)  # the finished clip replaces the raw cut

    caption = build_caption(copy.hook, job.source_url, job.hashtags, job.stream_info, title=copy.title)
    with open(os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".txt"), "w", encoding="utf-8") as caption_file:
        caption_file.write(caption)
    log(f"READY: {final_path}  (title: {copy.title!r}, hook: {copy.hook!r})")

    if settings.RCLONE_DEST:
        for extension in (".mp4", ".txt"):
            subprocess.run(["rclone", "copy", os.path.join(paths.READY_CLIPS_DIR, job.clip_name + extension),
                            settings.RCLONE_DEST])
        log(f"synced to {settings.RCLONE_DEST}")

    queue_item = {"clip": job.clip_name, "final": repo_relative(final_path), "caption": caption,
                  "hook": copy.hook, "title": copy.title, "comment": copy.comment, "score": job.score,
                  "created": time.strftime("%Y-%m-%d %H:%M"), "created_ts": time.time(),
                  "source": job.source_url, "length_s": round(timing.length_s), "meta": job.stream_info}
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
