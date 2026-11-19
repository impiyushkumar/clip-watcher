"""Turn one raw 9:16 search-window clip into a post-ready Short, then queue or post it.

    raw window -> find the loudest moment (moment_finder) -> choose a LENGTH-second window
    ending AFTER_PEAK seconds after it -> Whisper on that window -> Gemini WATCHES a frame grid
    + timed transcript and writes hook/title/comment and a BEAT SHEET from the full kit
    (copywriting, beats) -> 1. one video pass: trim + colour + zoom/shake/flash at zoom beats
    + emoji/sticker beats + hook box + captions + credit (video_effects) -> 2. sound beats
    mixed in (sound_design) -> 3. cutaways (text cards, memes) spliced in, last first
    -> 4. ducked music + -14 LUFS -> clips/ready/<name>.mp4
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
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from clipwatcher import paths, settings
from clipwatcher.log import log
from clipwatcher.render import moment_finder, sound_design
from clipwatcher.render import memes
from clipwatcher.render.beats import Beat, fallback_beats
from clipwatcher.render.copywriting import describe, write_copy
from clipwatcher.render.emojis import emoji_path, list_emojis
from clipwatcher.render.memes import meme_path
from clipwatcher.render.subtitles import caption_chunks, write_srt
from clipwatcher.render.text_cards import make_text_card
from clipwatcher.render.transcriber import transcribe_window
from clipwatcher.render.video_effects import edit_video, insert_cutaway

MEME_DELAY_AFTER_PEAK_S = 0.6
PEAK_SYNC_TOLERANCE_S = 0.6        # a beat this close to the peak counts as "on the peak"
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


def complete_beats(copy, timing, transcript_text, meme_menu):
    """Gemini's beat sheet (or the single-peak fallback), always with a zoom and a sound on
    the peak. Without Gemini a meme may follow the peak when its description matches."""
    beats = list(copy.beats) if copy.beats else fallback_beats(timing.onset_s, timing.peak_s, emoji=copy.emoji)
    near_peak = [beat for beat in beats if abs(beat.at_s - timing.onset_s) <= PEAK_SYNC_TOLERANCE_S]
    if not any(beat.kind == "zoom" for beat in near_peak):
        beats.append(Beat(at_s=timing.onset_s, kind="zoom"))
    if not any(beat.kind == "sound" for beat in near_peak):
        beats.append(Beat(at_s=timing.onset_s, kind="sound"))  # "" -> keyword pick / boom
    if not copy.beats and meme_menu and random.random() <= settings.MEME_CHANCE:
        meme_name = sound_design.best_category_by_keywords(transcript_text, meme_menu)
        if meme_name:
            beats.append(Beat(at_s=min(timing.peak_s + MEME_DELAY_AFTER_PEAK_S, max(1.0, timing.length_s - 0.5)),
                              kind="meme", value=meme_name, duration_s=settings.MEME_SECONDS))
    return sorted(beats, key=lambda beat: beat.at_s)


def render_cutaway(beat, work_path):
    """(file, duration_s) for a text card or meme beat, or (None, 0) if it can't be made."""
    if beat.kind == "text_card":
        sound_path = sound_design.resolve_sound(beat.sound) if beat.sound else None
        if make_text_card(beat.value, work_path, beat.duration_s, sound_path):
            return work_path, beat.duration_s
        return None, 0.0
    file_path = meme_path(beat.value)
    if not file_path:
        return None, 0.0
    return file_path, min(beat.duration_s or settings.MEME_SECONDS, sound_design.media_duration_s(file_path))


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
    meme_menu = memes.meme_menu()
    copy = write_copy(transcript, job.stream_info, video_path=job.raw_path, start_s=timing.start_s,
                      length_s=timing.length_s, peak_s=timing.peak_s, sound_menu=sound_design.load_sound_menu(),
                      emoji_names=list_emojis(), meme_menu=meme_menu)
    beats = complete_beats(copy, timing, transcript_text, meme_menu)
    log(f"{job.clip_name}: {describe(copy)}")
    log(f"{job.clip_name}: beats " + ", ".join(f"{beat.at_s:.1f}s {beat.kind} {beat.value}".strip() for beat in beats))

    final_path = os.path.join(paths.READY_CLIPS_DIR, job.clip_name + ".mp4")
    work_prefix = final_path + ".work"
    temporary_files = []

    # 1. picture: trim + effects at every zoom beat + emoji/sticker overlays + text
    overlays = []
    for beat in beats:
        overlay_file = emoji_path(beat.value) if beat.kind == "emoji" else (
            meme_path(beat.value) if beat.kind == "sticker" else None)
        if overlay_file:
            overlays.append((beat.kind, overlay_file, beat.at_s, beat.duration_s or 1.6))
    current_path = f"{work_prefix}.edit.mp4"
    temporary_files.append(current_path)
    if not edit_video(job.raw_path, current_path, timing.start_s, timing.length_s, caption_chunks(transcript),
                      copy.hook, copy.emphasis, job.seam_y, timing.peak_s,
                      zoom_times_s=[beat.at_s for beat in beats if beat.kind == "zoom"], overlays=overlays,
                      credit=source_credit(job.source_url)):
        log(f"video edit failed for {job.clip_name}; keeping raw clip only")
        remove_quietly(*temporary_files)
        return None

    # 2. sound beats (+ sticker audio), on the clip's own timeline
    sound_events = [(sound_design.resolve_sound(beat.value, transcript_text), beat.at_s, settings.SFX_VOLUME)
                    for beat in beats if beat.kind == "sound"]
    sound_events += [(file_path, at_s, 0.8) for kind, file_path, at_s, _duration in overlays
                     if kind == "sticker" and sound_design.has_audio(file_path)]
    with_sounds_path = f"{work_prefix}.sfx.mp4"
    temporary_files.append(with_sounds_path)
    if sound_events and sound_design.mix_audio(current_path, with_sounds_path, sound_events, normalize=False):
        current_path = with_sounds_path

    # 3. cutaways, last first, so earlier beat times stay valid
    for index, beat in enumerate(sorted((beat for beat in beats if beat.is_cutaway),
                                        key=lambda beat: beat.at_s, reverse=True)):
        cutaway_file, duration_s = render_cutaway(beat, f"{work_prefix}.card{index}.mp4")
        if beat.kind == "text_card" and cutaway_file:
            temporary_files.append(cutaway_file)
        if not cutaway_file or duration_s < 0.3:
            continue
        spliced_path = f"{work_prefix}.cut{index}.mp4"
        temporary_files.append(spliced_path)
        if insert_cutaway(current_path, cutaway_file, beat.at_s, duration_s, spliced_path):
            current_path = spliced_path
        else:
            log(f"{beat.kind} cutaway failed ({beat.value}) - skipped")

    # 4. music under everything + final loudness
    if sound_design.mix_audio(current_path, final_path, [], sound_design.pick_music()):
        sound_design.correct_loudness(final_path)
    else:
        shutil.copyfile(current_path, final_path)  # still a good clip, just not loudness-levelled
    remove_quietly(*temporary_files, job.raw_path)  # the finished clip replaces the raw cut

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
