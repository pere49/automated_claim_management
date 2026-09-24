"""What one receipt page says, worked out once per page.

    total_marks,      where the receipt prints its total (rule A4m, D33): a
    printed_as_total  row with a total label and no cash / change / card /
                      discount label — or (A4m+) a total label standing right
                      above the amount as its column's header (telebirr's
                      "Settled Amount")
    names_other_buyer a PIN-shaped value after a buyer label that is not the
                      company PIN (D13's CAUTION)
    whole_parts       the whole part of every amount printed with cents
                      (for claims typed with the cents dropped, D27)
    fingerprint       words, dates, times and amounts, for the repeated-page check
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.checking.labels import find_label
from app.checking.rules import CheckingRules
from app.matching import MatchingRules, PreparedPage, is_pin_shaped, pin_matches

CENTS = re.compile(r"(.+)[.,](\d{2})")


@dataclass(frozen=True)
class Fingerprint:
    words: frozenset[str]
    dates: frozenset[date]
    times: frozenset[str]
    amounts: frozenset[Decimal]


@dataclass(frozen=True)
class TotalMarks:
    """Where a page prints its total: rows carrying a total label (and no
    cash / change / card / discount label), and total labels standing as a
    column header (a label alone in its segment, the value printed under it)."""
    rows: frozenset[int]
    headers: tuple[tuple[int, float, float], ...]     # (row, left, right) of a header segment


def total_marks(page: PreparedPage, rules: CheckingRules) -> TotalMarks:
    rows, headers = set(), []
    slips = rules.label_letter_slips
    for i, row in enumerate(page.rows):
        if find_label(row.text, rules.not_total_labels, 0) is not None or any(m in row.text for m in rules.not_total_marks):
            continue
        if find_label(row.text, rules.total_labels, slips) is not None:
            rows.add(i)
        for seg in row.segments:
            if find_label(seg.text, rules.total_labels, slips) is not None and not _holds_number(seg.text):
                headers.append((i, seg.left, seg.right))
    return TotalMarks(frozenset(rows), tuple(headers))


def _holds_number(text: str) -> bool:
    """A word that is a number (a value, not a header). OCR may turn a foreign letter
    inside a label word into a digit ("9th&"), which does not count."""
    return any(re.fullmatch(r"[\d.,'/-]*\d[\d.,'/-]*", word) for word in text.split())


def printed_as_total(hit, marks: TotalMarks, look_above: bool) -> bool:
    """The hit's own row is a total row — or, with look_above, the row right
    above holds a total label as the header of the hit's column."""
    if hit.row in marks.rows:
        return True
    if not look_above or not hit.segments:
        return False
    left, right = min(s.left for s in hit.segments), max(s.right for s in hit.segments)
    return any(row == hit.row - 1 and a < right and left < b for row, a, b in marks.headers)


def names_other_buyer(page: PreparedPage, pin: str | None, rules: CheckingRules, matching: MatchingRules) -> bool:
    if not pin:
        return False
    for row in page.rows:
        low = row.text.lower()
        end = find_label(low, rules.buyer_pin_labels, 0)
        if end is None:
            continue
        for token in low[end:].split():
            value = token.strip(".,:;|").upper()
            if is_pin_shaped(value, matching):
                if not pin_matches(value, pin, matching):
                    return True
                break
    return False


def whole_parts(page: PreparedPage) -> set[str]:
    return {m.group(1) for row in page.amount_cores for core, _ in row
            if (m := CENTS.fullmatch(core)) and m.group(2) != "00"}


def fingerprint(page: PreparedPage, rules: CheckingRules) -> Fingerprint:
    text = " ".join(row.text for row in page.rows)
    dates = set()
    for d, m, y in rules.date_pattern.findall(text):
        year = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            dates.add(date(year, int(m), int(d)))
        except ValueError:
            continue
    amounts = set()
    for raw in rules.amount_pattern.findall(text):
        digits = re.sub(r"[,' ]", "", raw)
        try:
            value = Decimal(digits[:-3].replace(".", "") + "." + digits[-2:])
        except InvalidOperation:
            continue
        if value >= rules.amount_min:
            amounts.add(value)
    return Fingerprint(
        words=frozenset(w.lower() for w in text.split() if len(w) >= rules.word_min_length),
        dates=frozenset(dates),
        times=frozenset(f"{int(h)}:{mi}" for h, mi in rules.time_pattern.findall(text)),
        amounts=frozenset(amounts),
    )
