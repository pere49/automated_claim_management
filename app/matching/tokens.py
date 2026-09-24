"""Turning one printed row into tokens that remember where they came from.

A row (app/layout TextRow) is a list of OCR segments left to right. Its text
is split into whitespace-separated tokens; every token records which of the
row's segments its characters came from, so a match can be highlighted.

Two joins, both measured in the search-criteria trial:
  decimal tail  a value OCR split in two ("12,542" + ".00", "1,200." + "00")
                is glued back, only when the right part is exactly a decimal
                tail and the gap is small. Used for amounts only.
  fused word    "Ksh5.00.Amount" -> "Ksh5.00" and "Amount": a value fused to
                the next word by a full stop is split off. Used for amounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_DECIMAL_TAIL = re.compile(r"[.,]\d{2}")
_ENDS_WITH_DECIMAL_MARK = re.compile(r"\d[.,]$")
_TWO_DIGITS = re.compile(r"\d{2}")
_FUSED = re.compile(r"(?<=\d[.,]\d{2})\.(?=[A-Za-z])")


@dataclass(frozen=True)
class Token:
    text: str
    segments: tuple[int, ...]  # indexes into the row's segments, in order


def row_tokens(segments: list[Any], join_tails: bool, gap_per_height: float) -> list[Token]:
    """Tokens of one row. `segments` are app.layout Segments (text, left,
    right, height), left to right."""
    pieces: list[tuple[str, list[int]]] = []  # text, and the segment index of each character
    for i, seg in enumerate(segments):
        text = seg.text
        if join_tails and pieces and _is_tail(segments[i - 1], seg, gap_per_height):
            prev_text, prev_owner = pieces[-1]
            pieces[-1] = (prev_text + text, prev_owner + [i] * len(text))
        else:
            pieces.append((text, [i] * len(text)))
    tokens: list[Token] = []
    for text, owner in pieces:
        for m in re.finditer(r"\S+", text):
            owners = tuple(sorted(set(owner[m.start():m.end()])))
            tokens.append(Token(m.group(), owners))
    return tokens


def split_fused(tokens: list[Token]) -> list[Token]:
    """Split a value fused to the following word by a full stop."""
    out: list[Token] = []
    for tok in tokens:
        parts = [p for p in _FUSED.split(tok.text) if p]
        out.extend(Token(p, tok.segments) for p in parts) if len(parts) > 1 else out.append(tok)
    return out


def label_trim(text: str) -> str:
    """Remove a "Label:" prefix and surrounding punctuation ("DATE:10/08/2026")."""
    return re.sub(r"^[A-Za-z .#]*:", "", text).strip(".,;")


def _is_tail(left: Any, right: Any, gap_per_height: float) -> bool:
    l_text, r_text = left.text.strip(), right.text.strip()
    tail = _DECIMAL_TAIL.fullmatch(r_text) or (_ENDS_WITH_DECIMAL_MARK.search(l_text) and _TWO_DIGITS.fullmatch(r_text))
    return bool(tail) and right.left - left.right <= gap_per_height * min(left.height, right.height)
