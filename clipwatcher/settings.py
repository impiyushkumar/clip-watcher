"""All user settings in one place.

Each value is looked up in this order, and the first non-empty one wins:
    1. environment variable KEY        (e.g. RES=720x1280 ./start.sh)
    2. environment variable CW_KEY     (older name that run.sh used to export)
    3. config.txt                       (written by scripts/configure.sh)
    4. the default below
Empty values count as unset, like bash's ${KEY:-default}.

The config.txt key is the string in quotes. Every key is documented in
config.example.txt. To add a setting: add it here, then add it to config.example.txt.
Print the effective values with:  python3 -m clipwatcher settings
"""
import os
import shlex

from clipwatcher import paths


def read_config_file(path):
    """Parse a shell-style KEY=value file (quotes and # comments allowed) into a dict."""
    values = {}
    try:
        with open(path, encoding="utf-8") as config_file:
            lines = config_file.read().splitlines()
    except OSError:
        return values
    for line in lines:
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            continue
        for word in words:  # "export KEY=value" also works
            key, has_equals, value = word.partition("=")
            if has_equals and key.isidentifier():
                values[key] = value
    return values


_CONFIG_VALUES = read_config_file(paths.CONFIG_FILE)


def _text(key, default=""):
    for value in (os.environ.get(key), os.environ.get("CW_" + key), _CONFIG_VALUES.get(key)):
        if value:
            return value
    return default


def _int(key, default):
    return int(float(_text(key, str(default))))


def _float(key, default):
    return float(_text(key, str(default)))


def _flag(key, default):
    """'1' = on, anything else = off."""
    return _text(key, "1" if default else "0") == "1"


# --- what to watch -----------------------------------------------------------------
CHANNELS = _text("CHANNELS", _text("CHANNEL"))         # "kaicenat,kick:n3on,youtube:@x"
RECORD_QUALITY = _text("QUALITY", "best")              # streamlink quality (used by watch-channel.sh)

# --- spike detection ---------------------------------------------------------------
SPIKE_MIN_MESSAGES = _int("MIN", 10)                   # min messages in a 10 s bucket
SPIKE_FACTOR = _float("FACTOR", 2.5)                   # bucket must be this x the 3-min median
CLIP_COOLDOWN_S = _int("COOLDOWN", 0)                  # min seconds between clips per channel
CLIP_LENGTH_S = _int("LENGTH", 15)                     # final clip length (viral GTA clips: 8-20 s)
SEARCH_BEFORE_S = _int("SEARCH_BEFORE", 25)            # cut this much before the chat spike...
SEARCH_AFTER_S = _int("SEARCH_AFTER", 6)               # ...and after, then find the real peak in it
AFTER_PEAK_S = _float("AFTER_PEAK", 2.5)               # keep this much after the peak, then hard cut

# --- layout and picture ------------------------------------------------------------
OUTPUT_RESOLUTION = _text("RES", "1080x1920")          # "WIDTHxHEIGHT"
FFMPEG_THREADS = _text("THREADS", "0")                 # 0 = auto
LAYOUT = _text("LAYOUT", "split")                      # split = facecam on top + gameplay below
                                                       # crop = fill screen, fit = full frame + blur
FACECAMS = _text("FACECAMS")                           # manual facecam boxes, "xqc=0.73,0,0.27,0.3;n3on=none"
FACECAM_SHARE = _float("FACECAM_SHARE", 0.38)          # share of the height the facecam gets in split
COLOR_BOOST = _flag("COLOR_BOOST", True)               # punchier colours + sharpen
ZOOM_PUNCH = _flag("ZOOM", True)                       # zoom punch-in on the peak
SHAKE = _flag("SHAKE", True)                           # camera shake on the peak
FLASH = _flag("FLASH", True)                           # white flash frame on the peak

# --- text ----------------------------------------------------------------------------
SHOW_HOOK = _flag("HOOK", True)                        # context hook box
CAPTION_WORDS = _int("CAPTION_WORDS", 2)               # words on screen at a time
WHISPER_MODEL = _text("MODEL", "small")                # tiny / base / small / medium (accuracy vs speed)
WHISPER_VOCABULARY = _text("WHISPER_VOCABULARY",       # words Whisper should expect
                           "GTA 6, GTA VI, Vice City, Leonida, Lucia, Jason, NPC, chat, bro")

# --- sound ---------------------------------------------------------------------------
SFX_VOLUME = _float("SFX_VOLUME", 0.9)                 # impact sound on the peak
MUSIC_VOLUME = _float("MUSIC_VOLUME", 0)               # background music: off (memes + sounds only); e.g. 0.12 to enable
LOUDNESS_LUFS = _float("LOUDNESS", -14)                # final loudness (Shorts/TikTok standard)

# --- memes ---------------------------------------------------------------------------
MEME_CHANCE = _float("MEME_CHANCE", 0.4)               # share of clips with a meme cutaway
MEME_SECONDS = _float("MEME_SECONDS", 1.8)
YTDLP_COOKIES = _text("YTDLP_COOKIES")                 # cookies.txt for yt-dlp (YouTube blocks servers)
FONT_NAME = _text("CW_FONT", "Anton")                  # font family in assets/fonts/
GEMINI_API_KEY = _text("GEMINI_API_KEY")               # optional: AI hooks + meme choice
GEMINI_MODEL = _text("GEMINI_MODEL", "gemini-flash-latest")

# --- captions and posting ----------------------------------------------------------
HASHTAGS = _text("TAGS", "#gaming #shorts")
CALL_TO_ACTION = _text("CTA", "Follow for daily stream clips 🔥")
UPLOAD_TARGETS = _text("UPLOAD", "none")               # "youtube,instagram,facebook" or none
PRIVACY = _text("PRIVACY", "public")                   # YouTube: public / unlisted / private
POSTS_PER_DAY = _text("POSTS_PER_DAY")                 # "youtube=6,instagram=10,facebook=10"
POST_EVERY_H = _float("POST_EVERY", 0)                 # same interval for all (if no POSTS_PER_DAY)
RCLONE_DEST = _text("CW_RCLONE_DEST")                  # e.g. "gdrive:clip-watcher"

# --- disk and housekeeping ---------------------------------------------------------
BUFFER_MINUTES = _int("KEEP_MINUTES", 10)              # rolling recording buffer per channel
KEEP_RECORDINGS_DAYS = _int("KEEP_REC_DAYS", 1)        # used by watch-channel.sh
KEEP_POSTED_CLIP_DAYS = _float("KEEP_CLIP_DAYS", 2)
MAX_QUEUE_AGE_H = _float("MAX_AGE_H", 0)               # 0 = keep until posted
DISK_LIMIT_PERCENT = _float("DISK_LIMIT", 80)
AUTO_LEARN = _flag("AUTO_LEARN", True)

# --- debugging ---------------------------------------------------------------------
DEBUG = _text("CW_DEBUG") != ""                        # log every chat bucket
SCHEDULER_POLL_S = _int("CW_POLL", 300)


def output_size():
    """(width, height) as ints from OUTPUT_RESOLUTION."""
    width, height = OUTPUT_RESOLUTION.split("x")
    return int(width), int(height)


def as_dict():
    """Every setting, for `python3 -m clipwatcher settings`. Secrets are masked."""
    result = {}
    for name, value in globals().items():
        if name.isupper() and not name.startswith("_"):
            result[name] = "***" if "KEY" in name and value else value
    return result
