"""Every module must import without optional heavy packages (whisper, google, websocket)."""
import importlib
import pkgutil
import unittest

import clipwatcher


class ImportTest(unittest.TestCase):
    def test_all_modules_import(self):
        for module_info in pkgutil.walk_packages(clipwatcher.__path__, "clipwatcher."):
            with self.subTest(module=module_info.name):
                importlib.import_module(module_info.name)

    def test_cli_help(self):
        from clipwatcher.__main__ import main
        self.assertEqual(main(["help"]), 0)
        self.assertEqual(main(["no-such-command"]), 1)


if __name__ == "__main__":
    unittest.main()
