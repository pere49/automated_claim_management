"""Render one page of a file for display, on demand, in the window's own thread.

PDFs are rendered page by page with pymupdf; a photo or screenshot (JPG,
PNG, HEIC ...) is one page, read by the OCR module's own image reader.
Rendering takes tens of milliseconds, so the page on screen never waits for
the OCR thread, and only the page being looked at is held in memory. Pages
are rendered exactly as the OCR reads them (same resolution for PDFs, same
pixels and orientation for images), so a text position from OCR and a point
on the displayed page share one coordinate frame (needed for highlights).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtGui import QImage, QPixmap

from app.errors import StageError
from app.ocr import PDF_EXTS, read_image_rgb


def page_count(path: Path) -> int:
    """Number of pages (1 for an image). Raises StageError(stage="display")."""
    if not _is_pdf(path):
        _image_pixmap(path, 1)  # an image is one page; opening it also checks it is readable
        return 1
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("the PDF is password-protected")
            count = doc.page_count
    except Exception as exc:
        raise StageError("display", "could not open this file for display", file=path.name, cause=exc) from exc
    if count < 1:
        raise StageError("display", "the file has no pages", file=path.name)
    return count


def render_page(path: Path, number: int, dpi: int) -> QPixmap:
    """Page `number` (1-based) as a pixmap. Raises StageError(stage="display")."""
    if not _is_pdf(path):
        return _image_pixmap(path, number)
    try:
        with pymupdf.open(path) as doc:
            pix = doc[number - 1].get_pixmap(dpi=dpi, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(image.copy())  # copy: the pixmap outlives pymupdf's buffer
    except Exception as exc:
        raise StageError("display", "could not display this page", file=path.name, page=number, cause=exc) from exc


def _is_pdf(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTS


def _image_pixmap(path: Path, number: int) -> QPixmap:
    try:
        rgb = read_image_rgb(path)
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image.copy())  # copy: the pixmap outlives the array
    except Exception as exc:
        raise StageError("display", "could not open this image for display", file=path.name,
                         page=number, cause=exc) from exc
