"""PROTOTYPE (tools/) — duplicate receipt pages: the checks, each written two ways.

A page is its OCR segments' texts in reading order, plus the same segments
grouped into printed rows (app/layout), left to right. `Checks.fingerprint`
reduces it once to the facts every check needs. Each check then exists as
  pairwise  compare every two pages (n x (n-1) / 2 comparisons)
  indexed   one pass that files each page under its keys and compares only
            pages sharing a key; for 'text', the standard prefix filter (a
            pair sharing >= t of their words must share one of each page's
            rarest words), which is exact, not an approximation
and the two must flag the same pairs (run_trial.py asserts it). run_trial.py
measures accuracy; tools/stage_c_timing measures speed. Not used by the app.

Checks
  text        near-identical wording: the same scan or file repeated
  moment      same printed date + same printed time + a shared amount
  references  2+ reference-like numbers printed on these two pages only
  invoice     the same value after an invoice-type label; invoice_value_from
              "reading_order": the words after the label in OCR order;
              "row": the label's own printed row, else the next row's
              first word when invoice_next_row is on
"""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

AMOUNT = re.compile(r"(?<![\d.,])\d{1,3}(?:[,.' ]\d{3})*[.,]\d{2}(?!\d)|(?<![\d.,])\d+[.,]\d{2}(?!\d)")
DATE = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?!\d)")
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
SEPARATORS = r"[\s.:#_-]*"

Pair = tuple[int, int]


@dataclass(frozen=True)
class Fingerprint:
    words: frozenset[str]
    dates: frozenset[str]
    times: frozenset[str]
    amounts: frozenset[Decimal]
    references: frozenset[str]
    invoices: frozenset[str]


