"""Where is the streamer's webcam in the stream picture? Needed for the split layout
(facecam on top, gameplay below), which is what viral streamer clips use.

Order: FACECAMS in config.txt  >  cached detection (clips/facecams.json, 24 h)  >
Gemini looks at a frame of the stream  >  None (the clipper then uses a full-screen crop).

A box is (x, y, width, height) as fractions of the frame, e.g. (0.73, 0.0, 0.27, 0.3)
= top-right corner, 27 % wide and 30 % high.
"""
import json
import os
import subprocess
import time

from clipwatcher import paths, settings
from clipwatcher.gemini import ask_gemini_json
from clipwatcher.log import log

CACHE_MAX_AGE_S = 24 * 3600
MIN_BOX_SIDE = 0.08   # smaller than this is not a usable facecam


def parse_box(text):
    """"0.73,0,0.27,0.3" -> (0.73, 0.0, 0.27, 0.3); "none"/invalid -> None."""
    try:
        x, y, width, height = (float(value) for value in text.split(","))
    except ValueError:
        return None
    return clamp_box((x, y, width, height))


def clamp_box(box):
    """Keep the box inside the frame; None if it's too small to use."""
    x, y, width, height = (max(0.0, min(1.0, value)) for value in box)
    width, height = min(width, 1.0 - x), min(height, 1.0 - y)
    if width < MIN_BOX_SIDE or height < MIN_BOX_SIDE:
        return None
    return (round(x, 3), round(y, 3), round(width, 3), round(height, 3))


def configured_boxes():
    """{channel: box or None} from FACECAMS='xqc=0.73,0,0.27,0.3;n3on=none'."""
    boxes = {}
    for entry in settings.FACECAMS.split(";"):
        channel, has_equals, box_text = entry.partition("=")
        if has_equals and channel.strip():
            boxes[channel.strip().lower()] = parse_box(box_text.strip())
    return boxes


def load_cache():
    try:
        with open(paths.FACECAM_CACHE_FILE) as cache_file:
            return json.load(cache_file)
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(paths.FACECAM_CACHE_FILE), exist_ok=True)
    with open(paths.FACECAM_CACHE_FILE, "w") as cache_file:
        json.dump(cache, cache_file, indent=1)


def grab_frame_jpeg(video_path, at_s=1.0):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(at_s), "-i", video_path,
               "-frames:v", "1", "-vf", "scale=960:-2", "-f", "image2", "-vcodec", "mjpeg", "-"]
    return subprocess.run(command, capture_output=True).stdout


def detect_with_gemini(frame_jpeg):
    """Box of the webcam overlay in the frame, or None (no key, no webcam, unsure)."""
    if not frame_jpeg:
        return None
    prompt = ("This is one frame of a live stream. Find the streamer's WEBCAM overlay "
              "(a rectangle showing a real person's face, usually in a corner over the gameplay). "
              "Reply as JSON: {\"found\": true/false, \"x\": left, \"y\": top, \"width\": w, \"height\": h} "
              "with every value a fraction of the frame size from 0 to 1. If the whole frame is the "
              "camera (IRL stream) or there is no webcam, reply {\"found\": false}.")
    reply = ask_gemini_json(prompt, temperature=0.1, image_jpeg=frame_jpeg)
    if not reply or not reply.get("found"):
        return None
    try:
        return clamp_box((float(reply["x"]), float(reply["y"]), float(reply["width"]), float(reply["height"])))
    except (KeyError, TypeError, ValueError):
        return None


def facecam_box(channel, sample_video_path):
    """The facecam box for `channel`, or None for a full-screen crop."""
    channel = channel.lower()
    configured = configured_boxes()
    if channel in configured:
        return configured[channel]
    cache = load_cache()
    cached = cache.get(channel)
    if cached and time.time() - cached.get("checked_ts", 0) < CACHE_MAX_AGE_S:
        return tuple(cached["box"]) if cached.get("box") else None
    if not settings.GEMINI_API_KEY:
        return None
    box = detect_with_gemini(grab_frame_jpeg(sample_video_path))
    log(f"facecam for {channel}: {box or 'none found - full-screen crop'}")
    cache[channel] = {"box": list(box) if box else None, "checked_ts": time.time()}
    save_cache(cache)
    return box
