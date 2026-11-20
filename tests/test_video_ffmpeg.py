"""End-to-end ffmpeg checks: buffer -> split-layout cut -> peak found -> edited clip with
effects, captions and sound design. Skipped when ffmpeg is not installed. Small sizes."""
import json
import os
import shutil
import subprocess
import time
import unittest
from unittest import mock

from clipwatcher import paths, settings
from clipwatcher.capture.clip_cutter import cut_raw_clip
from clipwatcher.render import pipeline, sound_design
from tests.helpers import TempRepoTestCase

HAS_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def make_test_video(path, seconds, size="320x180", loud_at_s=None):
    """Test pattern with a quiet tone; optionally a loud burst (the "scream") at loud_at_s."""
    volume = (f"volume='if(between(t,{loud_at_s},{loud_at_s + 0.6}),1.0,0.05)':eval=frame"
              if loud_at_s is not None else "volume=0.1")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-af", volume, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path],
                   check=True)


def probe(path, entries):
    return subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", path],
                          capture_output=True, text=True).stdout


def duration_s(path):
    return float(json.loads(probe(path, "format=duration"))["format"]["duration"])


def video_size(path):
    stream = json.loads(probe(path, "stream=width,height"))["streams"][0]
    return stream["width"], stream["height"]


def integrated_loudness(path):
    output = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
    return float(output.rsplit("I:", 1)[1].split("LUFS")[0])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class VideoPipelineTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        for name, value in {"OUTPUT_RESOLUTION": "180x320", "FFMPEG_THREADS": "1", "LAYOUT": "split",
                            "MEME_SECONDS": 1.0, "GEMINI_API_KEY": "",
                            "RCLONE_DEST": ""}.items():
            patcher = mock.patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_split_layout_cut(self):
        recording_dir = os.path.join(self.temp_dir, "rec", "twitch_test")
        os.makedirs(recording_dir)
        lines = []
        for index in range(4):
            source = os.path.join(self.temp_dir, "piece.mp4")
            make_test_video(source, 2)
            piece_name = f"seg_{index:06d}.ts"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", source, "-c", "copy",
                            "-f", "mpegts", os.path.join(recording_dir, piece_name)], check=True)
            lines.append(f"{piece_name},{index * 2.0},{index * 2.0 + 2.0}")
        with open(os.path.join(recording_dir, "list.csv"), "w") as segment_list:
            segment_list.write("\n".join(lines) + "\n")
        recording_start_ts = time.time() - 8
        raw_path = cut_raw_clip(recording_dir, recording_start_ts, recording_start_ts + 5, "twitch_test_1",
                                before_s=3, after_s=2, facecam_box=(0.7, 0.0, 0.3, 0.3))
        self.assertIsNotNone(raw_path)
        self.assertAlmostEqual(duration_s(raw_path), 5, delta=0.5)
        self.assertEqual(video_size(raw_path), (180, 320))
        self.assertIn('"codec_type": "audio"', probe(raw_path, "stream=codec_type"))

    def test_process_clip_full_edit(self):
        os.makedirs(paths.RAW_CLIPS_DIR, exist_ok=True)
        raw_path = os.path.join(paths.RAW_CLIPS_DIR, "twitch_test_2.mp4")
        make_test_video(raw_path, 24, size="180x320", loud_at_s=14.0)  # the "moment" is at 14 s
        os.makedirs(paths.MEMES_DIR, exist_ok=True)
        make_test_video(os.path.join(paths.MEMES_DIR, "shocked-npc.mp4"), 2, size="200x200")
        os.makedirs(paths.MUSIC_DIR, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
                        os.path.join(paths.MUSIC_DIR, "beat.mp3")], check=True)
        transcript = {"text": "no way the npc did that",
                      "segments": [{"words": [{"word": " no", "start": 0.5, "end": 0.8, "probability": 0.9},
                                              {"word": " way", "start": 0.8, "end": 1.1, "probability": 0.9},
                                              {"word": " npc", "start": 9.0, "end": 9.4, "probability": 0.9}]}]}
        job = pipeline.ClipJob(clip_name="twitch_test_2", raw_path=raw_path, source_url="https://twitch.tv/test",
                               stream_info={"creator": "kaicenat", "game": "Grand Theft Auto VI"},
                               length_s=10, spike_at_s=18, score=42, seam_y=120)
        with mock.patch.object(pipeline, "transcribe_window", return_value=transcript) as transcribe:
            queue_item = pipeline.process_clip(job)

        start_s, length_s = transcribe.call_args[0][2], transcribe.call_args[0][3]
        self.assertAlmostEqual(start_s + length_s, 14.0 + 0.3 + settings.AFTER_PEAK_S, delta=0.5)  # ends after peak
        self.assertAlmostEqual(length_s, 10, delta=0.1)
        final_path = os.path.join(paths.READY_CLIPS_DIR, "twitch_test_2.mp4")
        self.assertAlmostEqual(duration_s(final_path), 10, delta=0.6)  # no Gemini -> no guessed meme cutaway
        self.assertAlmostEqual(integrated_loudness(final_path), settings.LOUDNESS_LUFS, delta=2.0)
        self.assertIn("KAI CENAT", queue_item["hook"] + queue_item["title"].upper())
        self.assertTrue(queue_item["title"])
        self.assertFalse(os.path.exists(raw_path))
        leftovers = [name for name in os.listdir(paths.READY_CLIPS_DIR)
                     if name.endswith(".mp4") and (".edit." in name or ".meme." in name or ".work" in name)]
        self.assertEqual(leftovers, [])
        self.assertTrue(os.path.exists(os.path.join(paths.QUEUE_DIR, "twitch_test_2.json")))

    def test_gemini_beat_sheet_renders(self):
        from clipwatcher.render import beats as beat_module, copywriting
        os.makedirs(paths.RAW_CLIPS_DIR, exist_ok=True)
        raw_path = os.path.join(paths.RAW_CLIPS_DIR, "twitch_test_3.mp4")
        make_test_video(raw_path, 20, size="180x320", loud_at_s=12.0)
        os.makedirs(paths.MEMES_DIR, exist_ok=True)
        make_test_video(os.path.join(paths.MEMES_DIR, "crying-guy.mp4"), 2, size="200x150")
        transcript = {"text": "no way bro", "segments": [{"words": [
            {"word": " no", "start": 1.0, "end": 1.3, "probability": 0.9},
            {"word": " way", "start": 1.3, "end": 1.6, "probability": 0.9}]}]}
        reply = {"hook": "PEAK GTA 6 NPC MOMENT", "emphasis": "PEAK", "title": "xQc vs NPC in GTA 6 😭",
                 "comment": "Who wins? 😭", "beats": [
                     {"at": 1.3, "kind": "sound", "value": "impact/punch", "reason": "r", "quote": "no way"},
                     {"at": 1.3, "kind": "emoji", "value": "skull", "reason": "r", "visual": "v"},
                     {"at": 3.0, "kind": "text_card", "value": "nobody cares", "duration": 0.8, "reason": "r", "visual": "v"},
                     {"at": 4.5, "kind": "sticker", "value": "crying-guy.mp4", "duration": 1.5, "reason": "r", "visual": "v"},
                     {"at": 6.0, "kind": "meme", "value": "crying-guy.mp4", "duration": 1.0, "reason": "r", "visual": "v"},
                     {"at": 7.0, "kind": "emoji", "value": "fire", "reason": "r", "visual": "v"},
                     {"at": 8.5, "kind": "zoom", "value": ""},
                     {"at": 9.0, "kind": "made-up-kind", "value": "x"}]}
        job = pipeline.ClipJob(clip_name="twitch_test_3", raw_path=raw_path, source_url="https://twitch.tv/xqc",
                               stream_info={"creator": "xqc", "game": "Grand Theft Auto VI"},
                               length_s=10, spike_at_s=14, seam_y=120)
        with mock.patch.object(settings, "GEMINI_API_KEY", "key"), \
                mock.patch.object(copywriting, "ask_gemini_json", return_value=reply), \
                mock.patch.object(pipeline, "transcribe_window", return_value=transcript):
            queue_item = pipeline.process_clip(job)
        final_path = os.path.join(paths.READY_CLIPS_DIR, "twitch_test_3.mp4")
        self.assertAlmostEqual(duration_s(final_path), 10 + 0.8 + 1.0, delta=0.6)  # + card + meme
        self.assertAlmostEqual(integrated_loudness(final_path), settings.LOUDNESS_LUFS, delta=2.0)
        self.assertEqual(queue_item["hook"], "PEAK GTA 6 NPC MOMENT")
        self.assertEqual(queue_item["comment"], "Who wins? 😭")
        with open(os.path.join(paths.READY_CLIPS_DIR, "twitch_test_3.edit.json"), encoding="utf-8") as report_file:
            report = json.load(report_file)
        self.assertTrue(all(beat.get("reason") for beat in report["beats"] if beat["kind"] != "zoom"))  # says why
        leftovers = [name for name in os.listdir(paths.READY_CLIPS_DIR) if ".work" in name or name.endswith(".ass")]
        self.assertEqual(leftovers, [])

    def test_builtin_sounds_generate(self):
        for name in sound_design.BUILTIN_SOUNDS:
            self.assertGreater(duration_s(sound_design.builtin_sound(name)), 0.3)


if __name__ == "__main__":
    unittest.main()
