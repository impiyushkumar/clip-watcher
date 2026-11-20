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
                 "summary": "An NPC punches Kai and he yells bro.",
                 "beats": [{"at": 2.0, "kind": "sound", "value": "impact/punch", "reason": "the NPC hits him",
                            "quote": "bro"},
                           {"at": 2.0, "kind": "emoji", "value": "skull", "reason": "he gets embarrassed",
                            "visual": "Kai falls over"},
                           {"at": 4.0, "kind": "sound", "value": "impact/punch", "reason": "made up",
                            "quote": "this was never said"},                          # false quote
                           {"at": 6.0, "kind": "emoji", "value": "fire"},               # no reason/evidence
                           {"at": 0.4, "kind": "text_card", "value": "too early", "reason": "x", "visual": "y"},
                           {"at": 5.0, "kind": "meme", "value": "not-there.mp4", "reason": "x", "visual": "y"},
                           {"at": 6.0, "kind": "sound", "value": "fail/made-up", "reason": "x", "visual": "y"}]}
        menu = {"impact/punch": "someone gets hit", "fail/mission-failed": "dies"}
        transcript = {"text": "bro the npc", "segments": [{"words": [{"word": " bro", "start": 1.9, "end": 2.1}]}]}
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value=reply) as ask:
            copy = copywriting.write_copy(transcript, self.stream_info, length_s=15, peak_s=2.0, sound_menu=menu,
                                          emoji_names=["skull", "fire"], meme_menu={"shocked.mp4": "shock"})
        self.assertEqual(copy.hook, "KAI CENAT GOT PRESSED BY AN NPC IN GTA 6")  # emoji stripped
        self.assertEqual(copy.emphasis, "PRESSED")
        self.assertEqual([(beat.kind, beat.value) for beat in copy.beats],
                         [("sound", "impact/punch"), ("emoji", "skull")])  # no evidence / invented / too early dropped
        self.assertEqual(copy.beats[0].reason, "the NPC hits him")
        self.assertEqual(copy.summary, "An NPC punches Kai and he yells bro.")
        self.assertEqual(copy.rejected_beats, 5)
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
        evidence = {"reason": "fits", "visual": "something happens"}
        raw = [{"at": 1.0, "kind": "sound", "value": "impact/punch", **evidence},
               {"at": 1.1, "kind": "sound", "value": "impact/punch", **evidence},  # too close to the same kind
               {"at": 2.0, "kind": "text_card", "value": "nobody cares", **evidence},
               {"at": 2.5, "kind": "meme", "value": "a.mp4", **evidence},         # cutaway too close
               {"at": 4.0, "kind": "meme", "value": "invented.mp4", **evidence},  # not in the menu
               {"at": 30.0, "kind": "zoom"},                                      # outside the clip
               {"at": "x", "kind": "zoom"}, {"kind": "teleport", "at": 3}, "garbage",
               {"at": 5.0, "kind": "emoji", "value": "skull", "duration": 99, **evidence}]  # duration capped
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


class BeatEvidenceTest(unittest.TestCase):
    def test_quotes_and_chat_must_really_occur_near_the_beat(self):
        from clipwatcher.render.beats import validate_beats
        timed_words = [(3.0, " no"), (3.2, " way"), (3.5, " bro"), (9.0, " nice")]
        chat_messages = [(6.5, "LMAOOO he's cooked"), (12.0, "W")]
        menu = {"impact/punch": "hit", "comedy/boing": "goofy"}
        raw = [{"at": 3.3, "kind": "sound", "value": "impact/punch", "reason": "r", "quote": "no way bro"},  # ok
               {"at": 7.0, "kind": "sound", "value": "comedy/boing", "reason": "r", "quote": "no way bro"},  # wrong time
               {"at": 5.0, "kind": "text_card", "value": "he's cooked", "reason": "chat", "chat": "he's cooked"},  # ok
               {"at": 9.0, "kind": "text_card", "value": "lol", "reason": "chat", "chat": "he's cooked"},  # chat earlier
               {"at": 9.0, "kind": "sound", "value": "comedy/boing", "visual": "falls"}]  # no reason
        beats = validate_beats(raw, 15.0, menu, [], {}, timed_words=timed_words, chat_messages=chat_messages)
        self.assertEqual([(beat.at_s, beat.kind) for beat in beats], [(3.3, "sound"), (5.0, "text_card")])


class TranscriptWindowTest(unittest.TestCase):
    def test_shift_to_window_keeps_only_window_words(self):
        from clipwatcher.render.transcriber import shift_to_window
        padded = {"segments": [{"words": [
            {"word": " before", "start": 2.0, "end": 2.4},
            {"word": " radio", "start": 6.0, "end": 6.4},
            {"word": " tower", "start": 6.4, "end": 6.8},
            {"word": " after", "start": 22.0, "end": 22.3}]}]}
        result = shift_to_window(padded, lead_s=5.0, length_s=15.0)
        self.assertEqual([(word["word"].strip(), word["start"]) for word in result["segments"][0]["words"]],
                         [("radio", 1.0), ("tower", 1.4)])
        self.assertEqual(result["text"], "radio tower")


class CaptionFixTest(unittest.TestCase):
    def test_misheard_words_are_replaced_keeping_times(self):
        from clipwatcher.render.subtitles import apply_caption_fixes, caption_chunks
        transcript = {"segments": [{"words": [{"word": " know", "start": 13.2, "end": 13.4},
                                              {"word": " charge,", "start": 13.4, "end": 13.7},
                                              {"word": " bro", "start": 13.8, "end": 14.0}]}]}
        apply_caption_fixes(transcript, [("know charge", "no charge"), ("x y", "only-one")])
        self.assertEqual(caption_chunks(transcript, max_words=2), [(13.2, 13.7, "NO CHARGE"), (13.8, 14.0, "BRO")])
