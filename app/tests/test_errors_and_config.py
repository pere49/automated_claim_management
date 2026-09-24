"""The shared error shape (app/errors.py) and config reading (app/config_files.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config_files import read_json_config
from app.errors import StageError
from app.ocr import OcrStageError


def _raise_and_catch() -> ValueError:
    try:
        raise ValueError("inner problem")
    except ValueError as exc:
        return exc


class StageErrorTests(unittest.TestCase):
    def test_summary_carries_stage_file_page_and_cause(self):
        error = StageError("load", "could not open", file="a.pdf", page=3, cause=_raise_and_catch())
        self.assertIn("load: a.pdf page 3 - could not open", error.summary)
        self.assertIn("(ValueError: inner problem)", error.summary)
        self.assertNotIn("\n", error.summary)

    def test_full_text_has_traceback_when_wrapping(self):
        error = StageError("load", "could not open", cause=_raise_and_catch())
        self.assertIn("Traceback (most recent call last)", error.full_text)
        self.assertIn("_raise_and_catch", error.full_text)

    def test_full_text_is_summary_without_cause(self):
        error = StageError("config", "bad value")
        self.assertEqual(error.full_text, error.summary)
        self.assertIn("?", error.summary)  # unknown file shown, not blank

    def test_ocr_error_is_a_stage_error(self):
        self.assertTrue(issubclass(OcrStageError, StageError))


class ReadJsonConfigTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.folder = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def write(self, text: str) -> Path:
        path = self.folder / "c.json"
        path.write_text(text, encoding="utf-8")
        return path

    def assertConfigError(self, path: Path, required: dict, fragment: str):
        with self.assertRaises(StageError) as ctx:
            read_json_config(path, required)
        self.assertEqual(ctx.exception.stage, "config")
        self.assertIn(fragment, ctx.exception.summary)

    def test_reads_valid_file(self):
        data = read_json_config(self.write('{"a": 1, "b": "x", "_c": "comment"}'), {"a": int, "b": str})
        self.assertEqual(data["a"], 1)

    def test_missing_file(self):
        self.assertConfigError(self.folder / "nope.json", {}, "not found")

    def test_broken_json(self):
        self.assertConfigError(self.write("{not json"), {}, "not valid JSON")

    def test_top_level_not_object(self):
        self.assertConfigError(self.write("[1, 2]"), {}, "one JSON object")

    def test_missing_and_wrong_type_keys_listed_together(self):
        self.assertConfigError(self.write('{"b": 5}'), {"a": int, "b": str}, "'a' is missing; 'b' must be text")

    def test_true_false_is_not_a_number(self):
        self.assertConfigError(self.write('{"a": true}'), {"a": (int, float)}, "'a' must be")


if __name__ == "__main__":
    unittest.main()
