"""The meme library in memes/: short reaction videos the beat sheet can cut to (full-screen,
letterboxed, with their own audio) or show as a picture-in-picture sticker. Memes on a flat
background (green screen, or black like GTA "wasted") are detected automatically, keyed out
and laid over the gameplay instead.

memes/catalog.json says what each meme is and WHEN to use it; Gemini reads it when it plans
the beats. Add memes with the importer, which trims, normalizes and describes them:

    python3 -m clipwatcher add-meme <file or URL> [--name shocked-guy] [--start 3.5 --end 6]
                                                  [--use-when "someone gets scared"]

URLs need yt-dlp (pip install yt-dlp). memes/ is git-ignored (except README.md): only add
clips you have the right to use in your videos.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

from clipwatcher import paths, settings
from clipwatcher.log import log

MEME_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".gif")
MAX_MEME_S = 4.0
KEY_MOMENT_MAX_S = 3.0      # auto-trim keeps at most this much around the key sound
CATALOG_NAME = "catalog.json"


def catalog_path():
    return os.path.join(paths.MEMES_DIR, CATALOG_NAME)


def load_catalog():
    try:
        with open(catalog_path(), encoding="utf-8") as catalog_file:
            return json.load(catalog_file)
    except (OSError, ValueError):
        return {}


def save_catalog(catalog):
    os.makedirs(paths.MEMES_DIR, exist_ok=True)
    with open(catalog_path(), "w", encoding="utf-8") as catalog_file:
        json.dump(dict(sorted(catalog.items())), catalog_file, indent=1, ensure_ascii=False)


def list_memes():
    try:
        return sorted(name for name in os.listdir(paths.MEMES_DIR) if name.lower().endswith(MEME_EXTENSIONS))
    except OSError:
        return []


def meme_menu():
    """{file name: "use when"} for every meme; the file name stands in when not catalogued."""
    catalog = load_catalog()
    return {name: (catalog.get(name) or {}).get("use_when")
            or os.path.splitext(name)[0].replace("-", " ").replace("_", " ")
            for name in list_memes()}


KEYABLE_BORDER_SHARE = 0.6   # this much of the frame border one flat colour = a keyable background
BLACK_OVERLAY_SHARE = 0.8    # this much of the whole frame black = a black-background overlay


def frame_pixels(file_path, at_s=0.5, size=32):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(at_s), "-i", file_path,
                          "-frames:v", "1", "-vf", f"scale={size}:{size}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    return [tuple(raw[index:index + 3]) for index in range(0, len(raw) - 2, 3)], size


def background_key_color(file_path):
    """The flat background colour to key out ("0x8cff2e" for a lime green screen, "0x000000"
    for a black overlay like GTA "wasted"), or None for a normal video. Looks at the frame
    border: green-screen and black-overlay memes have one flat colour there."""
    pixels, size = frame_pixels(file_path)
    if len(pixels) < size * size:
        return None
    border = [pixels[row * size + column] for row in range(size) for column in range(size)
              if row in (0, 1, size - 2, size - 1) or column in (0, 1, size - 2, size - 1)]
    green = [pixel for pixel in border if pixel[1] > 110 and pixel[1] > pixel[0] + 40 and pixel[1] > pixel[2] + 40]
    if len(green) / len(border) >= KEYABLE_BORDER_SHARE:
        red, green_value, blue = (sum(channel) // len(green) for channel in zip(*green))
        return f"0x{red:02x}{green_value:02x}{blue:02x}"
    # black: only a real overlay (GTA "wasted" text on black) is almost entirely black;
    # a normal video with black bars (pillarbox/letterbox) is not
    dark_share = sum(1 for pixel in pixels if max(pixel) < 30) / len(pixels)
    return "0x000000" if dark_share >= BLACK_OVERLAY_SHARE else None


def meme_key_color(name):
    """Background colour to key out for a meme (cached in memes/catalog.json), or None."""
    catalog = load_catalog()
    entry = catalog.setdefault(name, {})
    if "key_color" not in entry:
        file_path = meme_path(name)
        entry["key_color"] = background_key_color(file_path) if file_path else None
        save_catalog(catalog)
    return entry["key_color"]


def meme_path(name):
    path = os.path.join(paths.MEMES_DIR, name or "")
    return path if name and os.path.isfile(path) else None


def black_bar_crop(video_path):
    """ffmpeg crop filter that removes built-in black bars (pillarbox/letterbox), or "".
    Without this a meme with bars shows up tiny when it's cut in."""
    output = subprocess.run(["ffmpeg", "-hide_banner", "-i", video_path, "-vf", "cropdetect=24:2:0",
                             "-frames:v", "30", "-f", "null", "-"], capture_output=True, text=True, errors="replace").stderr
    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", output)
    if not crops:
        return ""
    width, height, x, y = (int(value) for value in crops[-1])
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", video_path], capture_output=True, text=True, errors="replace").stdout
    try:
        full_width, full_height = (int(value) for value in probe.strip().split(",")[:2])
    except ValueError:
        return ""
    if width * height >= full_width * full_height * 0.92 or width < 64 or height < 64:
        return ""  # no real bars, or cropdetect got confused by a dark scene
    return f"crop={width}:{height}:{x}:{y},"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "meme"


