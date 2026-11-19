import os
import tempfile
import unittest

from clipwatcher.render import subtitles


def transcript_of(*timed_words):
    return {"text": " ".join(word for word, _start, _end in timed_words),
            "segments": [{"words": [{"word": " " + word, "start": start, "end": end}
                                    for word, start, end in timed_words]}]}


class SubtitlesTest(unittest.TestCase):
    def test_chunks_of_three_words_break_on_punctuation(self):
        transcript = transcript_of(("no", 0, 0.2), ("way,", 0.2, 0.4), ("he", 0.5, 0.6),
                                   ("actually", 0.6, 1.0), ("did", 1.0, 1.2), ("it", 1.2, 1.4))
        self.assertEqual(subtitles.caption_chunks(transcript),
                         [(0, 0.4, "NO WAY"), (0.5, 1.2, "HE ACTUALLY DID"), (1.2, 1.4, "IT")])

    def test_time_formats(self):
        self.assertEqual(subtitles.srt_time(3661.5), "01:01:01,500")
        self.assertEqual(subtitles.ass_time(3661.5), "1:01:01.50")

    def test_write_srt_and_ass(self):
        transcript = transcript_of(("hello", 0, 0.5), ("chat", 0.5, 1.0))
        temp_dir = tempfile.mkdtemp()
        srt_path, ass_path = os.path.join(temp_dir, "clip.srt"), os.path.join(temp_dir, ".style.ass")
        self.assertEqual(subtitles.write_srt(transcript, srt_path), 1)
        with open(srt_path, encoding="utf-8") as srt_file:
            self.assertIn("00:00:00,000 --> 00:00:01,000\nHELLO CHAT", srt_file.read())
        subtitles.write_ass(ass_path, subtitles.caption_chunks(transcript), "WAIT FOR IT")
        with open(ass_path, encoding="utf-8") as ass_file:
            ass_text = ass_file.read()
        self.assertIn("HELLO CHAT", ass_text)
        self.assertIn("WAIT FOR IT", ass_text)

    def test_empty_transcript(self):
        self.assertEqual(subtitles.caption_chunks({"segments": []}), [])


if __name__ == "__main__":
    unittest.main()
