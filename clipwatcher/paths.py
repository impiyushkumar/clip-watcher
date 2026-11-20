"""Every file and folder clip-watcher reads or writes, as absolute paths.

Always use these constants (via `from clipwatcher import paths` and `paths.X`) instead of
building paths by hand, so the code works no matter which folder it is started from and
tests can point them at a temporary folder.
"""
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# user settings and secrets (all git-ignored)
CONFIG_FILE = os.path.join(ROOT_DIR, "config.txt")
YOUTUBE_CLIENT_SECRET_FILE = os.path.join(ROOT_DIR, "client_secret.json")
YOUTUBE_TOKEN_FILE = os.path.join(ROOT_DIR, "token.json")
META_CONFIG_FILE = os.path.join(ROOT_DIR, "meta.json")

# bundled assets and user-supplied media
FONTS_DIR = os.path.join(ROOT_DIR, "assets", "fonts")
MEMES_DIR = os.path.join(ROOT_DIR, "memes")

# runtime data (git-ignored)
RECORDINGS_DIR = os.path.join(ROOT_DIR, "rec")               # rolling 10 s stream pieces
CLIPS_DIR = os.path.join(ROOT_DIR, "clips")
RAW_CLIPS_DIR = os.path.join(CLIPS_DIR, "raw")               # cut, not yet captioned
READY_CLIPS_DIR = os.path.join(CLIPS_DIR, "ready")           # finished .mp4 + .srt + .txt
QUEUE_DIR = os.path.join(CLIPS_DIR, "queue")                 # one .json per clip waiting to post
POSTED_DIR = os.path.join(QUEUE_DIR, "posted")               # posted to every platform
EXPIRED_DIR = os.path.join(QUEUE_DIR, "expired")             # too old or file missing
SCOREBOARD_FILE = os.path.join(CLIPS_DIR, "scoreboard.csv")  # one row per clip, links + views
AUTO_SETTINGS_FILE = os.path.join(CLIPS_DIR, "auto.json")    # what learner.py decided
LEARNING_REPORT_FILE = os.path.join(CLIPS_DIR, "learning.md")
HEAVY_JOB_LOCK_FILE = os.path.join(CLIPS_DIR, ".heavy.lock")


def queue_stamp_file(platform):
    """Its modification time is when `platform` last posted."""
    return os.path.join(QUEUE_DIR, f".last_{platform}")


def stream_ended_marker(recording_dir):
    """watch-channel.sh creates this file when the stream stops."""
    return recording_dir + ".ended"
