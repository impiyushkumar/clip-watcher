"""The meme library in memes/: short reaction videos the beat sheet can cut to (full-screen,
letterboxed, with their own audio) or show as a picture-in-picture sticker.

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


def meme_path(name):
    path = os.path.join(paths.MEMES_DIR, name or "")
    return path if name and os.path.isfile(path) else None


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
    """Import one meme into memes/. Returns its file name."""
    os.makedirs(paths.MEMES_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipwatcher-meme-") as work_dir:
        source_path = fetch_source(source, work_dir)
        trim = []
        if start_s is not None:
            trim += ["-ss", str(start_s)]
        length_s = min(MAX_MEME_S, (end_s - (start_s or 0)) if end_s is not None else MAX_MEME_S)
        normalized = os.path.join(work_dir, "meme.mp4")
        result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *trim, "-i", source_path,
                                 "-t", f"{length_s:.2f}", "-vf", "scale='min(1080,iw)':-2,fps=30,format=yuv420p",
                                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", normalized])
        if result.returncode != 0:
            raise RuntimeError(f"could not convert {source}")
        description = None if use_when else (describe_meme(normalized) if settings.GEMINI_API_KEY else None)
        file_name = slugify(name or (description or {}).get("name") or os.path.splitext(os.path.basename(source))[0]) + ".mp4"
        shutil.move(normalized, os.path.join(paths.MEMES_DIR, file_name))
    catalog = load_catalog()
    catalog[file_name] = {"use_when": use_when or (description or {}).get("use_when")
                          or file_name[:-4].replace("-", " "), "source": source}
    save_catalog(catalog)
    log(f"meme added: {file_name}: {catalog[file_name]['use_when']}")
    return file_name
