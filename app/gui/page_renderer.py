"""Page sizes and page images of a claim file, for display, on demand.

Coordinates: one "page pixel" is one pixel of the page as the OCR reads it
(PDFs rendered at the OCR resolution; images at their own size). Text
positions from OCR are in page pixels, so the viewer lays pages out in page
pixels and highlights need no conversion. The picture itself may be drawn at
a lower display resolution to save memory; render_page() returns the factor
that scales it back to page pixels.

PDFs are rendered with pymupdf; a photo or screenshot (JPG, PNG, HEIC ...)
is one page, read by the OCR module's own image reader (same pixels, same
orientation as the OCR). render_region() draws only part of a page — the
claim sheet's printed area, given in fractions of the page (D39).
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPixmap

from app.errors import StageError
from app.ocr import PDF_EXTS, read_image_rgb


def page_sizes(path: Path, ocr_dpi: int) -> list[tuple[int, int]]:
    """(width, height) of every page, in page pixels. Nothing is rendered for
    a PDF. Raises StageError(stage="display")."""
    if not _is_pdf(path):
        try:
            height, width = read_image_rgb(path).shape[:2]
        except Exception as exc:
            raise StageError("display", "could not open this image for display", file=path.name, cause=exc) from exc
        return [(width, height)]
    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("the PDF is password-protected")
            matrix = pymupdf.Matrix(ocr_dpi / 72, ocr_dpi / 72)
            sizes = [((page.rect * matrix).irect.width, (page.rect * matrix).irect.height) for page in doc]
    except Exception as exc:
        raise StageError("display", "could not open this file for display", file=path.name, cause=exc) from exc
    if not sizes:
        raise StageError("display", "the file has no pages", file=path.name)
    return sizes


def render_page(path: Path, number: int, ocr_dpi: int, display_dpi: int) -> tuple[QPixmap, float]:
    """Page `number` (1-based) as a pixmap, and the factor from the pixmap's
    pixels to page pixels. Raises StageError(stage="display")."""
    if not _is_pdf(path):
        return _image_pixmap(path, number), 1.0
    try:
        with pymupdf.open(path) as doc:
            pix = doc[number - 1].get_pixmap(dpi=display_dpi, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(image.copy()), ocr_dpi / display_dpi  # copy: outlives pymupdf's buffer
    except Exception as exc:
        raise StageError("display", "could not display this page", file=path.name, page=number, cause=exc) from exc


def render_region(path: Path, number: int, dpi: int, box: tuple[float, float, float, float]) -> QPixmap:
    """The part of page `number` (1-based) inside `box` — (left, top, right, bottom)
    in fractions of the page — drawn at `dpi` (a picture at its own size).
    Raises StageError(stage="display")."""
    left, top, right, bottom = box
    if not 0 <= left < right <= 1 or not 0 <= top < bottom <= 1:
        raise StageError("display", "the part of the page to draw is not inside the page", file=path.name, page=number)
    if not _is_pdf(path):
        pixmap = _image_pixmap(path, number)
        w, h = pixmap.width(), pixmap.height()
        return pixmap.copy(QRect(int(left * w), int(top * h), max(1, int((right - left) * w)),
                                 max(1, int((bottom - top) * h))))
    try:
        with pymupdf.open(path) as doc:
            page = doc[number - 1]
            r = page.rect
            clip = pymupdf.Rect(r.x0 + left * r.width, r.y0 + top * r.height, r.x0 + right * r.width,
                                r.y0 + bottom * r.height)
            pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(image.copy())
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