class Checks:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        labels = sorted(cfg["invoice_labels"], key=len, reverse=True)
        body = "|".join(SEPARATORS.join(re.escape(p) for p in label.split()) for label in labels)
        self._label = re.compile(rf"(?:{body}){SEPARATORS}", re.IGNORECASE)

    # ---------------------------------------------------------------- one page

    def fingerprint(self, segments: list[str], rows: list[list[str]]) -> Fingerprint:
        text = " ".join(segments)
        return Fingerprint(
            words=frozenset(w.lower() for w in text.split() if len(w) >= self.cfg["word_min_length"]),
            dates=frozenset(f"{int(d)}/{int(m)}/{y[-2:]}" for d, m, y in DATE.findall(text)),
            times=frozenset(f"{int(h)}:{mi}" for h, mi in TIME.findall(text)),
            amounts=frozenset(a for a in _amounts(text) if a >= self.cfg["amount_min"]),
            references=frozenset(self._references(text)),
            invoices=frozenset(self._invoices(segments) if self.cfg["invoice_value_from"] == "reading_order"
                               else self._invoices_by_row(rows)),
        )

    def _references(self, text: str) -> set[str]:
        out = set()
        for raw in text.split():
            t = _alnum(raw)
            if (len(t) >= self.cfg["reference_min_length"] and _digits(t) >= self.cfg["reference_min_digits"]
                    and not AMOUNT.search(raw) and not DATE.search(raw)):
                out.add(t)
        return out

    def _invoices(self, segments: list[str]) -> set[str]:
        out = set()
        ahead = self.cfg["invoice_look_ahead_segments"]
        for i, seg in enumerate(segments):
            for m in self._label.finditer(seg):
                value = self._value([seg[m.end():]] + segments[i + 1:i + 1 + ahead])
                if value:
                    out.add(value)
        return out

    def _invoices_by_row(self, rows: list[list[str]]) -> set[str]:
        out = set()
        for r, row in enumerate(rows):
            for k, seg in enumerate(row):
                for m in self._label.finditer(seg):
                    value = self._value([seg[m.end():]] + row[k + 1:])
                    if value is None and self.cfg["invoice_next_row"] and r + 1 < len(rows):
                        value = self._value(rows[r + 1][:1])
                    if value:
                        out.add(value)
        return out

    def _value(self, texts: list[str]) -> str | None:
        """The first reference-like word among the next invoice_value_tokens words."""
        words = [w for t in texts for w in t.split()][: self.cfg["invoice_value_tokens"]]
        for raw in words:
            t = _alnum(raw)
            if (len(t) >= self.cfg["invoice_value_min_length"] and _digits(t) >= self.cfg["invoice_value_min_digits"]
                    and not AMOUNT.search(raw) and not DATE.search(raw)):
                return t
        return None

    # ---------------------------------------------------------------- pairwise

    def pairwise(self, fps: list[Fingerprint], check: str, threshold: float | None = None) -> set[Pair]:
        th = self.cfg["text_similarity_min"] if threshold is None else threshold
        on_pages = _reference_pages(fps) if check == "references" else None
        found = set()
        for i, j in itertools.combinations(range(len(fps)), 2):
            a, b = fps[i], fps[j]
            if check == "text":
                hit = _jaccard(a.words, b.words) >= th
            elif check == "moment":
                hit = bool(a.dates & b.dates) and bool(a.times & b.times) and bool(a.amounts & b.amounts)
            elif check == "references":
                hit = sum(1 for r in a.references & b.references if on_pages[r] == {i, j}) >= self.cfg["shared_references_min"]
            else:  # invoice
                hit = bool(a.invoices & b.invoices)
            if hit:
                found.add((i, j))
        return found

    # ---------------------------------------------------------------- indexed

    def indexed(self, fps: list[Fingerprint], check: str, threshold: float | None = None) -> set[Pair]:
        th = self.cfg["text_similarity_min"] if threshold is None else threshold
        if check == "text":
            return _near_identical(fps, th)
        if check == "moment":
            groups = defaultdict(set)
            for i, f in enumerate(fps):
                for key in itertools.product(f.dates, f.times):
                    groups[key].add(i)
            return {(i, j) for g in groups.values() for i, j in itertools.combinations(sorted(g), 2)
                    if fps[i].amounts & fps[j].amounts}
        if check == "references":
            shared = Counter(tuple(sorted(p)) for p in _reference_pages(fps).values() if len(p) == 2)
            return {p for p, n in shared.items() if n >= self.cfg["shared_references_min"]}
        groups = defaultdict(set)
        for i, f in enumerate(fps):
            for v in f.invoices:
                groups[v].add(i)
        return {p for g in groups.values() for p in itertools.combinations(sorted(g), 2)}


# ---------------------------------------------------------------- helpers


def _near_identical(fps: list[Fingerprint], th: float) -> set[Pair]:
    """Prefix filter: order words rarest first; a pair with overlap >= th shares
    a word within each page's first |A| - ceil(th x |A|) + 1 words."""
    freq = Counter(w for f in fps for w in f.words)
    index = defaultdict(list)
    found = set()
    for i, f in enumerate(fps):
        ordered = sorted(f.words, key=lambda w: (freq[w], w))
        needed = math.ceil(th * len(ordered) - 1e-9)   # 0.9 x 10 is 9.000000000000002 in floating point
        prefix = ordered[: len(ordered) - needed + 1] if ordered else []
        candidates = {j for w in prefix for j in index[w]}
        for j in candidates:
            if _jaccard(fps[j].words, f.words) >= th:
                found.add((j, i))
        for w in prefix:
            index[w].append(i)
    return found


def _reference_pages(fps: list[Fingerprint]) -> dict[str, set[int]]:
    on_pages = defaultdict(set)
    for i, f in enumerate(fps):
        for r in f.references:
            on_pages[r].add(i)
    return on_pages


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / max(1, len(a | b))


def _amounts(text: str) -> set[Decimal]:
    out = set()
    for m in AMOUNT.findall(text):
        s = re.sub(r"[,' ]", "", m)
        try:
            out.add(Decimal(s[:-3].replace(".", "") + "." + s[-2:]))
        except InvalidOperation:
            pass
    return out


def _alnum(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", text).upper()


def _digits(text: str) -> int:
    return sum(c.isdigit() for c in text)
