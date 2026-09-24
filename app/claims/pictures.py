"""The picture of a scanned claim sheet, in the same pixel frame as its OCR words.

OCR word positions (Word.page_box) are in the page as rendered at the OCR's
resolution (a PDF page) or in the image's own pixels (a photo). The table
lines are looked for in exactly that picture, so words and lines line up.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf

from app.errors import StageError


def page_picture(path: Path, number: int, dpi: int) -> np.ndarray:
    """Grey-scale picture of page `number` (1-based). Raises StageError(stage="claim sheet")."""
    try:
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as doc:
                pix = doc[number - 1].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
                return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
        from app.ocr.image_files import read_image_rgb   # photos only: the same reader OCR used, one pixel frame
        rgb = read_image_rgb(path)
        return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype(np.uint8)
    except StageError:
        raise
    except Exception as exc:
        raise StageError("claim sheet", "could not draw this page to find its table", file=path.name,
                         page=number, cause=exc) from exc
