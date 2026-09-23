"""The window's settings file (app/gui/settings.py)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app import paths
from app.errors import StageError
from app.gui.settings import DEFAULT_SETTINGS, load_settings


class SettingsTests(unittest.TestCase):
    def test_shipped_settings_load(self):
        settings = load_settings()
        self.assertEqual(settings.working_folder, paths.PROJECT_ROOT / "images")
        self.assertEqual(settings.file_extensions, (".pdf", ".jpg", ".jpeg", ".png", ".heic", ".heif"))

    def test_invalid_values_rejected(self):
        good = json.loads(DEFAULT_SETTINGS.read_text(encoding="utf-8"))
        cases = {
            "file_extensions": ["pdf"],
            "pdf_render_dpi": 0,
            "zoom_step": 1,
            "min_zoom": 9,
            "pane_widths": [100, 200],
            "window_size": [100, True],
            "shutdown_wait_seconds": 0,
            "read_ahead": "yes",
        }
        with tempfile.TemporaryDirectory() as folder:
            for key, value in cases.items():
                path = Path(folder) / "s.json"
                path.write_text(json.dumps({**good, key: value}), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(StageError) as ctx:
                    load_settings(path)
                self.assertEqual(ctx.exception.stage, "config")
                self.assertIn(key, ctx.exception.summary)


if __name__ == "__main__":
    unittest.main()
