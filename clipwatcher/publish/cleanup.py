"""Keep the disk flat. Called every 10 minutes by the scheduler.

1. Delete finished clips that were posted everywhere (or expired) and are older than
   KEEP_CLIP_DAYS. scoreboard.csv keeps their links.
2. Delete raw cuts a crash left behind (older than 1 day).
3. If the disk is over DISK_LIMIT %, drop the WEAKEST unposted clips until it is
   5 points under the limit.
"""
import glob
import json
import os
import shutil
import time

from clipwatcher import paths, settings
from clipwatcher.log import log
from clipwatcher.publish.poster import resolve_path

CLIP_FILE_EXTENSIONS = (".mp4", ".srt", ".txt")
DISK_HEADROOM_PERCENT = 5
STALE_RAW_CLIP_S = 86400


def delete_clip_files(queue_item):
    """Delete the clip's .mp4/.srt/.txt. Returns bytes freed."""
    freed_bytes = 0
    base_path = os.path.splitext(resolve_path(queue_item["final"]))[0]
    for extension in CLIP_FILE_EXTENSIONS:
        if os.path.exists(base_path + extension):
            freed_bytes += os.path.getsize(base_path + extension)
            os.remove(base_path + extension)
    return freed_bytes


def disk_used_percent():
    usage = shutil.disk_usage(paths.ROOT_DIR)
    return usage.used / usage.total * 100


def clean_up(waiting_items):
    """waiting_items: [(json_path, queue_item)] still in the queue, for the disk guard."""
    keep_s = settings.KEEP_POSTED_CLIP_DAYS * 86400
    now_ts = time.time()
    freed_bytes = 0
    for folder in (paths.POSTED_DIR, paths.EXPIRED_DIR):
        for json_path in glob.glob(os.path.join(folder, "*.json")):
            if now_ts - os.path.getmtime(json_path) < keep_s:
                continue
            try:
                with open(json_path, encoding="utf-8") as item_file:
                    freed_bytes += delete_clip_files(json.load(item_file))
                os.remove(json_path)
            except (OSError, ValueError, KeyError):
                pass
    for raw_path in glob.glob(os.path.join(paths.RAW_CLIPS_DIR, "*.mp4")):
        if now_ts - os.path.getmtime(raw_path) > STALE_RAW_CLIP_S:
            freed_bytes += os.path.getsize(raw_path)
            os.remove(raw_path)

    limit_percent = settings.DISK_LIMIT_PERCENT
    if disk_used_percent() > limit_percent:
        weakest_first = sorted(waiting_items, key=lambda entry: (entry[1]["score"], entry[1]["created_ts"]))
        for json_path, queue_item in weakest_first:
            if disk_used_percent() <= limit_percent - DISK_HEADROOM_PERCENT:
                break
            freed_bytes += delete_clip_files(queue_item)
            os.remove(json_path)
            log(f"disk over {limit_percent:.0f}%: dropped weakest unposted clip "
                f"{queue_item['clip']} (score {queue_item['score']})")
    if freed_bytes:
        log(f"cleanup: freed {freed_bytes / 1e9:.2f} GB")
