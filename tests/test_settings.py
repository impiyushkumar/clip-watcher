import os
import tempfile
import unittest

from clipwatcher import settings


class ReadConfigFileTest(unittest.TestCase):
    def test_parses_quotes_comments_and_export(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as config_file:
            config_file.write("CHANNELS='xqc,kick:n3on'\n"
                              "MODEL=tiny        # ~3x faster captions\n"
                              "TAGS='#gaming #shorts'\n"
                              "# a comment line\n"
                              "export RES=720x1280\n"
                              "CW_RCLONE_DEST=''\n")
        self.addCleanup(os.remove, config_file.name)
        values = settings.read_config_file(config_file.name)
        self.assertEqual(values["CHANNELS"], "xqc,kick:n3on")
        self.assertEqual(values["MODEL"], "tiny")
        self.assertEqual(values["TAGS"], "#gaming #shorts")
        self.assertEqual(values["RES"], "720x1280")
        self.assertEqual(values["CW_RCLONE_DEST"], "")

    def test_missing_file_is_empty(self):
        self.assertEqual(settings.read_config_file("/nonexistent/config.txt"), {})

    def test_secrets_are_masked(self):
        original = settings.GEMINI_API_KEY
        settings.GEMINI_API_KEY = "secret"
        try:
            self.assertEqual(settings.as_dict()["GEMINI_API_KEY"], "***")
        finally:
            settings.GEMINI_API_KEY = original


if __name__ == "__main__":
    unittest.main()
