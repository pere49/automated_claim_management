"""Turning search hits into highlight outlines on the pages.

Each hit names the layout segments it was found in; each segment's .source
is the OCR Word, whose .page_box is its position on the page as displayed
(app/ocr/geometry.py). The value itself is outlined and lightly filled in
its key's colour; its neighbours on the same row are outlined more faintly;
a possible match (faded decimal point) is drawn dashed.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from app.gui.document_view import Shape
from app.matching import POSSIBLE, Hit


@dataclass(frozen=True)
class HighlightStyle:
    colours: dict[str, str]
    fill_alpha: int
    neighbour_alpha: int
    line_px: int


def hit_area(hit: Hit) -> tuple[tuple[float, float], ...]:
    """Page-pixel corners around the hit's value (empty if not placeable)."""
    points = [tuple(p) for seg in hit.segments for p in (_page_box(seg) or [])]
    if not points:
        return ()
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return ((min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys)))


def shapes_for(places: list[tuple[int, Hit]], style: HighlightStyle) -> tuple[list[Shape], int]:
    """Outlines for every hit, and how many hit segments had no page position."""
    shapes: list[Shape] = []
    missing = 0
    for page, hit in places:
        colour = QColor(style.colours[hit.key])
        dashed = hit.strength == POSSIBLE
        for seg in hit.segments:
            box = _page_box(seg)
            if box is None:
                missing += 1
                continue
            shapes.append(Shape(page, box, colour, style.fill_alpha, style.line_px, dashed))
        faint = QColor(colour)
        faint.setAlpha(style.neighbour_alpha)
        for seg in hit.neighbours:
            box = _page_box(seg)
            if box is not None:
                shapes.append(Shape(page, box, faint, 0, max(1, style.line_px - 1), True))
    return shapes, missing


def _page_box(segment) -> tuple[tuple[float, float], ...] | None:
    box = getattr(segment.source, "page_box", None)
    return tuple((float(x), float(y)) for x, y in box) if box else None
