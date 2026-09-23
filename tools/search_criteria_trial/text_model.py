"""PROTOTYPE (tools/) — search-criteria trial: a page's text as rows of tokens.

A page is a list of OCR segments (text + four-point box). They are grouped
into printed rows by the application's own app/layout, then each row is
turned into a list of tokens (whitespace-separated words), after optionally
joining adjacent segments that OCR split apart:

    join "none"   every segment stands alone
    join "near"   two neighbouring segments are glued (no space) when the
                  gap between them is at most gap_per_height x text height
    join "tail"   glued only when the right segment is a decimal tail (".00",
                  ",50") or the left ends in "." / "," and the right is two
                  digits, and the gap is at most gap_per_height x height
    join "all"    every neighbouring pair on a row is glued (the unsafe
                  baseline: "Qty 1" + "100.00" becomes "Qty 1100.00")

Optionally, digit groups separated by single spaces inside one segment
("1 200.00") are merged into one token (space as thousands separator).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.layout import RowRules, group_rows  # noqa: E402

ROW_RULES = RowRules(same_row_offset_per_height=0.5, max_overlap_per_height=0.5,
                     wide_gap_per_height=1.5, wide_gap_text="    ")
SPACE_GROUP = re.compile(r"\b\d{1,3}(?: \d{3})+(?:\.\d{2})?\b")


@dataclass(frozen=True)
class TextSettings:
    join: str = "none"            # "none" | "near" | "all"
    gap_per_height: float = 0.6
    merge_space_thousands: bool = False


def segment(text: str, x: float, y: float = 0.0, height: float = 20.0) -> SimpleNamespace:
    """A fabricated OCR segment: text at (x, y), 0.5 x height per character."""
    width = max(1, len(text)) * height * 0.5
    return SimpleNamespace(text=text, box=[[x, y], [x + width, y], [x + width, y + height], [x, y + height]])


def page_rows(segments: list, settings: TextSettings) -> list[list[str]]:
    """Rows top to bottom, each a list of tokens left to right."""
    rows = group_rows(segments, ROW_RULES)
    return [row_tokens(row.segments, settings) for row in rows]


def row_tokens(segs: list, settings: TextSettings) -> list[str]:
    pieces: list[str] = []
    prev = None
    for seg in segs:
        text = seg.text
        if settings.merge_space_thousands:
            text = SPACE_GROUP.sub(lambda m: m.group().replace(" ", ""), text)
        if prev is not None and _glue(prev, seg, settings):
            pieces[-1] = pieces[-1] + text
        else:
            pieces.append(text)
        prev = seg
    return [tok for piece in pieces for tok in piece.split()]


def _glue(left, right, settings: TextSettings) -> bool:
    if settings.join == "all":
        return True
    if settings.join == "none":
        return False
    gap = right.left - left.right
    if settings.join == "tail":
        l_text, r_text = left.text.strip(), right.text.strip()
        tail = re.fullmatch(r"[.,]\d{2}", r_text) or \
            (re.search(r"\d[.,]$", l_text) and re.fullmatch(r"\d{2}", r_text))
        return bool(tail) and gap <= settings.gap_per_height * min(left.height, right.height)
    return gap <= settings.gap_per_height * min(left.height, right.height)
