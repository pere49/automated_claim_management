"""Repeated receipt pages (D29): which pages show a receipt already shown on an earlier page.

Two checks, measured one document at a time (tools/duplicate_pages_trial:
9 of 15 re-captured receipts caught, 0 of 2,065 different pairs flagged; the
same scan repeated is always caught):
    text    nearly identical words — shared / all >= text_similarity_min;
            found with the exact "prefix filter" (a pair sharing that share
            of its words must share one of each page's rarest words), so
            only candidate pairs are compared
    moment  the same printed date and time and a shared amount; pages are
            filed under each (date, time) they print, so only pages sharing
            one are compared
A shared-reference-number check was dropped: inside one claim it flags two
receipts from the same shop.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict

from app.checking.page_facts import Fingerprint
from app.checking.rules import CheckingRules


def repeated_pages(prints: dict[int, Fingerprint], rules: CheckingRules) -> list[tuple[int, int]]:
    """(earlier page, the later page repeating it), in page order."""
    numbers = sorted(prints)
    found = _near_identical([prints[n] for n in numbers], rules.text_similarity_min)
    found |= _same_moment([prints[n] for n in numbers])
    return sorted((numbers[i], numbers[j]) for i, j in found)


def _near_identical(fps: list[Fingerprint], threshold: float) -> set[tuple[int, int]]:
    freq = Counter(w for f in fps for w in f.words)
    index: dict[str, list[int]] = defaultdict(list)
    found = set()
    for i, f in enumerate(fps):
        ordered = sorted(f.words, key=lambda w: (freq[w], w))
        needed = math.ceil(threshold * len(ordered) - 1e-9)   # 0.9 x 10 is 9.000000000000002 in floating point
        prefix = ordered[: len(ordered) - needed + 1] if ordered else []
        for j in {j for w in prefix for j in index[w]}:
            if _jaccard(fps[j].words, f.words) >= threshold:
                found.add((j, i))
        for w in prefix:
            index[w].append(i)
    return found


def _same_moment(fps: list[Fingerprint]) -> set[tuple[int, int]]:
    groups: dict[tuple, set[int]] = defaultdict(set)
    for i, f in enumerate(fps):
        for key in itertools.product(f.dates, f.times):
            groups[key].add(i)
    return {(i, j) for group in groups.values() for i, j in itertools.combinations(sorted(group), 2)
            if fps[i].amounts & fps[j].amounts}


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / max(1, len(a | b))
