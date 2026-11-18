#!/usr/bin/env python3
"""Scheduled poster: each platform posts on its own schedule from one clip queue.

    python poster.py --per-day "youtube=6,instagram=10,facebook=10"
    python poster.py --every 4 --upload youtube,instagram   (same rate for all)

For each platform, when it's due it posts the best queued clip that platform
hasn't had yet: your manual picks first, then the biggest chat spike. A clip
leaves the queue once every platform has it, or when it's older than --max-age.
"""
import argparse
import glob
import json
import os
import shutil
import time

import learn
import postprocess

ap = argparse.ArgumentParser()
ap.add_argument("--per-day", default="", help='e.g. "youtube=6,instagram=10,facebook=10"')
ap.add_argument("--every", type=float, default=4, help="hours between posts (if no --per-day)")
ap.add_argument("--upload", default="none", help="targets when using --every")
ap.add_argument("--tags", default="#gaming #shorts")
ap.add_argument("--privacy", default="public")
ap.add_argument("--queue", default="clips/queue")
ap.add_argument("--scoreboard", default="clips/scoreboard.csv")
ap.add_argument("--max-age", type=float, default=48, help="drop queued clips older than this (hours)")
ap.add_argument("--once", action="store_true", help="post the best clip to every target now and exit")
a = ap.parse_args()

# target -> hours between posts
if a.per_day:
    every = {}
    for part in a.per_day.split(","):
        if "=" in part:
            t, n = part.split("=")
            if float(n) > 0:
                every[t.strip()] = 24.0 / float(n)
else:
    every = {t.strip(): a.every for t in a.upload.split(",") if t.strip() and t.strip() != "none"}
allowed = os.environ.get("CW_ALLOWED")  # targets that are actually logged in (from check_uploads.sh)
if allowed is not None:
    every = {t: h for t, h in every.items() if t in allowed.split(",")}

posted_dir, old_dir = os.path.join(a.queue, "posted"), os.path.join(a.queue, "expired")
for d in (a.queue, posted_dir, old_dir):
    os.makedirs(d, exist_ok=True)


def stamp(t):
    return os.path.join(a.queue, f".last_{t}")


def queue_items():
    items = []
    for p in glob.glob(os.path.join(a.queue, "*.json")):
        it = json.load(open(p, encoding="utf-8"))
        if time.time() - it["created_ts"] > a.max_age * 3600 or not os.path.exists(it["final"]):
            shutil.move(p, old_dir)
            continue
        items.append((p, it))
    return items


def post_to(target):
    cands = [(it["score"], it["created_ts"], p, it) for p, it in queue_items()
             if target not in it.get("posted_to", {})]
    if not cands:
        return False
    _, _, path, item = max(cands)
    postprocess.log(f"[{target}] posting {item['clip']} (score {item['score']}): {item['hook']}")
    urls = postprocess.post_item(item, target, a.tags, a.privacy, a.scoreboard)
    item.setdefault("posted_to", {})[target] = urls.get(target, "failed")
    json.dump(item, open(path, "w", encoding="utf-8"), indent=1)
    if all(t in item["posted_to"] for t in every):
        shutil.move(path, posted_dir)
    open(stamp(target), "w").write(time.strftime("%Y-%m-%d %H:%M"))
    return True


postprocess.log("poster: " + (", ".join(f"{t} {24 / h:g}/day" for t, h in every.items()) or "no targets")
                + f" ({len(glob.glob(os.path.join(a.queue, '*.json')))} queued)")
if a.once:
    for t in every:
        post_to(t) or postprocess.log(f"[{t}] nothing new to post")
    raise SystemExit

last_learn = 0
while True:
    if time.time() - last_learn > 12 * 3600:   # relearn twice a day
        try:
            auto = learn.refresh_and_learn()
            postprocess.log(f"learned: length {auto.get('length', '-')}s, "
                            f"best hours {auto.get('best_hours') or 'any'}")
        except Exception as e:
            postprocess.log(f"learning skipped: {e}")
        last_learn = time.time()
    hours = learn.load_auto().get("best_hours") or []
    good_hour = not hours or time.localtime().tm_hour in hours
    for t, h in every.items():
        since = time.time() - (os.path.getmtime(stamp(t)) if os.path.exists(stamp(t)) else 0)
        # due, and a good hour - or we've already waited one extra interval
        if since >= h * 3600 and (good_hour or since >= 2 * h * 3600):
            post_to(t)
    time.sleep(int(os.environ.get("CW_POLL", 300)))
