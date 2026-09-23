"""A stand-in for OcrReader, so window and worker behaviour can be tested
quickly and every failure path can be forced on purpose, plus a maker of
synthetic PDFs for it to "read"."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pymupdf

from app.ocr import OcrStageError, Page, PageResult, Word


def word(text: str, left: float, top: float, width: float = 40, height: float = 10) -> Word:
    box = [[left, top], [left + width, top], [left + width, top + height], [left, top + height]]
    return Word(text, 0.99, box)


def make_pdf(path: Path, pages: int) -> Path:
    """A synthetic PDF with `pages` near-blank pages."""
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        doc.new_page(width=200, height=260).insert_text((20, 40), f"synthetic page {n}")
    doc.save(path)
    doc.close()
    return path


class FakeReader:
    """Takes the page count from the real (synthetic) PDF; each page reads as
    two rows of synthetic text without any OCR.

    start_error / load_error: raise that OcrStageError from start() / load_pages().
    page_errors: page numbers whose PageResult carries an OCR error.
    crash_pages: page numbers whose read_page() raises a bare exception.
    delay: seconds each read_page() takes (to test cancelling mid-document).
    """

    def __init__(self, *, start_error: bool = False, load_error: bool = False,
                 page_errors: set[int] = frozenset(), crash_pages: set[int] = frozenset(),
                 delay: float = 0.0) -> None:
        self.start_error, self.load_error = start_error, load_error
        self.page_errors, self.crash_pages, self.delay = page_errors, crash_pages, delay
        self.ready = False
        self.pages_read: list[tuple[str, int]] = []

    def start(self) -> None:
        if self.start_error:
            raise OcrStageError("startup", "the OCR engine could not be started", cause=RuntimeError("model missing"))
        self.ready = True

    def load_pages(self, path: Path, dpi: int) -> list[Page]:
        if self.load_error:
            raise OcrStageError("load", "could not open or render this file", file=path.name,
                                cause=ValueError("broken file"))
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as doc:
                count = doc.page_count
        else:
            count = 1  # an image file is one page
        return [Page(path, n, np.full((200, 150, 3), 255, np.uint8)) for n in range(1, count + 1)]

    def read_page(self, page: Page) -> PageResult:
        time.sleep(self.delay)
        self.pages_read.append((page.source.name, page.number))
        if page.number in self.crash_pages:
            raise RuntimeError("simulated crash inside the reader")
        if page.number in self.page_errors:
            error = OcrStageError("ocr", "the OCR engine raised an error while reading a page",
                                  file=page.source.name, page=page.number, cause=RuntimeError("simulated"))
            return PageResult(page.number, [], [], None, [], 0.0, error=error)
        words = [word("TOTAL", 10, 10), word(f"{page.number}00.00", 100, 11), word("THANK YOU", 10, 40)]
        return PageResult(page.number, words, [], None, [], 0.01)
