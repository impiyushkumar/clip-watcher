"""Scheduled posting: each platform posts the best queued clip on its own clock.

    python3 -m clipwatcher.publish.scheduler                       # uses POSTS_PER_DAY from config.txt
    python3 -m clipwatcher.publish.scheduler --per-day "youtube=6,instagram=10"
    python3 -m clipwatcher.publish.scheduler --every 4 --upload youtube,instagram
    python3 -m clipwatcher post-now                                 # best clip everywhere, once

When a platform is due it gets the best clip it hasn't had yet: manual picks first,
then the biggest chat spike. A clip moves to queue/posted/ once every platform has it,
or to queue/expired/ when it is older than --max-age hours (0 = never).
learner.py runs twice a day; posts wait for a good hour (at most one extra interval).
"""
import argparse
import glob
import json
import os
import shutil
import time

from clipwatcher import learner, paths, settings
from clipwatcher.log import log
from clipwatcher.publish.cleanup import clean_up
from clipwatcher.publish.poster import post_clip, resolve_path, split_targets, usable_targets

CLEANUP_EVERY_S = 600
RELEARN_EVERY_S = 12 * 3600
DEFAULT_POST_EVERY_H = 4


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--per-day", default=settings.POSTS_PER_DAY, help='e.g. "youtube=6,instagram=10,facebook=10"')
    parser.add_argument("--every", type=float, default=settings.POST_EVERY_H or DEFAULT_POST_EVERY_H,
                        help="hours between posts for every --upload target (if no --per-day)")
    parser.add_argument("--upload", default=settings.UPLOAD_TARGETS, help="targets when using --every")
    parser.add_argument("--tags", default=settings.HASHTAGS)
    parser.add_argument("--privacy", default=settings.PRIVACY)
    parser.add_argument("--max-age", type=float, default=settings.MAX_QUEUE_AGE_H,
                        help="expire queued clips older than this many hours (0 = keep until posted)")
    parser.add_argument("--once", action="store_true", help="post the best clip to every target now and exit")
    return parser.parse_args(argv)


def hours_between_posts(per_day_text, every_h, upload_text):
    """{platform: hours between posts}, from "youtube=6,..." or one interval for all targets."""
    if per_day_text:
        intervals = {}
        for part in per_day_text.split(","):
            if "=" in part:
                platform, posts_per_day = part.split("=")
                if float(posts_per_day) > 0:
                    intervals[platform.strip()] = 24.0 / float(posts_per_day)
        return intervals
    return {platform: every_h for platform in split_targets(upload_text)}


class Scheduler:
    def __init__(self, intervals_h, hashtags, privacy, max_age_h):
        self.intervals_h = intervals_h
        self.hashtags = hashtags
        self.privacy = privacy
        self.max_age_h = max_age_h
        for folder in (paths.QUEUE_DIR, paths.POSTED_DIR, paths.EXPIRED_DIR):
            os.makedirs(folder, exist_ok=True)

    def waiting_items(self):
        """[(json_path, queue_item)] still waiting. Expired or missing clips are moved out."""
        items = []
        for json_path in glob.glob(os.path.join(paths.QUEUE_DIR, "*.json")):
            with open(json_path, encoding="utf-8") as item_file:
                queue_item = json.load(item_file)
            too_old = self.max_age_h > 0 and time.time() - queue_item["created_ts"] > self.max_age_h * 3600
            if too_old or not os.path.exists(resolve_path(queue_item["final"])):
                shutil.move(json_path, paths.EXPIRED_DIR)
                continue
            items.append((json_path, queue_item))
        return items

    def post_best_to(self, platform):
        """Post the best clip `platform` hasn't had. Returns False if there was none."""
        candidates = [(queue_item["score"], queue_item["created_ts"], json_path, queue_item)
                      for json_path, queue_item in self.waiting_items()
                      if platform not in queue_item.get("posted_to", {})]
        if not candidates:
            return False
        _score, _created_ts, json_path, queue_item = max(candidates, key=lambda entry: entry[:2])
        log(f"[{platform}] posting {queue_item['clip']} (score {queue_item['score']}): {queue_item['hook']}")
        urls = post_clip(queue_item, platform, self.hashtags, self.privacy)
        queue_item.setdefault("posted_to", {})[platform] = urls.get(platform, "failed")
        with open(json_path, "w", encoding="utf-8") as item_file:
            json.dump(queue_item, item_file, indent=1)
        if all(target in queue_item["posted_to"] for target in self.intervals_h):
            shutil.move(json_path, paths.POSTED_DIR)
        with open(paths.queue_stamp_file(platform), "w") as stamp_file:
            stamp_file.write(time.strftime("%Y-%m-%d %H:%M"))
        return True

    def seconds_since_last_post(self, platform):
        stamp_path = paths.queue_stamp_file(platform)
        return time.time() - (os.path.getmtime(stamp_path) if os.path.exists(stamp_path) else 0)

    def run_forever(self):
        last_cleanup_ts = last_learn_ts = 0
        while True:
            if time.time() - last_cleanup_ts > CLEANUP_EVERY_S:
                clean_up(self.waiting_items())
                last_cleanup_ts = time.time()
            if time.time() - last_learn_ts > RELEARN_EVERY_S:
                try:
                    auto_settings = learner.refresh_and_learn()
                    log(f"learned: length {auto_settings.get('length', '-')}s, "
                        f"best hours {auto_settings.get('best_hours') or 'any'}")
                except Exception as error:
                    log(f"learning skipped: {error}")
                last_learn_ts = time.time()
            best_hours = learner.load_auto_settings().get("best_hours") or []
            is_good_hour = not best_hours or time.localtime().tm_hour in best_hours
            for platform, interval_h in self.intervals_h.items():
                since_s = self.seconds_since_last_post(platform)
                # due and a good hour - or we already waited one extra interval
                if since_s >= interval_h * 3600 and (is_good_hour or since_s >= 2 * interval_h * 3600):
                    self.post_best_to(platform)
            time.sleep(settings.SCHEDULER_POLL_S)


def main(argv=None):
    args = parse_args(argv)
    intervals_h = hours_between_posts(args.per_day, args.every, args.upload)
    allowed = set(usable_targets(",".join(intervals_h), explain=True))
    intervals_h = {platform: hours for platform, hours in intervals_h.items() if platform in allowed}
    scheduler = Scheduler(intervals_h, args.tags, args.privacy, args.max_age)
    queued_count = len(glob.glob(os.path.join(paths.QUEUE_DIR, "*.json")))
    summary = ", ".join(f"{platform} {24 / hours:g}/day" for platform, hours in intervals_h.items())
    log(f"poster: {summary or 'no targets'} ({queued_count} queued)")
    if args.once:
        for platform in intervals_h:
            scheduler.post_best_to(platform) or log(f"[{platform}] nothing new to post")
        return
    scheduler.run_forever()


if __name__ == "__main__":
    main()
