"""Finding a label's words on a printed row, whole words in order.

Labels only help find where to look (blueprint section 10), so a label word
of four or more letters may differ from the configured word by a few OCR
letter slips ("TOTEL" for TOTAL). Values are never matched this way.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z'\-]+")


def find_label(text: str, labels: tuple[tuple[str, ...], ...], slips: int) -> int | None:
    """Character position just after the first label found on `text`, else None."""
    words = [(m.group(0), m.end()) for m in _WORD.finditer(text.lower())]
    for label in labels:
        n = len(label)
        for i in range(len(words) - n + 1):
            if all(_close(w, part, slips) for (w, _), part in zip(words[i:i + n], label)):
                return words[i + n - 1][1]
    return None


def _close(word: str, label: str, slips: int) -> bool:
    if word == label:
        return True
    if slips == 0 or len(label) < 4 or abs(len(word) - len(label)) > slips:
        return False
    return _distance(word, label, slips) <= slips


def _distance(a: str, b: str, limit: int) -> int:
    """Edit distance, stopping early once it is past `limit`."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]
