import json
import os
import time
import unittest
from unittest import mock

from clipwatcher import learner, paths
from clipwatcher.publish import cleanup, scheduler, scoreboard
from tests.helpers import TempRepoTestCase


def make_queued_clip(name, score, posted_to=None):
    os.makedirs(paths.READY_CLIPS_DIR, exist_ok=True)
    os.makedirs(paths.QUEUE_DIR, exist_ok=True)
    final_path = os.path.join(paths.READY_CLIPS_DIR, name + ".mp4")
    with open(final_path, "wb") as video_file:
        video_file.write(b"fake video")
    queue_item = {"clip": name, "final": os.path.relpath(final_path, paths.ROOT_DIR), "caption": "c",
                  "hook": "HOOK " + name, "score": score, "created": "2025-01-01 12:00",
                  "created_ts": time.time(), "source": "twitch: test", "length_s": 30,
                  "meta": {"creator": "test", "game": ""}}
    if posted_to:
        queue_item["posted_to"] = posted_to
    with open(os.path.join(paths.QUEUE_DIR, name + ".json"), "w", encoding="utf-8") as item_file:
        json.dump(queue_item, item_file)
    return queue_item


class HoursBetweenPostsTest(unittest.TestCase):
    def test_per_day(self):
        self.assertEqual(scheduler.hours_between_posts("youtube=6,instagram=10,facebook=0", 4, "none"),
                         {"youtube": 4.0, "instagram": 2.4})

    def test_every_for_upload_targets(self):
        self.assertEqual(scheduler.hours_between_posts("", 3, "youtube, instagram"),
                         {"youtube": 3, "instagram": 3})


class SchedulerTest(TempRepoTestCase):
    def test_posts_best_unposted_clip_then_moves_it(self):
        make_queued_clip("weak", score=5)
        make_queued_clip("strong", score=50)
        make_queued_clip("already", score=999, posted_to={"youtube": "url"})
        posting = scheduler.Scheduler({"youtube": 4.0}, "#shorts", "public", max_age_h=0)
        with mock.patch.object(scheduler, "post_clip", return_value={"youtube": "https://yt/1"}) as post_clip:
            self.assertTrue(posting.post_best_to("youtube"))
        self.assertEqual(post_clip.call_args[0][0]["clip"], "strong")
        self.assertTrue(os.path.exists(os.path.join(paths.POSTED_DIR, "strong.json")))
        self.assertTrue(os.path.exists(paths.queue_stamp_file("youtube")))

    def test_missing_video_expires(self):
        queue_item = make_queued_clip("gone", score=1)
        os.remove(os.path.join(paths.ROOT_DIR, queue_item["final"]))
        posting = scheduler.Scheduler({"youtube": 4.0}, "", "public", max_age_h=0)
        self.assertEqual(posting.waiting_items(), [])
        self.assertTrue(os.path.exists(os.path.join(paths.EXPIRED_DIR, "gone.json")))

    def test_disk_guard_drops_weakest(self):
        make_queued_clip("weak", score=1)
        make_queued_clip("strong", score=100)
        posting = scheduler.Scheduler({"youtube": 4.0}, "", "public", max_age_h=0)
        usage = iter([95, 95, 70])  # over limit, still over after none, then fine
        with mock.patch.object(cleanup, "disk_used_percent", side_effect=lambda: next(usage)):
            cleanup.clean_up(posting.waiting_items())
        remaining = sorted(os.path.basename(path) for path in os.listdir(paths.QUEUE_DIR) if path.endswith(".json"))
        self.assertEqual(remaining, ["strong.json"])


class ScoreboardAndLearnerTest(TempRepoTestCase):
    def test_upsert_fills_existing_row(self):
        scoreboard.upsert_row({"clip": "a", "hook": "H", "youtube_url": ""})
        scoreboard.upsert_row({"clip": "a", "youtube_url": "https://yt/a"})
        rows = scoreboard.read_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["hook"], rows[0]["youtube_url"]), ("H", "https://yt/a"))

    def test_learner_picks_best_length(self):
        old = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 3 * 86400))
        for index in range(10):
            length_s = 20 if index % 2 else 45
            scoreboard.upsert_row({"clip": f"c{index}", "hook": "SHORT HOOK", "length_s": str(length_s),
                                   "views": str(1000 if length_s == 20 else 10), "posted": old})
        auto_settings = learner.learn()
        self.assertEqual(auto_settings["length"], 20)
        self.assertNotIn("hook_words", auto_settings)  # no long hooks to compare with -> not decided yet
        self.assertTrue(os.path.exists(paths.LEARNING_REPORT_FILE))
        with mock.patch.object(learner.random, "random", return_value=0.99):
            self.assertEqual(learner.pick_clip_length(30), 20)

    def test_pick_length_without_data_uses_default(self):
        self.assertEqual(learner.pick_clip_length(30), 30)


if __name__ == "__main__":
    unittest.main()
