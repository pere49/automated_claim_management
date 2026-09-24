"""One claimed amount's finding: PASS / CAUTION / REVIEW, its colour, and why in plain words.

Green (PASS): paired with a page. Red (REVIEW): one repeated receipt relied
on by two claims. Yellow otherwise, naming the nearest miss so the manual
check is quick: the page that came closest and what it lacks. CAUTION
(still yellow) marks a possible match only, or a page naming another buyer.
The detail names amounts, dates and pages for the window; it never goes to
a log or an error.
"""

from __future__ import annotations

from datetime import date

from app.checking.assignment import Pairing
from app.checking.findings import CENTS_DROPPED, EXACT_AMOUNT, POSSIBLE_AMOUNT, ItemFindings, PageFinding
from app.checking.model import (ALREADY_PAIRED, AMOUNT_UNREADABLE, CAUTION, DATE_CONTRADICTED, DATE_MISSING,
                                DATE_UNDECIDED, DATE_UNREADABLE, DOUBLE_CLAIM, GREEN, NO_DATE, NO_PIN, NOT_FOUND,
                                NOT_TOTAL, OTHER_BUYER, PAIRED, PASS, POSSIBLE_ONLY, RED, REPEAT_COPY, REVIEW,
                                YELLOW, ItemResult)
from app.checking.receipts import ReceiptFacts
from app.claims import EMPTY, UNREADABLE


def item_result(i: int, findings: list[ItemFindings], pairing: Pairing, facts: ReceiptFacts,
                pin_required: bool) -> ItemResult:
    f = findings[i]
    item = f.item
    when = pairing.date_of.get(i)
    by_page = {p.page: p for p in f.pages}

    def result(status, colour, page, reason, detail, hit_date=when):
        hits = by_page[page].hits(hit_date) if page in by_page else []
        return ItemResult(item, status, colour, page, when, reason, detail, hits)

    if i in pairing.red:
        page = pairing.page_of.get(i) or pairing.page_of.get(_partner(i, findings, pairing))
        copy = next((later for later, earlier in facts.repeat_of.items() if earlier == page), None)
        rows = sorted(findings[j].item.row for j in pairing.red
                      if findings[j].item.amount == item.amount and pairing.date_of.get(j) == when)
        return result(REVIEW, RED, page, DOUBLE_CLAIM, f"one receipt (page {page}, repeated as page {copy}) "
                      f"for two claims: rows {' and '.join(map(str, rows))}")
    if i in pairing.page_of:
        page = pairing.page_of[i]
        p = by_page[page]
        how = "amount" if p.amount == EXACT_AMOUNT else "amount (cents dropped on the sheet)"
        return result(PASS, GREEN, page, PAIRED,
                      f"{how}, date{' and company PIN' if pin_required else ''} on page {page}")
    if item.amount is None:
        return result(REVIEW, YELLOW, None, AMOUNT_UNREADABLE, f"the amount in this cell could not be read "
                      f"({item.problem})")
    with_amount = [p for p in f.pages if p.amount in (EXACT_AMOUNT, CENTS_DROPPED)]
    best = _best(with_amount) or (f.pages[0] if f.pages else None)
    best_page = best.page if best else None
    where = f"; the amount is on page {best_page}" if best_page else ""
    if item.date.how == EMPTY:
        return result(REVIEW, YELLOW, best_page, NO_DATE, f"no date on the claim sheet for this row{where}", None)
    if item.date.how == UNREADABLE:
        return result(REVIEW, YELLOW, best_page, DATE_UNREADABLE, f"the date on the claim sheet could not be read{where}",
                      None)
    if i in pairing.contradicted:
        other = next(d for d in item.date.candidates if d != item.date.value)
        page = next(p.page for p in with_amount if other in p.dates)
        return result(REVIEW, YELLOW, page, DATE_CONTRADICTED,
                      f"the sheet's date reads {_day(item.date.value)}, but the receipt with this amount (page {page}) "
                      f"is dated {_day(other)} — the sheet's date could be read either way", other)
    if when is None:
        a, b = item.date.candidates
        return result(REVIEW, YELLOW, best_page, DATE_UNDECIDED,
                      f"the date could be {_day(a)} or {_day(b)}; the receipts do not settle it{where}", None)
    if not f.pages:
        return result(REVIEW, YELLOW, None, NOT_FOUND, "this amount is not on any receipt page")
    dated = [p for p in with_amount if when in p.dates]
    if dated:
        return _dated_miss(result, dated, findings, pairing, facts, pin_required)
    if with_amount:
        p = best
        return result(REVIEW, YELLOW, p.page, DATE_MISSING,
                      f"the amount is on page {p.page}, but not the date {_day(when)}{_nearest(when, facts, p.page)}")
    p = next(p for p in f.pages if p.amount == POSSIBLE_AMOUNT) if any(
        p.amount == POSSIBLE_AMOUNT for p in f.pages) else None
    if p is not None:
        return result(CAUTION, YELLOW, p.page, POSSIBLE_ONLY,
                      f"only a possible match on page {p.page} (a decimal point the OCR could not see)")
    return result(REVIEW, YELLOW, None, NOT_FOUND, "this amount is not on any receipt page")


def _dated_miss(result, dated: list[PageFinding], findings, pairing: Pairing, facts: ReceiptFacts, pin_required: bool):
    """Pages with the amount and the date, but not paired. Where the amount is
    not printed as the total it could never pass, so that is the reason;
    otherwise the page was taken, is a repeat, names another buyer, or lacks the PIN."""
    totals = [p for p in dated if p.anchored]
    if not totals:
        p = dated[0]
        return result(REVIEW, YELLOW, p.page, NOT_TOTAL,
                      f"amount and date on page {p.page}, but the amount is not printed as the receipt's total")
    taken = pairing.taken
    for p in totals:
        if p.page in taken:
            other = findings[taken[p.page]].item
            return result(REVIEW, YELLOW, p.page, ALREADY_PAIRED,
                          f"amount and date on page {p.page}, already paired with row {other.row} ({other.column})")
    for p in totals:
        if p.page in facts.repeat_of:
            return result(REVIEW, YELLOW, p.page, REPEAT_COPY,
                          f"its receipt, page {p.page}, repeats page {facts.repeat_of[p.page]}")
    for p in totals:
        if p.page in facts.other_buyer:
            return result(CAUTION, YELLOW, p.page, OTHER_BUYER, f"page {p.page} names a different buyer's PIN")
    p = totals[0]
    return result(REVIEW, YELLOW, p.page, NO_PIN, f"amount and date on page {p.page}, but not the company PIN")


def _best(pages: list[PageFinding]) -> PageFinding | None:
    if not pages:
        return None
    return max(pages, key=lambda p: (p.anchored, p.amount == EXACT_AMOUNT, bool(p.dates), p.pin, -p.page))


def _partner(i: int, findings, pairing: Pairing) -> int:
    return next(j for j in pairing.red if j != i and findings[j].item.amount == findings[i].item.amount)


def _nearest(when: date, facts: ReceiptFacts, page: int) -> str:
    printed = facts.dates.get(page, ())
    if not printed:
        return " (no readable date on that page)"
    near = min(printed, key=lambda d: abs((d - when).days))
    days = (near - when).days
    how = "" if abs(days) > 7 else (" — one day earlier" if days == -1 else " — one day later" if days == 1
                                    else f" — {abs(days)} days {'earlier' if days < 0 else 'later'}")
    return f" (that receipt is dated {_day(near)}{how})"


def _day(d: date) -> str:
    return f"{d:%d %b %Y}"
