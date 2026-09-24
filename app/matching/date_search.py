"""Finding a claimed date on one page (trial winner D4).

A token matches after trimming a "Label:" prefix ("DATE:10/08/2026") when it
equals a one-token form, or starts with one directly followed by a time OCR
fused onto the year ("03/08/2026193:33:31"). Month-name forms spread over
several tokens ("03 Aug 2026", "Jun 12, 2026") match consecutive tokens.

`cores` are the label-trimmed, lower-case tokens of the page, computed once
per page (text_cores); each search is lookups.
"""

from __future__ import annotations

import re

from app.matching.dates import DateForms
from app.matching.found import EXACT, Found
from app.matching.tokens import Token, label_trim

_FUSED_TIME = re.compile(r"\d{1,3}:\d{2}")


def text_cores(rows: list[list[Token]]) -> list[list[str]]:
    """Label-trimmed tokens, lower case (once per page; shared with PINs)."""
    return [[label_trim(t.text).lower() for t in tokens] for tokens in rows]


def find_date(forms: DateForms, rows: list[list[Token]], cores: list[list[str]]) -> list[Found]:
    """Every place the date is printed. `rows` are plain tokens (no joining)."""
    found: list[Found] = []
    seen: set[tuple[int, tuple[int, ...]]] = set()

    def add(r: int, segments: tuple[int, ...]) -> None:
        if (r, segments) not in seen:
            seen.add((r, segments))
            found.append(Found(r, segments, EXACT))

    for r, (tokens, row) in enumerate(zip(rows, cores)):
        for tok, core in zip(tokens, row):
            if core in forms.single or (":" in core and _fused_time(core, forms.single)):
                add(r, tok.segments)
        plain = [c.strip(",") for c in row]
        for i, first in enumerate(plain):
            for form in forms.multi_by_first.get(first, ()):
                if tuple(plain[i:i + len(form)]) == form:
                    add(r, tuple(sorted({s for t in tokens[i:i + len(form)] for s in t.segments})))
    return found


def _fused_time(core: str, single: frozenset[str]) -> bool:
    return any(core.startswith(f) and _FUSED_TIME.match(core[len(f):]) for f in single if len(core) > len(f))
