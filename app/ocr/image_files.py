"""Reading a photo or screenshot file (JPG, PNG, HEIC, ...) into pixels.

The one place that decides how an image file becomes pixels: the OCR reads
it through this, and the window displays it through this, so a text
position found by OCR and a point on the displayed image always share one
coordinate frame. The photo's own orientation flag (EXIF) is applied, as a
phone's gallery would show it. HEIC/HEIF needs pillow-heif, which is
registered with Pillow on first use.

Raises whatever Pillow raises; callers wrap it in their own StageError.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_heif_registered = False


def read_image_rgb(path: Path) -> Any:
    """The image as an H x W x 3 uint8 RGB array, orientation applied."""
    import numpy as np
    from PIL import Image, ImageOps

    _register_heif()
    with Image.open(path) as im:
        return np.ascontiguousarray(np.asarray(ImageOps.exif_transpose(im).convert("RGB")))


def _register_heif() -> None:
    global _heif_registered
    if _heif_registered:
        return
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # HEIC files then fail to open, and the caller reports it
    _heif_registered = True
