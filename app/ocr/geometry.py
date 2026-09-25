"""Mapping OCR text positions back onto the page as it is displayed.

OCR reads a prepared copy of each page (pipeline.py may crop it, straighten
it and resize it), so every Word.box is in that copy's coordinates. The
window shows the page as rendered, before any preparation. For highlights,
each box is mapped back once, in the background, when the page is read:

    forward = page_transform(result.applied, width, height)   # page -> prepared copy
    attach_page_boxes(result, width, height)                   # sets Word.page_box

Only three steps move pixels — crop, rotate, resize — and each is an exact
affine transform, reproduced here from the step functions in pipeline.py
(rotate_bound grows the canvas; the arithmetic below is the same). All other
steps change tone only. Pure arithmetic: no image is touched.
"""

from __future__ import annotations

import math
from typing import Any

Affine = tuple[float, float, float, float, float, float]  # x' = a*x + b*y + c ; y' = d*x + e*y + f

IDENTITY: Affine = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
GEOMETRIC_STEPS = {"crop", "rotate", "resize"}


def page_transform(steps: list[Any], width: int, height: int) -> Affine:
    """The affine map from rendered-page pixels to the prepared copy's pixels,
    for `steps` (objects with .name and .params) applied in order to a page
    of `width` x `height`."""
    forward = IDENTITY
    w, h = float(width), float(height)
    for step in steps:
        if step.name not in GEOMETRIC_STEPS:
            continue
        p = step.params
        if step.name == "crop":
            x0, y0 = int(p["x0"]), int(p["y0"])
            x1, y1 = min(int(p["x1"]), int(w)), min(int(p["y1"]), int(h))
            step_map: Affine = (1.0, 0.0, -x0, 0.0, 1.0, -y0)
            w, h = float(x1 - x0), float(y1 - y0)
        elif step.name == "rotate":
            step_map, w, h = _rotate_bound(float(p["angle_deg"]), w, h)
        else:  # resize
            f = float(p["factor"])
            step_map = (f, 0.0, 0.0, 0.0, f, 0.0)
            w, h = float(round(w * f)), float(round(h * f))
        forward = _compose(step_map, forward)
    return forward


def invert(m: Affine) -> Affine:
    a, b, c, d, e, f = m
    det = a * e - b * d
    if abs(det) < 1e-12:
        raise ValueError("the page transform cannot be inverted")
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    return (ia, ib, -(ia * c + ib * f), id_, ie, -(id_ * c + ie * f))


def apply(m: Affine, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + b * y + c, d * x + e * y + f


def attach_page_boxes(result: Any, width: int, height: int) -> None:
    """Set .page_box on every word of `result` (a PageResult). Raises
    ValueError if the transform is degenerate; callers report it."""
    back = invert(page_transform(result.applied, width, height))
    for word in result.words:
        word.page_box = [[round(v, 1) for v in apply(back, float(px), float(py))] for px, py in word.box]


# ---------------------------------------------------------------- internal


def _compose(second: Affine, first: Affine) -> Affine:
    """second after first."""
    a2, b2, c2, d2, e2, f2 = second
    a1, b1, c1, d1, e1, f1 = first
    return (a2 * a1 + b2 * d1, a2 * b1 + b2 * e1, a2 * c1 + b2 * f1 + c2,
            d2 * a1 + e2 * d1, d2 * b1 + e2 * e1, d2 * c1 + e2 * f1 + f2)


def _rotate_bound(angle_deg: float, w: float, h: float) -> tuple[Affine, float, float]:
    """The same matrix pipeline.rotate_bound builds with cv2.getRotationMatrix2D."""
    cx, cy = w / 2.0, h / 2.0
    alpha, beta = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    new_w = float(int(round(h * abs(beta) + w * abs(alpha))))
    new_h = float(int(round(h * abs(alpha) + w * abs(beta))))
    tx = (1 - alpha) * cx - beta * cy + new_w / 2.0 - cx
    ty = beta * cx + (1 - alpha) * cy + new_h / 2.0 - cy
    return (alpha, beta, tx, -beta, alpha, ty), new_w, new_h
