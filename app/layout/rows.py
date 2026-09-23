"""Group OCR text segments into the printed rows they came from.

RapidOCR returns text as separate segments, each with a four-point box in
the coordinates of the image it read. A printed receipt line is often split
into several segments ("TOTAL", "12,542", ".00"). group_rows() puts them
back into rows, top to bottom, each row's segments left to right.

How: segments are taken in order of their vertical centre; each one joins
the existing row whose centre is closest, if that distance is within
`same_row_offset_per_height` × the smaller of the two heights; otherwise it
starts a new row. A segment never joins a row it would horizontally overlap
(beyond `max_overlap_per_height` × height): text printed over other text is
on a different line. The rule values live in row_rules.json beside this file.

This module is display- and search-neutral: it only groups, it never changes
or interprets any text.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from app.config_files import read_json_config
from app.errors import StageError

DEFAULT_ROW_RULES = Path(__file__).resolve().with_name("row_rules.json")


class HasTextAndBox(Protocol):
    text: str
    box: list[list[float]]


@dataclass(frozen=True)
class RowRules:
    same_row_offset_per_height: float
    max_overlap_per_height: float
    wide_gap_per_height: float
    wide_gap_text: str


@dataclass(frozen=True)
class Segment:
    """One OCR segment, reduced to what grouping needs, plus the original."""
    text: str
    left: float
    right: float
    top: float
    bottom: float
    source: Any  # the object it was made from (an OCR Word), kept for later highlighting

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 1.0)

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class TextRow:
    """One printed row: its segments left to right, and its display text."""
    segments: list[Segment] = field(default_factory=list)
    text: str = ""

    @property
    def center_y(self) -> float:
        return statistics.fmean(s.center_y for s in self.segments)

    @property
    def height(self) -> float:
        return statistics.median(s.height for s in self.segments)


# ---------------------------------------------------------------- public


def load_row_rules(path: Path = DEFAULT_ROW_RULES) -> RowRules:
    """Read and check row_rules.json. Raises StageError(stage="config")."""
    data = read_json_config(path, {
        "same_row_offset_per_height": (int, float),
        "max_overlap_per_height": (int, float),
        "wide_gap_per_height": (int, float),
        "wide_gap_text": str,
    })
    for key in ("same_row_offset_per_height", "wide_gap_per_height"):
        if data[key] <= 0:
            raise StageError("config", f"'{key}' must be greater than zero", file=path.name)
    if data["max_overlap_per_height"] < 0:
        raise StageError("config", "'max_overlap_per_height' must not be negative", file=path.name)
    if not data["wide_gap_text"]:
        raise StageError("config", "'wide_gap_text' must not be empty", file=path.name)
    return RowRules(float(data["same_row_offset_per_height"]), float(data["max_overlap_per_height"]),
                    float(data["wide_gap_per_height"]), data["wide_gap_text"])


def group_rows(words: Iterable[HasTextAndBox], rules: RowRules) -> list[TextRow]:
    """Group segments into rows, top to bottom. Raises StageError(stage=
    "layout") if a segment's box is unusable — callers processing many pages
    catch it per page."""
    segments = [_to_segment(w, i) for i, w in enumerate(words)]
    rows: list[TextRow] = []
    for seg in sorted(segments, key=lambda s: (s.center_y, s.left)):
        row = _closest_row(seg, rows, rules)
        if row is None:
            rows.append(TextRow([seg]))
        else:
            row.segments.append(seg)
    rows.sort(key=lambda r: r.center_y)
    for row in rows:
        row.segments.sort(key=lambda s: s.left)
        row.text = _row_text(row, rules)
    return rows


def ungrouped_rows(words: Iterable[HasTextAndBox]) -> list[TextRow]:
    """Fallback when rules are unavailable: one row per segment, in the
    order the engine returned them, with no grouping claimed."""
    return [TextRow([Segment(str(w.text), 0, 0, 0, 0, w)], str(w.text)) for w in words]


# ---------------------------------------------------------------- internal


def _to_segment(word: HasTextAndBox, index: int) -> Segment:
    try:
        xs = [float(p[0]) for p in word.box]
        ys = [float(p[1]) for p in word.box]
        if not xs or not ys:
            raise ValueError("empty box")
        return Segment(str(word.text), min(xs), max(xs), min(ys), max(ys), word)
    except Exception as exc:
        raise StageError("layout", f"text segment {index + 1} has an unusable position box", cause=exc) from exc


def _closest_row(seg: Segment, rows: list[TextRow], rules: RowRules) -> TextRow | None:
    best, best_offset = None, None
    for row in rows:
        offset = abs(seg.center_y - row.center_y)
        if offset <= rules.same_row_offset_per_height * min(seg.height, row.height)                 and not _overlaps(seg, row, rules):
            if best_offset is None or offset < best_offset:
                best, best_offset = row, offset
    return best


def _overlaps(seg: Segment, row: TextRow, rules: RowRules) -> bool:
    """True if `seg` sits horizontally over any segment already in `row`."""
    for other in row.segments:
        overlap = min(seg.right, other.right) - max(seg.left, other.left)
        if overlap > rules.max_overlap_per_height * min(seg.height, other.height):
            return True
    return False


def _row_text(row: TextRow, rules: RowRules) -> str:
    parts = [row.segments[0].text]
    wide = rules.wide_gap_per_height * row.height
    for prev, seg in zip(row.segments, row.segments[1:]):
        parts.append(rules.wide_gap_text if seg.left - prev.right > wide else " ")
        parts.append(seg.text)
    return "".join(parts)
