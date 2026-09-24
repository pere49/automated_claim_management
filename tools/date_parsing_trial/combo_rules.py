"""PROTOTYPE (tools/) — date trial: rules built from steps, including the owner's two methods.

Every date cell is reduced to two readings the same way, whatever the file:
  text 6/10/2026     as read = day-first (the local convention), flipped = month-first
  Excel date cell    as read = the stored date, flipped = day and month exchanged
  month word, ISO    one reading only
A cell is ambiguous when both readings are valid and differ. Text cells and
Excel cells each get their own sheet-level choice between "as read" and
"flipped": Excel's stored order says nothing about how the text cells were
typed, so neither lends its choice to the other, and nothing depends on a
file's display format.

Steps, in order, each only while the choice is still open:
  votes       the owner's method 1: a day can be 1-31 but a month only 1-12,
              so a cell with exactly one valid reading shows the sheet's
              choice; conflicting votes leave the choice open for good
  future      a reading after the day the claim is checked is impossible
  chronology  the choice that keeps the sheet within max_claim_span_days
  closeness   the owner's method 2: the choice lying closer to the day the
              claim is checked — "last": the last listed ambiguous date
              decides (as the owner described it); "all": every ambiguous
              date counts; "each": every date decides for itself
  receipts    per row: the one reading found on a receipt carrying the amount
  guard       the sheet's choice contradicted by the row's receipt -> officer
  undecided   "as_read", or "officer" (never guessed)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from strategies import Parser, _excel_date


@dataclass(frozen=True)
class Steps:
    votes: bool = True
    future: bool = False
    chronology: bool = False
    closeness: str | None = None      # "last" | "all" | "each"
    receipts: bool = False
    guard: bool = False
    undecided: str = "officer"        # "as_read" | "officer"


COMBOS = {
    "U1": Steps(closeness="last", undecided="as_read"),                    # the owner's methods as described
    "U0": Steps(closeness="each", undecided="as_read"),                    # method 2 applied date by date
    "U2": Steps(future=True, closeness="all", undecided="as_read"),        # method 2 on every date, no future
    "R10u": Steps(future=True, chronology=True, receipts=True, guard=True),
    "R11": Steps(future=True, chronology=True, closeness="all", receipts=True, guard=True),
}


def pair(parser: Parser, cell) -> tuple[str, date | None, date | None]:
    """(kind, as read, flipped); kind is "text", "excel", "fixed" or "none"."""
    stored = _excel_date(cell)
    if stored is not None:
        if stored.day > 12:
            return "excel", stored, None
        if stored.day == stored.month:
            return "fixed", stored, stored
        return "excel", stored, date(stored.year, stored.day, stored.month)
    dates, numeric = parser.readings(cell)
    if not dates:
        return "none", None, None
    if not numeric:
        return "fixed", dates[0], dates[0]
    by_day, by_month = parser.day_first(cell), parser.month_first(cell)
    if by_day == by_month:
        return "fixed", by_day, by_day
    return "text", by_day, by_month


def run_combo(steps: Steps, parser: Parser, cells: list, receipts: list[set], today: date) -> list[date | None]:
    pairs = [pair(parser, c) for c in cells]
    choice = {kind: _choose(steps, parser, pairs, kind, today) for kind in ("text", "excel")}
    out: list[date | None] = []
    for (kind, as_read, flipped), rec in zip(pairs, receipts):
        if kind == "none":
            out.append(None)
        elif as_read is None or flipped is None or as_read == flipped:
            out.append(as_read or flipped)
        elif steps.closeness == "each" and choice[kind] is None:
            options = [d for d in (as_read, flipped) if not steps.future or d <= today]
            out.append(min(options, key=lambda d: abs((today - d).days)) if options else None)
        else:
            by_sheet = {"as_read": as_read, "flipped": flipped}.get(choice[kind])
            on_receipt = [d for d in (as_read, flipped) if d in rec]
            by_receipt = on_receipt[0] if len(on_receipt) == 1 else None
            if by_sheet is not None:
                contradicted = steps.guard and by_sheet not in rec and by_receipt not in (None, by_sheet)
                out.append(None if contradicted else by_sheet)
            elif steps.receipts and by_receipt is not None:
                out.append(by_receipt)
            else:
                out.append(as_read if steps.undecided == "as_read" else None)
    return out


def _choose(steps: Steps, parser: Parser, pairs: list, kind: str, today: date) -> str | None:
    mine = [p for p in pairs if p[0] == kind]
    ambiguous = [p for p in mine if p[1] is not None and p[2] is not None and p[1] != p[2]]
    if not ambiguous:
        return None
    read = {"as_read": lambda p: p[1], "flipped": lambda p: p[2]}
    if steps.votes:
        votes = {"as_read" if p[1] is not None else "flipped" for p in mine if (p[1] is None) != (p[2] is None)}
        if len(votes) == 1:
            return votes.pop()
        if votes:
            return None
    options = ["as_read", "flipped"]
    if steps.future:
        options = [o for o in options if all(read[o](p) <= today for p in ambiguous)]
        if len(options) < 2:
            return options[0] if options else None
    if steps.chronology:
        fixed = [p[1] or p[2] for p in pairs if p[0] != "none" and (p[1] is None or p[2] is None or p[1] == p[2])]
        fits = []
        for o in options:
            ds = fixed + [read[o](p) for p in ambiguous]
            if (max(ds) - min(ds)).days <= parser.max_span:
                fits.append(o)
        if len(fits) == 1:
            return fits[0]
    if steps.closeness in ("last", "all"):
        sample = ambiguous[-1:] if steps.closeness == "last" else ambiguous
        distance = {o: sum(abs((today - read[o](p)).days) for p in sample) for o in options}
        if distance["as_read"] != distance["flipped"]:
            return min(options, key=distance.get)
    return None
