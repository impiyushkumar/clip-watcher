"""End-to-end ffmpeg checks: buffer -> raw cut -> captions burned -> meme spliced.
Skipped when ffmpeg is not installed. Uses small sizes so it runs in seconds."""
import os
import shutil
import subprocess
import time
import unittest
from unittest import mock

from clipwatcher import paths, settings
from clipwatcher.capture.clip_cutter import cut_raw_clip
from clipwatcher.render.subtitles import caption_chunks
from clipwatcher.render.video_effects import burn_captions, insert_meme
from tests.helpers import TempRepoTestCase

HAS_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def make_test_video(path, seconds, size="320x180"):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", path], check=True)


def duration_s(path):
    output = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(output)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg not installed")
class VideoPipelineTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        for name, value in {"OUTPUT_RESOLUTION": "180x320", "FFMPEG_THREADS": "1",
                            "LAYOUT": "crop", "MEME_SECONDS": 1.0}.items():
            patcher = mock.patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_recording_buffer(self, piece_count):
        recording_dir = os.path.join(self.temp_dir, "rec", "twitch_test")
        os.makedirs(recording_dir)
        lines = []
        for index in range(piece_count):
            piece_name = f"seg_{index:06d}.ts"
            source = os.path.join(self.temp_dir, "piece.mp4")
            make_test_video(source, 2)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", source, "-c", "copy",
                            "-f", "mpegts", os.path.join(recording_dir, piece_name)], check=True)
            lines.append(f"{piece_name},{index * 2.0},{index * 2.0 + 2.0}")
        with open(os.path.join(recording_dir, "list.csv"), "w") as segment_list:
            segment_list.write("\n".join(lines) + "\n")
        return recording_dir

    def test_cut_burn_and_meme(self):
        recording_dir = self.make_recording_buffer(piece_count=4)  # 8 s of stream
        recording_start_ts = time.time() - 8
        raw_path = cut_raw_clip(recording_dir, recording_start_ts, spike_ts=recording_start_ts + 5,
                                clip_name="twitch_test_1", before_s=3, after_s=2)
        self.assertIsNotNone(raw_path)
        self.assertAlmostEqual(duration_s(raw_path), 5, delta=0.5)

        transcript = {"segments": [{"words": [{"word": " hello", "start": 0.2, "end": 0.6},
                                              {"word": " chat", "start": 0.6, "end": 1.0}]}]}
        os.makedirs(paths.READY_CLIPS_DIR, exist_ok=True)
        final_path = os.path.join(paths.READY_CLIPS_DIR, "twitch_test_1.mp4")
        self.assertTrue(burn_captions(raw_path, "WAIT FOR IT", final_path, caption_chunks(transcript), spike_at_s=3))
        self.assertTrue(os.path.exists(final_path))

        os.makedirs(paths.MEMES_DIR, exist_ok=True)
        make_test_video(os.path.join(paths.MEMES_DIR, "shocked.mp4"), 2, size="200x200")
        with_meme_path = final_path + ".meme.mp4"
        self.assertTrue(insert_meme(final_path, "shocked.mp4", 3.4, with_meme_path))
        self.assertAlmostEqual(duration_s(with_meme_path), 6, delta=0.6)

    def test_process_clip_queues_finished_clip(self):
        from clipwatcher.render import pipeline
        raw_path = os.path.join(paths.RAW_CLIPS_DIR, "twitch_test_2.mp4")
        os.makedirs(paths.RAW_CLIPS_DIR, exist_ok=True)
        make_test_video(raw_path, 4, size="180x320")
        transcript = {"text": "no way he actually did that chat",
                      "segments": [{"words": [{"word": " no", "start": 0.1, "end": 0.3},
                                              {"word": " way", "start": 0.3, "end": 0.6}]}]}
        job = pipeline.ClipJob(clip_name="twitch_test_2", raw_path=raw_path, source_url="https://twitch.tv/test",
                               stream_info={"creator": "test", "game": ""}, length_s=4, spike_at_s=2, score=42)
        with mock.patch.object(pipeline, "transcribe", return_value=transcript), \
                mock.patch.object(settings, "GEMINI_API_KEY", ""), mock.patch.object(settings, "RCLONE_DEST", ""):
            queue_item = pipeline.process_clip(job)
        self.assertEqual(queue_item["hook"], "NO WAY HE ACTUALLY DID THAT CHAT")
        self.assertEqual(queue_item["final"], os.path.join("clips", "ready", "twitch_test_2.mp4"))
        self.assertTrue(os.path.exists(os.path.join(paths.QUEUE_DIR, "twitch_test_2.json")))
        self.assertFalse(os.path.exists(raw_path))  # raw cut is deleted once the final clip exists
        for extension in (".mp4", ".srt", ".txt"):
            self.assertTrue(os.path.exists(os.path.join(paths.READY_CLIPS_DIR, "twitch_test_2" + extension)))


if __name__ == "__main__":
    unittest.main()
