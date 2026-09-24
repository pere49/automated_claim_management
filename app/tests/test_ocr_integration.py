"""The real OCR engine end to end, on a synthetic PDF generated here.

Slower than the other tests (it starts RapidOCR); proves the moved OCR
module, OcrReader and row grouping work together on a real render.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf

from app.errors import StageError
from app.layout import group_rows, load_row_rules
from app.ocr import OcrReader, OcrStageError


def synthetic_receipt(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((30, 60), "SYNTHETIC SHOP", fontsize=16)
    page.insert_text((30, 120), "TOTAL", fontsize=14)
    page.insert_text((190, 120), "1,234.00", fontsize=14)
    page.insert_text((30, 180), "DATE 05/08/2026", fontsize=14)
    doc.save(path)
    doc.close()


class OcrIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader = OcrReader()
        cls.reader.start()

    def test_reads_and_groups_a_synthetic_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic.pdf"
            synthetic_receipt(path)
            pages = self.reader.load_pages(path, 300)
        self.assertEqual(len(pages), 1)
        result = self.reader.read_page(pages[0])
        self.assertIsNone(result.error)
        rows = [r.text for r in group_rows(result.words, load_row_rules())]
        self.assertEqual(len(rows), 3, rows)
        self.assertIn("SYNTHETIC SHOP", rows[0])
        self.assertTrue(rows[1].startswith("TOTAL") and rows[1].endswith("1,234.00"), rows[1])
        self.assertIn("05/08/2026", rows[2])
        for w in result.words:  # every word also knows where it is on the page as displayed
            self.assertIsNotNone(w.page_box)
            if not result.applied:
                self.assertEqual(w.page_box, w.box)

    def test_corrupt_pdf_raises_structured_load_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corrupt.pdf"
            path.write_bytes(b"%PDF-1.4 not really a pdf")
            with self.assertRaises(OcrStageError) as ctx:
                self.reader.load_pages(path, 300)
        self.assertEqual((ctx.exception.stage, ctx.exception.file), ("load", "corrupt.pdf"))
        self.assertIn("Traceback", ctx.exception.full_text)

    def test_missing_rules_file_is_a_config_error(self):
        reader = OcrReader(rules_path=Path("no-such-rules.json"))
        with self.assertRaises(StageError) as ctx:
            reader.start()
        self.assertEqual(ctx.exception.stage, "config")

    def test_broken_engine_settings_are_a_config_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "engine_settings.json"
            path.write_text('{"rapidocr_params": "not a section"}', encoding="utf-8")
            with self.assertRaises(StageError) as ctx:
                OcrReader(engine_settings_path=path).start()
        self.assertEqual(ctx.exception.stage, "config")
        self.assertIn("rapidocr_params", ctx.exception.summary)

    def test_engine_settings_file_reaches_the_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "engine_settings.json"
            path.write_text('{"rapidocr_params": {"Global.text_score": 0.6}}', encoding="utf-8")
            reader = OcrReader(engine_settings_path=path)
            reader.start()
        self.assertEqual(reader._engine._ocr.cfg.Global.text_score, 0.6)

    def test_reading_before_start_is_refused_cleanly(self):
        with self.assertRaises(OcrStageError) as ctx:
            OcrReader().load_pages(Path("x.pdf"), 300)
        self.assertEqual(ctx.exception.stage, "startup")


if __name__ == "__main__":
    unittest.main()