def fetch_source(source, work_dir):
    """Local path as is; a URL is downloaded with yt-dlp."""
    if os.path.exists(source):
        return source
    if not shutil.which("yt-dlp"):
        raise RuntimeError("downloading a URL needs yt-dlp: pip install yt-dlp (or pass a local file)")
    output_template = os.path.join(work_dir, "source.%(ext)s")
    cookies = ["--cookies", settings.YTDLP_COOKIES] if settings.YTDLP_COOKIES else []
    subprocess.run(["yt-dlp", "-q", "--no-warnings", *cookies, "--match-filter", "duration < 300",
                    "--max-downloads", "1", "-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
                    "--merge-output-format", "mp4", "-o", output_template, source])
    if not any(name.startswith("source.") for name in os.listdir(work_dir)):
        raise RuntimeError("download failed (YouTube blocks servers: set YTDLP_COOKIES or run on your PC)")
    return next(os.path.join(work_dir, name) for name in os.listdir(work_dir) if name.startswith("source."))


def describe_meme(meme_file):
    """Gemini watches 3 frames and writes what the meme is and when to use it, or None."""
    from clipwatcher.gemini import ask_gemini_json
    from clipwatcher.render.copywriting import contact_sheet_jpeg
    from clipwatcher.render.sound_design import media_duration_s
    duration_s = media_duration_s(meme_file)
    frames = contact_sheet_jpeg(meme_file, [duration_s * 0.15, duration_s * 0.5, duration_s * 0.85])
    reply = ask_gemini_json(
        "These are 3 frames of a short reaction meme clip. Reply as JSON: {\"name\": \"2-5 word "
        "kebab-case name, e.g. shocked-guy-staring\", \"use_when\": \"one sentence: what it shows and "
        "the exact kind of moment in a gaming stream clip it fits\"}", temperature=0.3, image_jpeg=frames)
    return reply if reply and reply.get("use_when") else None


def add_meme(source, name=None, start_s=None, end_s=None, use_when=None):
    """Import one meme into memes/. Without start/end it auto-trims to the key moment (the
    loudest sound event, max KEY_MOMENT_MAX_S). Returns its file name."""
    os.makedirs(paths.MEMES_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipwatcher-meme-") as work_dir:
        source_path = fetch_source(source, work_dir)
        if start_s is None and end_s is None:  # keep only the key moment ("noice", the laugh, the scream)
            from clipwatcher.render.moment_finder import find_key_moment, loudness_envelope
            key_moment = find_key_moment(loudness_envelope(source_path), max_length_s=KEY_MOMENT_MAX_S)
            if key_moment:
                start_s, end_s = key_moment
        trim = []
        if start_s is not None:
            trim += ["-ss", str(start_s)]
        length_s = min(MAX_MEME_S, (end_s - (start_s or 0)) if end_s is not None else MAX_MEME_S)
        normalized = os.path.join(work_dir, "meme.mp4")
        crop = black_bar_crop(source_path)
        result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *trim, "-i", source_path,
                                 "-t", f"{length_s:.2f}", "-vf", f"{crop}scale='min(1080,iw)':-2,fps=30,format=yuv420p",
                                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", normalized])
        if result.returncode != 0:
            raise RuntimeError(f"could not convert {source}")
        description = None if use_when else (describe_meme(normalized) if settings.GEMINI_API_KEY else None)
        file_name = slugify(name or (description or {}).get("name") or os.path.splitext(os.path.basename(source))[0]) + ".mp4"
        shutil.move(normalized, os.path.join(paths.MEMES_DIR, file_name))
    catalog = load_catalog()
    catalog[file_name] = {"use_when": use_when or (description or {}).get("use_when")
                          or file_name[:-4].replace("-", " "), "source": source,
                          "key_color": background_key_color(os.path.join(paths.MEMES_DIR, file_name))}
    save_catalog(catalog)
    log(f"meme added: {file_name}: {catalog[file_name]['use_when']}")
    return file_name
