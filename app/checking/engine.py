"""Checking a claim sheet against its receipts — the public entry of app/checking.

    analyse_receipts(pages, ...)                 -> ReceiptFacts   (receipts.py; once per receipts document)
    find_all(sheet, facts, pin, matching)        -> [ItemFindings] (the searching; kept by the caller)
    decide(sheet, findings, facts, pin_required) -> ClaimCheck     (pairing, links, badges, totals, status)
    check_claim(...)                             both of the last two

decide(): pair the amounts with pages (assignment.py), say why each unpaired
one is not green (verdict.py), link every amount to one page (links.py),
judge each amount and page by colour rule B (badges.py), then the sums and
the four statuses. Flipping the PIN switch only calls decide() again: no
search is repeated.
"""

from __future__ import annotations

from dataclasses import replace

from app.checking.assignment import pair_items
from app.checking.badges import Judged, judge
from app.checking.findings import ItemFindings, find_item
from app.checking.links import link_pages
from app.checking.model import (CAUTION, GREEN, GREY, P_NO_RECEIPT, P_OTHER_BUYER, P_PIN, PASS, RED, REVIEW,
                                YELLOW, ClaimCheck, ItemResult, PageResult, Status)
from app.checking.receipts import ReceiptFacts
from app.checking.totals import total_status, totals
from app.checking.verdict import item_result
from app.claims import ClaimSheet
from app.matching import MatchingRules


def find_all(sheet: ClaimSheet, facts: ReceiptFacts, pin: str | None, matching: MatchingRules) -> list[ItemFindings]:
    return [find_item(item, facts, pin, matching) for item in sheet.items]


def decide(sheet: ClaimSheet, findings: list[ItemFindings], facts: ReceiptFacts, pin_required: bool) -> ClaimCheck:
    pairing = pair_items(findings, facts, pin_required)
    verdicts = [item_result(i, findings, pairing, facts, pin_required) for i in range(len(findings))]
    links = link_pages(findings, pairing, [v.page for v in verdicts], facts)
    judged, pages = judge(findings, pairing, links, facts, pin_required)
    results = [_final(v, j, links.page_of.get(i)) for i, (v, j) in enumerate(zip(verdicts, judged))]
    sums = totals(sheet, results)
    return ClaimCheck(results, pin_required, facts.pin_pages, facts.repeats, facts.unread, sums,
                      _verification(results, pages), _pin(pages, pin_required), _repeats(facts),
                      total_status(sums, results), pages)


def check_claim(sheet: ClaimSheet, facts: ReceiptFacts, pin: str | None, pin_required: bool | None,
                matching: MatchingRules) -> ClaimCheck:
    """pin_required None: the PIN scan decides (required when the PIN is on any page, D23)."""
    required = bool(pin) and (bool(facts.pin_pages) if pin_required is None else pin_required)
    return decide(sheet, find_all(sheet, facts, pin, matching), facts, required)


def _final(verdict: ItemResult, judged: Judged, page: int | None) -> ItemResult:
    """The verdict's reason and words, with the colour, page and highlights of the linked page."""
    if judged.colour == GREEN:
        status = PASS
    elif judged.colour == YELLOW and verdict.status == CAUTION:
        status = CAUTION
    else:
        status = REVIEW
    return replace(verdict, status=status, colour=judged.colour, page=page, hits=judged.hits,
                   problems=judged.problems, lines=judged.lines)


def _verification(results: list[ItemResult], pages: dict[int, PageResult]) -> Status:
    """The receipt pages that failed; amounts with no receipt counted on the small line (D38, D42)."""
    if not results:
        return Status(YELLOW, "no claimed amounts", "the claim sheet holds no claimed amount")
    colours = {r.colour for r in results} | {p.colour for p in pages.values()}
    if colours == {GREEN}:
        return Status(GREEN, "all verified", "every claimed amount matched its own receipt page")
    failing = [n for n, p in sorted(pages.items()) if p.colour != GREEN]
    missing = [r for r in results if P_NO_RECEIPT in r.problems]
    pages_text = f"p. {', '.join(map(str, failing))}" if failing else ""
    missing_text = f"{len(missing)} no receipt" if missing else ""
    details = ([f"Receipt pages to check: {', '.join(map(str, failing))}."] if failing else []) + (
        ["No receipt found for: " + "; ".join(f"{r.item.column} ({r.item.amount:,.2f})" if r.item.amount is not None
                                               else r.item.column for r in missing) + "."] if missing else [])
    return Status(RED if RED in colours else YELLOW, pages_text or missing_text, " ".join(details),
                  missing_text if pages_text else "")


def _pin(pages: dict[int, PageResult], required: bool) -> Status:
    if not required:
        return Status(GREY, "not required", "the PIN toggle is off: the company PIN is not required")
    missing = [n for n, p in sorted(pages.items()) if p.item is not None and {P_PIN, P_OTHER_BUYER} & set(p.problems)]
    if missing:
        return Status(RED, "missing", f"the company PIN is missing on page{'s' if len(missing) > 1 else ''} "
                                      f"{', '.join(map(str, missing))}")
    return Status(GREEN, "on every receipt", "the company PIN is on every receipt page linked to a claimed amount")


def _repeats(facts: ReceiptFacts) -> Status:
    if facts.repeats:
        pairs = ", ".join(f"page {later} repeats page {earlier}" for earlier, later in facts.repeats)
        return Status(RED, "p. " + ", ".join(str(later) for _, later in facts.repeats), pairs,
                      "repeats p. " + ", ".join(str(earlier) for earlier, _ in facts.repeats))
    if facts.unread:
        return Status(YELLOW, "not checked", "pages that could not be read were not compared")
    return Status(GREEN, "none", "no receipt page repeats another")
