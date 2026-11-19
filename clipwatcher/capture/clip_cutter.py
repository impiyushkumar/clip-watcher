"""Cut one raw 9:16 clip around a spike from the rolling buffer (ffmpeg)."""
import os
import subprocess
import time

from clipwatcher import paths, settings
from clipwatcher.capture.recording_buffer import list_segments
from clipwatcher.heavy_job import heavy_job_slot
from clipwatcher.log import log


def vertical_filter():
    """ffmpeg filter that turns 16:9 into OUTPUT_RESOLUTION 9:16.
    crop = fill the screen (cuts the sides); fit = whole frame sharp + blurred background."""
    width, height = settings.output_size()
    if settings.LAYOUT == "fit":
        return (f"split[a][b];[a]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},boxblur=20:2[bg];[b]scale={width}:-2:flags=lanczos[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return f"crop='trunc(ih*9/16/2)*2':ih,scale={width}:{height}:flags=lanczos,setsar=1"


def cut_raw_clip(recording_dir, recording_start_ts, spike_ts, clip_name, before_s, after_s):
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
        "-filter_complex" if settings.LAYOUT == "fit" else "-vf", vertical_filter(),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", settings.FFMPEG_THREADS,
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", raw_path,
    ]
    with heavy_job_slot():
        result = subprocess.run(command)
    if result.returncode == 0 and os.path.exists(raw_path):
        log(f"raw clip saved: {raw_path}")
        return raw_path
    log(f"ffmpeg failed for {clip_name}")
    return None
