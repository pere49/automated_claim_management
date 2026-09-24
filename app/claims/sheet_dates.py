"""Claim-sheet dates: rule R10u (owner-approved 2026-09-24, decisions D26).

Every date cell, whatever the file, is reduced to its possible readings the
same way:
    text 6/10/2026       day-first (as read) and month-first (flipped)
    an Excel date cell   the date stored, and the same with day and month
                         exchanged (an Excel set to the other order stores
                         3/8/2026 typed day-first as 8 March)
    12-Jul-26, ISO, a part above 12: one reading only
Text cells and Excel date cells each get one choice per sheet between "as
read" and "flipped" (Excel's stored order says nothing about how the text
cells were typed), made by the first step that settles it:
    1  a cell with exactly one valid reading shows the order (the owner's
       method 1: a day may be 1-31, a month only 1-12)
    2  no reading can be after the day the claim is checked
    3  the order keeping the sheet within max_claim_span_days
Still open: the cell keeps both readings (DateReading.open) — the receipts
may settle it (app/checking), else the officer does. Never guessed.
Measured in tools/date_parsing_trial (99.67% of 50,282 fabricated dates
right, 2 wrong; all 65 dates of the owner's six real sheets right).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.claims.model import CLAIM_PERIOD, EMPTY, NO_FUTURE, ONE_MEANING, SHEET_ORDER, UNDECIDED, UNREADABLE, DateReading
from app.claims.rules import ClaimRules

EXCEL_EPOCH = date(1899, 12, 30)
AS_READ, FLIPPED = "as read", "flipped"
TEXT, EXCEL, FIXED, NONE, BLANK = "text", "excel", "fixed", "none", "blank"


def read_dates(cells: list[object], today: date, rules: ClaimRules) -> list[DateReading]:
    """One DateReading per cell, the whole sheet deciding together."""
    pairs = [cell_readings(c, rules) for c in cells]
    choice = {kind: _choose(pairs, kind, today, rules) for kind in (TEXT, EXCEL)}
    out = []
    for kind, as_read, flipped in pairs:
        if kind == BLANK:
            out.append(DateReading(None, (), EMPTY))
        elif kind == NONE:
            out.append(DateReading(None, (), UNREADABLE))
        elif as_read is None or flipped is None or as_read == flipped:
            one = as_read or flipped
            out.append(DateReading(one, (one,), ONE_MEANING))
        else:
            picked, how = choice[kind]
            both = (as_read, flipped)
            if picked is None:
                out.append(DateReading(None, both, UNDECIDED))
            else:
                out.append(DateReading(as_read if picked == AS_READ else flipped, both, how))
    return out


def cell_readings(value: object, rules: ClaimRules) -> tuple[str, date | None, date | None]:
    """(kind, as read, flipped) of one cell."""
    if value is None or (isinstance(value, str) and (not value.strip() or value.strip() in rules.empty_marks)):
        return BLANK, None, None
    stored = _excel_date(value, rules)
    if stored is not None:
        if stored.day > 12:
            return EXCEL, stored, None
        if stored.day == stored.month:
            return FIXED, stored, stored
        return EXCEL, stored, date(stored.year, stored.day, stored.month)
    if not isinstance(value, str):
        return NONE, None, None
    text = _clean(value, rules)
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if m:
        d = _valid(int(m[1]), int(m[2]), int(m[3]), rules)
        return (FIXED, d, d) if d else (NONE, None, None)
    parts = [p for p in re.split(r"[-/.,\s]+", text) if p]
    words = [p for p in parts if p.isalpha()]
    numbers = [p for p in parts if p.isdigit()]
    if words:
        month = rules.month_names.get(words[0].lower()) if len(words) == 1 else None
        if month is None or len(numbers) != 2 or len(parts) != 3:
            return NONE, None, None
        day_s, year_s = ((numbers[0], numbers[1]) if len(numbers[1]) in (2, 4) and len(numbers[0]) <= 2
                         else (numbers[1], numbers[0]))
        d = _valid(_year(year_s), month, int(day_s), rules)
        return (FIXED, d, d) if d else (NONE, None, None)
    if len(parts) == 3 and len(numbers) == 3 and len(parts[0]) <= 2 and len(parts[1]) <= 2 and len(parts[2]) in (2, 4):
        a, b, y = int(parts[0]), int(parts[1]), _year(parts[2])
        by_day, by_month = _valid(y, b, a, rules), _valid(y, a, b, rules)
        if by_day is None and by_month is None:
            return NONE, None, None
        return TEXT, by_day, by_month
    return NONE, None, None


# ---------------------------------------------------------------- the sheet's choice


def _choose(pairs: list, kind: str, today: date, rules: ClaimRules) -> tuple[str | None, str]:
    mine = [p for p in pairs if p[0] == kind]
    ambiguous = [p for p in mine if p[1] is not None and p[2] is not None and p[1] != p[2]]
    if not ambiguous:
        return None, UNDECIDED
    votes = {AS_READ if p[1] is not None else FLIPPED for p in mine if (p[1] is None) != (p[2] is None)}
    if len(votes) == 1:
        return votes.pop(), SHEET_ORDER
    if votes:
        return None, UNDECIDED           # the sheet contradicts itself: every open row goes to the receipts / officer
    read = {AS_READ: lambda p: p[1], FLIPPED: lambda p: p[2]}
    options = [o for o in (AS_READ, FLIPPED) if all(read[o](p) <= today for p in ambiguous)]
    if len(options) == 1:
        return options[0], NO_FUTURE
    if not options:
        return None, UNDECIDED
    fixed = [p[1] or p[2] for p in pairs if p[0] not in (BLANK, NONE) and (p[1] is None or p[2] is None or p[1] == p[2])]
    fits = []
    for o in options:
        dates = fixed + [read[o](p) for p in ambiguous]
        if (max(dates) - min(dates)).days <= rules.max_claim_span_days:
            fits.append(o)
    if len(fits) == 1:
        return fits[0], CLAIM_PERIOD
    return None, UNDECIDED


# ---------------------------------------------------------------- one cell


def _excel_date(value: object, rules: ClaimRules) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer():
        d = EXCEL_EPOCH + timedelta(days=int(value))
        return d if rules.date_years[0] <= d.year <= rules.date_years[1] else None
    return None


def _clean(text: str, rules: ClaimRules) -> str:
    t = " ".join(text.split())
    if rules.ocr_digit_repairs:
        letters = "".join(re.escape(k) for k in rules.ocr_digit_repairs)
        pattern = re.compile(rf"(?<=[\d/.\-])[{letters}]|[{letters}](?=[\d/.\-])")
        if re.search(r"\d", t) and not re.search(r"[A-Za-z]{3,}", t):   # never inside a month name
            t = pattern.sub(lambda m: rules.ocr_digit_repairs[m.group(0)], t)
    t = re.sub(r"\s*([/.\-])\s*", r"\1", t)
    t = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", t, flags=re.IGNORECASE)
    return t


def _year(text: str) -> int:
    y = int(text)
    return 2000 + y if y < 100 else y


def _valid(y: int, m: int, d: int, rules: ClaimRules) -> date | None:
    if not rules.date_years[0] <= y <= rules.date_years[1]:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None
