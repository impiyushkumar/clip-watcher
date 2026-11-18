#!/usr/bin/env python3
"""Scheduled poster: every N hours, post the best queued clip to all targets.

Best = your manual picks first, then the biggest chat spike. Clips older than
--max-age hours are skipped (old moments don't perform). Runs forever:
    python poster.py --every 4 --upload youtube,instagram,facebook
"""
import argparse
import glob
import json
import os
import shutil
import time

import postprocess

ap = argparse.ArgumentParser()
ap.add_argument("--every", type=float, default=4, help="hours between posts")
ap.add_argument("--upload", default="none")
ap.add_argument("--tags", default="#gaming #shorts")
ap.add_argument("--privacy", default="public")
ap.add_argument("--queue", default="clips/queue")
ap.add_argument("--scoreboard", default="clips/scoreboard.csv")
ap.add_argument("--max-age", type=float, default=48, help="drop queued clips older than this (hours)")
ap.add_argument("--once", action="store_true", help="post one clip now and exit")
a = ap.parse_args()

posted_dir, old_dir = os.path.join(a.queue, "posted"), os.path.join(a.queue, "expired")
for d in (a.queue, posted_dir, old_dir):
    os.makedirs(d, exist_ok=True)
stamp = os.path.join(a.queue, ".last_post")


def next_item():
    items = []
    for p in glob.glob(os.path.join(a.queue, "*.json")):
        it = json.load(open(p, encoding="utf-8"))
        if time.time() - it["created_ts"] > a.max_age * 3600 or not os.path.exists(it["final"]):
            shutil.move(p, old_dir)
            continue
        items.append((it["score"], it["created_ts"], p, it))
    return max(items)[2:] if items else (None, None)


postprocess.log(f"poster: 1 clip every {a.every}h to {a.upload} "
                f"({len(glob.glob(os.path.join(a.queue, '*.json')))} queued)")
while True:
    last = os.path.getmtime(stamp) if os.path.exists(stamp) else 0
    if a.once or time.time() - last >= a.every * 3600:
        path, item = next_item()
        if item:
            postprocess.log(f"posting {item['clip']} (score {item['score']}): {item['hook']}")
            postprocess.post_item(item, a.upload, a.tags, a.privacy, a.scoreboard)
            shutil.move(path, posted_dir)
            open(stamp, "w").write(time.strftime("%Y-%m-%d %H:%M"))
        elif a.once:
            postprocess.log("queue is empty")
    if a.once:
        break
    time.sleep(300)
