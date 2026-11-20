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
            copy = copywriting.write_copy({"text": "1 and time 4 and am ago"}, self.stream_info)
        self.assertIn("GTA 6", copy.hook + " " + copy.title)
        self.assertNotIn("AGO", copy.hook)

    def test_fallback_is_stable_across_templates(self):
        with mock.patch.object(settings, "GEMINI_API_KEY", ""):
            for _attempt in range(20):
                copy = copywriting.write_copy({"text": ""}, self.stream_info)
                self.assertIn("KAI CENAT", copy.title.upper())
                self.assertTrue(copy.comment)

    def test_gemini_reply_is_validated_against_menus(self):
        reply = {"hook": "Kai Cenat got PRESSED by an NPC in GTA 6 😭", "emphasis": "pressed",
                 "title": "Kai Cenat got PRESSED by an NPC in GTA 6 😭", "comment": "Would you fight back? 😭",
                 "beats": [{"at": 2.0, "kind": "sound", "value": "impact/punch"},
                           {"at": 2.0, "kind": "emoji", "value": "skull"},
                           {"at": 0.4, "kind": "text_card", "value": "too early"},     # cutaway in the first second
                           {"at": 5.0, "kind": "meme", "value": "not-there.mp4"},
                           {"at": 6.0, "kind": "sound", "value": "fail/made-up"}]}
        menu = {"impact/punch": "someone gets hit", "fail/mission-failed": "dies"}
        transcript = {"text": "bro the npc", "segments": [{"words": [{"word": " bro", "start": 1.9, "end": 2.1}]}]}
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value=reply) as ask:
            copy = copywriting.write_copy(transcript, self.stream_info, length_s=15, peak_s=2.0, sound_menu=menu,
                                          emoji_names=["skull", "fire"], meme_menu={"shocked.mp4": "shock"})
        self.assertEqual(copy.hook, "KAI CENAT GOT PRESSED BY AN NPC IN GTA 6")  # emoji stripped
        self.assertEqual(copy.emphasis, "PRESSED")
        self.assertEqual([(beat.kind, beat.value) for beat in copy.beats],
                         [("sound", "impact/punch"), ("emoji", "skull")])  # invented / too early dropped
        self.assertEqual(copy.comment, "Would you fight back? 😭")
        prompt = ask.call_args[0][0]
        self.assertIn("fail/mission-failed: dies", prompt)  # Gemini sees the whole sound menu
        self.assertIn("shocked.mp4: shock", prompt)         # ...and the meme menu
        self.assertIn("[1.9] bro", prompt)                   # ...and word timings

    def test_bad_gemini_hook_falls_back(self):
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value={"hook": "LOL"}):
            copy = copywriting.write_copy({"text": "text"}, self.stream_info)
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


class BeatValidationTest(unittest.TestCase):
    def test_validation_and_limits(self):
        from clipwatcher.render.beats import validate_beats
        raw = [{"at": 1.0, "kind": "sound", "value": "impact/punch"},
               {"at": 1.1, "kind": "sound", "value": "impact/punch"},          # too close to the same kind
               {"at": 2.0, "kind": "text_card", "value": "nobody cares"},
               {"at": 2.5, "kind": "meme", "value": "a.mp4"},                   # cutaway too close
               {"at": 4.0, "kind": "meme", "value": "invented.mp4"},            # not in the menu
               {"at": 30.0, "kind": "zoom"},                                    # outside the clip
               {"at": "x", "kind": "zoom"}, {"kind": "teleport", "at": 3}, "garbage",
               {"at": 5.0, "kind": "emoji", "value": "skull", "duration": 99}]  # duration capped
        beats = validate_beats(raw, 15.0, {"impact/punch": "hit"}, ["skull"], {"a.mp4": "x"})
        self.assertEqual([(beat.at_s, beat.kind) for beat in beats],
                         [(1.0, "sound"), (2.0, "text_card"), (5.0, "emoji")])
        self.assertEqual(beats[-1].duration_s, 2.5)


class LibraryImportTest(unittest.TestCase):
    def test_myinstants_parsing(self):
        from clipwatcher.library_import import INSTANT_PATTERN
        page = ('<button class="small-button" onclick="play(\'/media/sounds/vine-boom.mp3\', \'loader-1\', \'x\')" '
                'title="Play" type="button"></button><div id="loader-1" class="loader"></div>'
                '<a href="/en/instant/x/" class="instant-link link-secondary">VINE BOOM SOUND</a>')
        match = INSTANT_PATTERN.search(page)
        self.assertEqual((match.group("path"), match.group("title")), ("/media/sounds/vine-boom.mp3", "VINE BOOM SOUND"))


class SoundLibraryMenuTest(unittest.TestCase):
    def test_library_sounds_join_the_menu(self):
        import json, os, tempfile
        from clipwatcher import paths
        from clipwatcher.render import sound_design
        sfx_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(sfx_dir, "reaction"))
        open(os.path.join(sfx_dir, "reaction", "bruh.mp3"), "wb").write(b"x")
        json.dump({"reaction/bruh.mp3": {"use_when": "disappointment, a dumb move"}},
                  open(os.path.join(sfx_dir, "catalog.json"), "w"))
        with mock.patch.object(paths, "SFX_DIR", sfx_dir):
            menu = sound_design.load_sound_menu()
            self.assertEqual(menu["custom/reaction/bruh.mp3"], "disappointment, a dumb move")
            self.assertEqual(sound_design.sound_files("custom/reaction/bruh.mp3"),
                             [os.path.join(sfx_dir, "reaction", "bruh.mp3")])
