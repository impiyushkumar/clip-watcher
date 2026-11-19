"""Shared test helpers."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from clipwatcher import paths

PATH_NAMES = ["CLIPS_DIR", "RAW_CLIPS_DIR", "READY_CLIPS_DIR", "QUEUE_DIR", "POSTED_DIR",
              "EXPIRED_DIR", "SCOREBOARD_FILE", "AUTO_SETTINGS_FILE", "LEARNING_REPORT_FILE",
              "HEAVY_JOB_LOCK_FILE", "MEMES_DIR", "YOUTUBE_TOKEN_FILE", "META_CONFIG_FILE"]


class TempRepoTestCase(unittest.TestCase):
    """Points every runtime path in clipwatcher.paths at a fresh temporary folder."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="clipwatcher-test-")
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        for name in PATH_NAMES:
            relative = os.path.relpath(getattr(paths, name), paths.ROOT_DIR)
            patcher = mock.patch.object(paths, name, os.path.join(self.temp_dir, relative))
            patcher.start()
            self.addCleanup(patcher.stop)
        root_patcher = mock.patch.object(paths, "ROOT_DIR", self.temp_dir)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)
        os.makedirs(paths.CLIPS_DIR, exist_ok=True)
