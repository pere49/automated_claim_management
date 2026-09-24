"""PROTOTYPE (tools/) — date trial: candidate rules for reading claim-sheet dates.

Every rule gets a whole sheet (the cells of its date column) and returns,
per row, a date or None (left for the officer). Shared first step, `readings`:
each cell's possible dates —
  one reading   Excel date cell, Excel serial number, ISO (2026-07-12), a
                month word (12-Jul-26, Jul 12, 2026), or numeric with a part
                above 12 (23/6/2026)
  two readings  numeric with both parts 12 or below (6/10/2026)
after undoing OCR-style noise (O for 0, l for 1, S for 5, stray spaces).

Rules
  R1 day-first      every numeric date read day-first
  R2 month-first    every numeric date read month-first
  R3 per-row        one reading if only one is valid, else day-first
  R4 sheet-vote     the sheet's order = the order of its one-reading numeric
                    dates; conflicting votes or no votes -> two-reading rows
                    left for the officer
  R5 +chronology    R4; with no votes, the order that keeps the sheet's dates
                    within max_claim_span_days, if only one does
  R6 +receipts      R5; rows still undecided take the one reading found on a
                    receipt carrying the row's amount, if exactly one is
  R7 receipts-first two-reading rows: first the one reading found on a
                    receipt (if exactly one), then R5's sheet order
  R8 R7 + guard     R7, but a sheet whose votes conflict (a writer who swaps)
                    never lends its order to a two-reading row: only receipts
                    can settle those rows
  R9 R6 + contradiction  R6, but when the sheet's order gives a reading that
                    no receipt shows while the other reading is on a receipt,
                    the row goes to the officer instead (a writer who swapped
                    that one row)
  R10 R9 + Excel order   R9 for text; an Excel date cell (or serial number)
                    whose day is 12 or less also has two readings, the
                    stored one and the swapped one. The sheet decides
                    stored-or-swapped: votes (a date cell with day > 12 votes
                    "stored"; a slash-written text date with one valid order
                    votes "swapped", since Excel would have converted it in
                    its own order), then chronology (which choice keeps the
                    sheet within max_claim_span_days), then per row the one
                    reading on a receipt, then R9's contradiction guard.
                    Nothing decides: the stored date.
  R10s strict       R10, but nothing decides: the one reading on a receipt,
                    else left for the officer
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

EXCEL_EPOCH = date(1899, 12, 30)


class Parser:
    def __init__(self, cfg: dict) -> None:
        self.months = {}
        for num, names in cfg["month_names"].items():
            for name in names:
                self.months[name.lower()] = int(num)
        self.max_span = cfg["max_claim_span_days"]

    # ---------------------------------------------------------------- one cell

    def readings(self, cell) -> tuple[list[date], bool]:
        """(possible dates, numeric?) — numeric means the order question applies."""
        if cell is None:
            return [], False
        if isinstance(cell, datetime):
            return [cell.date()], False
        if isinstance(cell, date):
            return [cell], False
        if isinstance(cell, (int, float)):
            d = EXCEL_EPOCH + timedelta(days=int(cell))
            return ([d], False) if 1990 <= d.year <= 2100 else ([], False)
        text = self._clean(str(cell))
        m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
        if m:
            return self._valid(int(m[1]), int(m[2]), int(m[3])), False
        parts = [p for p in re.split(r"[-/.,\s]+", text) if p]
        words = [p for p in parts if p.isalpha()]
        if words:
            month = self._month(words[0])
            nums = [p for p in parts if p.isdigit()]
            if month is None or len(words) != 1 or len(nums) != 2:
                return [], False
            day_s, year_s = (nums[0], nums[1]) if len(nums[1]) in (2, 4) and len(nums[0]) <= 2 else (nums[1], nums[0])
            return self._valid(self._year(year_s), month, int(day_s)), False
        if len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) <= 2 and len(parts[1]) <= 2:
            a, b, y = int(parts[0]), int(parts[1]), self._year(parts[2])
            found = {d for d in self._valid(y, b, a) + self._valid(y, a, b)}  # day-first, month-first
            return sorted(found), True
        return [], False

    def day_first(self, cell) -> date | None:
        return self._pick(cell, "day")

    def month_first(self, cell) -> date | None:
        return self._pick(cell, "month")

    def _pick(self, cell, order: str) -> date | None:
        dates, numeric = self.readings(cell)
        if not numeric:
            return dates[0] if len(dates) == 1 else None
        text = self._clean(str(cell))
        a, b, y = re.split(r"[-/.,\s]+", text)[:3]
        day, month = (int(a), int(b)) if order == "day" else (int(b), int(a))
        valid = self._valid(self._year(y), month, day)
        return valid[0] if valid else None

    # ---------------------------------------------------------------- helpers

    def _clean(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"(?<=\d)[Oo](?=[\d/.\-])|(?<=[/.\-])[Oo](?=\d)", "0", t)
        t = re.sub(r"(?<=\d)[lI|](?=[\d/.\-])|(?<=[/.\-])[lI|](?=\d)|^[lI|](?=\d)", "1", t)
        t = re.sub(r"(?<=\d)S(?=[\d/.\-])|(?<=[/.\-])S(?=\d)", "5", t)
        t = re.sub(r"\s*([/.\-])\s*", r"\1", t)
        t = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", t, flags=re.I)
        return t

    def _month(self, word: str) -> int | None:
        w = word.lower()
        return self.months.get(w)

    @staticmethod
    def _year(text: str) -> int:
        y = int(text)
        return 2000 + y if y < 100 else y

    @staticmethod
    def _valid(y: int, m: int, d: int) -> list[date]:
        try:
            return [date(y, m, d)]
        except ValueError:
            return []


# ---------------------------------------------------------------- rules


def run_rule(rule: str, parser: Parser, cells: list, receipts: list[set]) -> list[date | None]:
    if rule in ("R10", "R10s"):
        return _run_excel_aware(rule, parser, cells, receipts)
    if rule == "R1":
        return [parser.day_first(c) for c in cells]
    if rule == "R2":
        return [parser.month_first(c) for c in cells]
    info = [parser.readings(c) for c in cells]
    if rule == "R3":
        return [d[0] if len(d) == 1 else (parser.day_first(c) if d else None) for c, (d, _) in zip(cells, info)]

    order, conflict = _sheet_order(parser, cells, info)
    if order is None and not conflict and rule in ("R5", "R6", "R7", "R8", "R9"):
        order = _chronology(parser, cells, info)
    out: list[date | None] = []
    for c, (dates, numeric), rec in zip(cells, info, receipts):
        if len(dates) <= 1:
            out.append(dates[0] if dates else None)
            continue
        on_receipt = [d for d in dates if d in rec]
        by_receipt = on_receipt[0] if len(on_receipt) == 1 else None
        by_order = (parser.day_first(c) if order == "day" else parser.month_first(c)) if order else None
        if rule in ("R4", "R5"):
            out.append(by_order)
        elif rule == "R6":
            out.append(by_order or by_receipt)
        elif rule == "R9":
            contradicted = by_order is not None and by_order not in rec and by_receipt not in (None, by_order)
            out.append(None if contradicted else (by_order or by_receipt))
        elif rule == "R7":
            out.append(by_receipt or by_order)
        else:  # R8
            out.append(by_receipt or (None if conflict else by_order))
    return out


def _sheet_order(parser: Parser, cells: list, info: list) -> tuple[str | None, bool]:
    votes = set()
    for c, (dates, numeric) in zip(cells, info):
        if not numeric:
            continue
        by_day, by_month = parser.day_first(c), parser.month_first(c)
        if (by_day is None) != (by_month is None):  # exactly one order is valid: a real vote
            votes.add("day" if by_day else "month")   # (4/4/2027 reads the same both ways: no vote)
    if len(votes) == 1:
        return votes.pop(), False
    return None, len(votes) > 1


def _chronology(parser: Parser, cells: list, info: list) -> str | None:
    fits = []
    for order in ("day", "month"):
        ds = [((parser.day_first(c) if order == "day" else parser.month_first(c)) if len(d) > 1 else (d[0] if d else None))
              for c, (d, _) in zip(cells, info)]
        ds = [d for d in ds if d]
        if ds and (max(ds) - min(ds)).days <= parser.max_span:
            fits.append(order)
    return fits[0] if len(fits) == 1 else None


# ---------------------------------------------------------------- R10: Excel date cells


def _run_excel_aware(rule: str, parser: Parser, cells: list, receipts: list[set]) -> list[date | None]:
    text_out = run_rule("R9", parser, cells, receipts)
    info = [parser.readings(c) for c in cells]
    choice = _excel_choice(parser, cells, info)
    out = []
    for c, got, rec in zip(cells, text_out, receipts):
        stored = _excel_date(c)
        swapped = _swap(stored) if stored else None
        if stored is None or swapped is None:
            out.append(got)
            continue
        on_receipt = [d for d in (stored, swapped) if d in rec]
        by_receipt = on_receipt[0] if len(on_receipt) == 1 else None
        by_sheet = {"stored": stored, "swapped": swapped}.get(choice)
        if by_sheet is not None:
            contradicted = by_sheet not in rec and by_receipt not in (None, by_sheet)
            out.append(None if contradicted else by_sheet)
        else:
            out.append(by_receipt or (stored if rule == "R10" else None))
    return out


def _excel_choice(parser: Parser, cells: list, info: list) -> str | None:
    votes = set()
    for c, (dates, numeric) in zip(cells, info):
        stored = _excel_date(c)
        if stored is not None:
            if stored.day > 12:
                votes.add("stored")
        elif (isinstance(c, str) and numeric and "/" in c
              and (parser.day_first(c) is None) != (parser.month_first(c) is None)):
            votes.add("swapped")
    if len(votes) == 1:
        return votes.pop()
    if votes:
        return None
    fits = []
    for choice in ("stored", "swapped"):
        ds = []
        for c, (dates, numeric) in zip(cells, info):
            stored = _excel_date(c)
            if stored is not None:
                ds.append((_swap(stored) or stored) if choice == "swapped" else stored)
            elif len(dates) == 1:
                ds.append(dates[0])
        if ds and (max(ds) - min(ds)).days <= parser.max_span:
            fits.append(choice)
    return fits[0] if len(fits) == 1 else None


def _excel_date(cell) -> date | None:
    """The stored date of an Excel date cell or serial number; None for anything else."""
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, int) and not isinstance(cell, bool):
        d = EXCEL_EPOCH + timedelta(days=cell)
        return d if 1990 <= d.year <= 2100 else None
    return None


def _swap(d: date) -> date | None:
    """The same date with day and month exchanged, if that is a different valid date."""
    if d.day > 12 or d.day == d.month:
        return None
    return date(d.year, d.day, d.month)
