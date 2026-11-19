import unittest
from unittest import mock

from clipwatcher import settings
from clipwatcher.capture import facecam
from clipwatcher.render import copywriting, moment_finder


class MomentFinderTest(unittest.TestCase):
    def envelope(self, loud_at_s, duration_s=30.0):
        steps = int(duration_s / moment_finder.STEP_S)
        return [(index * moment_finder.STEP_S,
                 -10.0 if abs(index * moment_finder.STEP_S - loud_at_s) < 0.35 else -40.0)
                for index in range(steps)]

    def test_finds_peak_and_onset(self):
        envelope = self.envelope(loud_at_s=18.0)
        peak_s = moment_finder.find_peak_s(envelope)
        self.assertAlmostEqual(peak_s, 18.2, delta=0.3)
        self.assertLess(moment_finder.find_onset_s(envelope, peak_s), peak_s)

    def test_search_range(self):
        envelope = self.envelope(loud_at_s=5.0)
        self.assertGreater(moment_finder.find_peak_s(envelope, search_start_s=10.0), 10.0)
        self.assertIsNone(moment_finder.find_peak_s([], 0, 10))

    def test_window_ends_after_peak_and_is_clamped(self):
        self.assertEqual(moment_finder.choose_window(31.0, 18.0, 15, 2.5), (5.5, 20.5))
        self.assertEqual(moment_finder.choose_window(31.0, 4.0, 15, 2.5), (0.0, 15.0))
        self.assertEqual(moment_finder.choose_window(31.0, 30.5, 15, 2.5), (16.0, 31.0))


class CopywritingTest(unittest.TestCase):
    stream_info = {"creator": "kaicenat", "game": "Grand Theft Auto VI"}

    def test_fallback_names_creator_and_game_without_gibberish(self):
        with mock.patch.object(settings, "GEMINI_API_KEY", ""):
            copy = copywriting.write_copy("1 and time 4 and am ago", self.stream_info)
        self.assertIn("GTA 6", copy.hook + " " + copy.title)
        self.assertNotIn("AGO", copy.hook)

    def test_fallback_is_stable_across_templates(self):
        with mock.patch.object(settings, "GEMINI_API_KEY", ""):
            for _attempt in range(20):
                copy = copywriting.write_copy("", self.stream_info)
                self.assertIn("KAI CENAT", copy.title.upper())
                self.assertTrue(copy.comment)

    def test_gemini_reply_is_validated_against_menus(self):
        reply = {"hook": "Kai Cenat got PRESSED by an NPC in GTA 6 😭", "emphasis": "pressed",
                 "title": "Kai Cenat got PRESSED by an NPC in GTA 6 😭", "peak_sound": "impact/punch",
                 "reaction_sound": "fail/made-up", "emoji": "skull", "meme": "not-there.mp4",
                 "comment": "Would you fight back? 😭"}
        menu = {"impact/punch": "someone gets hit", "fail/mission-failed": "dies"}
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value=reply) as ask:
            copy = copywriting.write_copy("bro the npc", self.stream_info, sound_menu=menu,
                                          emoji_names=["skull", "fire"], meme_names=["shocked.mp4"])
        self.assertEqual(copy.hook, "KAI CENAT GOT PRESSED BY AN NPC IN GTA 6")  # emoji stripped
        self.assertEqual(copy.emphasis, "PRESSED")
        self.assertEqual((copy.peak_sound, copy.reaction_sound), ("impact/punch", ""))  # invented -> dropped
        self.assertEqual((copy.emoji, copy.meme), ("skull", ""))
        self.assertEqual(copy.comment, "Would you fight back? 😭")
        prompt = ask.call_args[0][0]
        self.assertIn("fail/mission-failed: dies", prompt)  # Gemini sees the whole menu

    def test_bad_gemini_hook_falls_back(self):
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value={"hook": "LOL"}):
            copy = copywriting.write_copy("text", self.stream_info)
        self.assertGreaterEqual(len(copy.hook.split()), 3)


class FacecamTest(unittest.TestCase):
    def test_parse_and_clamp(self):
        self.assertEqual(facecam.parse_box("0.73,0,0.27,0.3"), (0.73, 0.0, 0.27, 0.3))
        self.assertEqual(facecam.parse_box("0.9,0.9,0.5,0.5"), (0.9, 0.9, 0.1, 0.1))
        self.assertIsNone(facecam.parse_box("none"))
        self.assertIsNone(facecam.parse_box("0,0,0.02,0.5"))

    def test_config_overrides(self):
        with mock.patch.object(settings, "FACECAMS", "xqc=0.7,0,0.3,0.3; n3on=none"):
            self.assertEqual(facecam.configured_boxes(), {"xqc": (0.7, 0.0, 0.3, 0.3), "n3on": None})
            self.assertIsNone(facecam.facecam_box("n3on", "/no/video.mp4"))


if __name__ == "__main__":
    unittest.main()


class SoundMenuTest(unittest.TestCase):
    def test_keyword_fallback(self):
        from clipwatcher.render import sound_design
        menu = {"impact/punch": "someone gets hit, a fist fight", "danger/siren": "police show up, cops chase"}
        self.assertEqual(sound_design.best_category_by_keywords("the cops are here bro", menu), "danger/siren")
        self.assertIsNone(sound_design.best_category_by_keywords("hello", menu))


class FreshnessRankingTest(unittest.TestCase):
    def test_fresh_clip_beats_old_bigger_spike_but_not_manual(self):
        from clipwatcher.publish.scheduler import ranking_value
        now_ts = 1_000_000.0
        old_big = {"score": 100, "created_ts": now_ts - 12 * 3600}
        fresh = {"score": 40, "created_ts": now_ts - 600}
        manual_old = {"score": 10 ** 6, "created_ts": now_ts - 48 * 3600}
        ranked = sorted([old_big, fresh, manual_old], key=lambda item: ranking_value(item, now_ts), reverse=True)
        self.assertEqual(ranked, [manual_old, fresh, old_big])
