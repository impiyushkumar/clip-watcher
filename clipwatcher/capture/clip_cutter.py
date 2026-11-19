"""Cut one raw 9:16 clip around a spike from the rolling buffer (ffmpeg).

The cut is a wide "search window" (SEARCH_BEFORE_S before the chat spike, SEARCH_AFTER_S
after); render/moment_finder.py later trims it to the real peak."""
import os
import subprocess
import time

from clipwatcher import paths, settings
from clipwatcher.capture.recording_buffer import list_segments
from clipwatcher.heavy_job import heavy_job_slot
from clipwatcher.log import log


def even(value):
    return int(value) // 2 * 2


def split_heights(height):
    """(facecam_height, gameplay_height) for the split layout, both even."""
    facecam_height = even(height * settings.FACECAM_SHARE)
    return facecam_height, height - facecam_height


def fill(width, height):
    """Scale to cover width x height, then center-crop to exactly that."""
    return (f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height}")


def vertical_filter(facecam_box=None):
    """ffmpeg filter graph that turns the 16:9 stream into OUTPUT_RESOLUTION 9:16.

    split (needs facecam_box) = streamer's webcam on top, gameplay center below (viral layout)
    crop  = fill the screen with the center of the picture
    fit   = whole frame sharp in the middle + blurred background (small gameplay, avoid)"""
    width, height = settings.output_size()
    if settings.LAYOUT == "split" and facecam_box:
        box_x, box_y, box_width, box_height = facecam_box
        facecam_height, gameplay_height = split_heights(height)
        return (f"[0:v]split[cam_source][game_source];"
                f"[cam_source]crop=iw*{box_width}:ih*{box_height}:iw*{box_x}:ih*{box_y},"
                f"{fill(width, facecam_height)}[cam];"
                f"[game_source]{fill(width, gameplay_height)}[game];"
                f"[cam][game]vstack,setsar=1[video]")
    if settings.LAYOUT == "fit":
        return (f"[0:v]split[a][b];[a]{fill(width, height)},boxblur=20:2[bg];"
                f"[b]scale={width}:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[video]")
    return f"[0:v]{fill(width, height)},setsar=1[video]"


def cut_raw_clip(recording_dir, recording_start_ts, spike_ts, clip_name, before_s, after_s, facecam_box=None):
    """Wait until the buffer covers [spike - before_s, spike + after_s], then cut it to
    clips/raw/<clip_name>.mp4. Returns the path, or None if it failed."""
    segments = list_segments(recording_dir)
    stream_base_s = segments[0][1] if segments else 0.0
    window_start_s = stream_base_s + max(0.0, spike_ts - recording_start_ts - before_s)
    window_end_s = window_start_s + before_s + after_s
    deadline_ts = time.time() + after_s + 90
    while time.time() < deadline_ts:  # the "after" part is still being recorded
        segments = list_segments(recording_dir)
        if segments and segments[-1][2] >= window_end_s:
            break
        if os.path.exists(paths.stream_ended_marker(recording_dir)) and segments:
            break
        time.sleep(2)
    pieces = [segment for segment in segments
              if segment[2] > window_start_s and segment[1] < window_end_s
              and os.path.exists(segment[0])]
    if not pieces:
        log(f"no recording for {clip_name} (window already gone)")
        return None

    os.makedirs(paths.RAW_CLIPS_DIR, exist_ok=True)
    raw_path = os.path.join(paths.RAW_CLIPS_DIR, clip_name + ".mp4")
    offset_s = max(0.0, window_start_s - pieces[0][1])
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{offset_s:.2f}", "-i", "concat:" + "|".join(piece[0] for piece in pieces),
        "-t", str(before_s + after_s),
        "-filter_complex", vertical_filter(facecam_box), "-map", "[video]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", settings.FFMPEG_THREADS,
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", raw_path,
    ]
    with heavy_job_slot():
        result = subprocess.run(command)
    if result.returncode == 0 and os.path.exists(raw_path):
        log(f"raw clip saved: {raw_path}")
        return raw_path
    log(f"ffmpeg failed for {clip_name}")
    return None
