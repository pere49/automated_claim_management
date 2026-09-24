"""Checking a claim sheet against its receipts — the public entry of app/checking.

    analyse_receipts(pages, ...)                 -> ReceiptFacts   (receipts.py; once per receipts document)
    find_all(sheet, facts, pin, matching)        -> [ItemFindings] (the searching; kept by the caller)
    decide(sheet, findings, facts, pin_required) -> ClaimCheck     (pairing, verdicts, totals, status)
    check_claim(...)                             both of the last two

Flipping the PIN switch only calls decide() again: no search is repeated.
"""

from __future__ import annotations

from app.checking.assignment import pair_items
from app.checking.findings import ItemFindings, find_item
from app.checking.model import (DOUBLE_CLAIM, GREEN, GREY, NO_PIN, RED, YELLOW, ClaimCheck, ItemResult, Status,
                                Totals)
from app.checking.receipts import ReceiptFacts
from app.checking.totals import totals
from app.checking.verdict import item_result
from app.claims import ClaimSheet
from app.matching import MatchingRules


def find_all(sheet: ClaimSheet, facts: ReceiptFacts, pin: str | None, matching: MatchingRules) -> list[ItemFindings]:
    return [find_item(item, facts, pin, matching) for item in sheet.items]


def decide(sheet: ClaimSheet, findings: list[ItemFindings], facts: ReceiptFacts, pin_required: bool) -> ClaimCheck:
    pairing = pair_items(findings, facts, pin_required)
    results = [item_result(i, findings, pairing, facts, pin_required) for i in range(len(findings))]
    sums = totals(sheet, results)
    return ClaimCheck(results, pin_required, facts.pin_pages, facts.repeats, facts.unread, sums,
                      _verification(results, sums, facts), _pin(results, pin_required, facts),
                      _repeats(results, facts))


def check_claim(sheet: ClaimSheet, facts: ReceiptFacts, pin: str | None, pin_required: bool | None,
                matching: MatchingRules) -> ClaimCheck:
    """pin_required None: the PIN scan decides (required when the PIN is on any page, D23)."""
    required = bool(pin) and (bool(facts.pin_pages) if pin_required is None else pin_required)
    return decide(sheet, find_all(sheet, facts, pin, matching), facts, required)


def _verification(results: list[ItemResult], sums: Totals, facts: ReceiptFacts) -> Status:
    to_check = sum(1 for r in results if r.colour != GREEN)
    if not results:
        return Status(YELLOW, "no claimed amounts on the sheet")
    if to_check == 0 and sums.grand_total_2 and not facts.unread:
        return Status(GREEN, "all verified")
    notes = [f"{to_check} to check"] if to_check else []
    if sums.grand_total_2 is not True:
        notes.append("Grand total 2 does not match")
    if facts.unread:
        notes.append(f"{len(facts.unread)} receipt page{'s' if len(facts.unread) > 1 else ''} unread")
    return Status(YELLOW, "manual check required: " + ", ".join(notes))


def _pin(results: list[ItemResult], required: bool, facts: ReceiptFacts) -> Status:
    if not required:
        return Status(GREY, "not required")
    missing = sum(1 for r in results if r.reason == NO_PIN)
    if missing:
        return Status(RED, f"not detected on {missing} matched receipt{'s' if missing > 1 else ''}")
    return Status(GREEN, "detected on every paired receipt")


def _repeats(results: list[ItemResult], facts: ReceiptFacts) -> Status:
    pairs = ", ".join(f"page {later} repeats page {earlier}" for earlier, later in facts.repeats)
    if any(r.reason == DOUBLE_CLAIM for r in results):
        return Status(RED, f"{pairs} — one receipt, two claims")
    if facts.repeats:
        return Status(YELLOW, f"{pairs} (claimed once)")
    if facts.unread:
        return Status(YELLOW, "none found, but unread pages were not checked")
    return Status(GREEN, "none")
