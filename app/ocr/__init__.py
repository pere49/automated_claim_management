"""OCR: prepare each page and read it with RapidOCR.

Public entry point: OcrReader (reader.py). Everything in pipeline.py is the
proven internal machinery behind it — measure, advise, apply, read — with
its tuning rules in enhance_rules.json and the engine's start-up settings
(speed only, never what is read) in engine_settings.json.
"""

from app.ocr.image_files import read_image_rgb
from app.ocr.pipeline import PDF_EXTS, OcrStageError, Page, PageResult, Word
from app.ocr.reader import OcrReader

__all__ = ["PDF_EXTS", "OcrReader", "OcrStageError", "Page", "PageResult", "Word", "read_image_rgb"]
