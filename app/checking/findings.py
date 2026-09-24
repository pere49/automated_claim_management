"""What each receipt page that can hold a claimed amount shows about it.

For one claimed amount, only the pages printing one of its forms are
searched (ReceiptFacts.pages_for). On each: is the amount there — exactly,
with its cents dropped (D27: a claim of 500 for 500.34 printed), or only as a
possible match (a faded decimal point, never a pass) — is it printed as the
receipt's total (D33), which of the claim's possible dates are printed, and
is the company PIN there. The hits are kept for highlighting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.checking.page_facts import CENTS, printed_as_total
from app.checking.receipts import ReceiptFacts
from app.claims import ClaimItem
from app.matching import AMOUNT, DATE, EXACT, PIN, POSSIBLE, Hit, MatchingRules, Query, amount_forms, make_hit, search_page

EXACT_AMOUNT, CENTS_DROPPED, POSSIBLE_AMOUNT = "exact", "cents dropped", "possible"


@dataclass
class PageFinding:
    page: int
    amount: str | None                    # EXACT_AMOUNT | CENTS_DROPPED | POSSIBLE_AMOUNT | None
    anchored: bool                        # printed as the receipt's total
    dates: set[date]                      # which of the claim's possible dates the page prints
    pin: bool
    amount_hits: list[Hit] = field(default_factory=list)
    date_hits: dict[date, list[Hit]] = field(default_factory=dict)
    pin_hits: list[Hit] = field(default_factory=list)

    def hits(self, when: date | None) -> list[Hit]:
        return self.amount_hits + (self.date_hits.get(when, []) if when else []) + self.pin_hits


@dataclass
class ItemFindings:
    item: ClaimItem
    dates: tuple[date, ...]               # the dates searched: the one read, or both possible readings
    pages: list[PageFinding]              # in page order


def find_item(item: ClaimItem, facts: ReceiptFacts, pin: str | None, matching: MatchingRules,
              look_above: bool | None = None) -> ItemFindings:
    """look_above: None = as configured (a trial may compare both)."""
    if item.amount is None:
        return ItemFindings(item, (), [])
    above = facts.look_above if look_above is None else look_above
    reading = item.date
    dates = reading.candidates if len(reading.candidates) == 2 else ((reading.value,) if reading.value else ())
    pages = []
    for n in facts.pages_for(item.amount, matching):
        page = facts.pages[n]
        found = search_page(page, Query(amount=item.amount, pin=pin), matching)
        exact = [h for h in found if h.key == AMOUNT and h.strength != POSSIBLE]
        possible = [h for h in found if h.key == AMOUNT and h.strength == POSSIBLE]
        dropped = [] if exact else cents_dropped_hits(page, item, matching)
        kind, hits = ((EXACT_AMOUNT, exact) if exact else (CENTS_DROPPED, dropped) if dropped
                      else (POSSIBLE_AMOUNT, possible) if possible else (None, []))
        date_hits = {d: [h for h in search_page(page, Query(date=d), matching) if h.key == DATE] for d in dates}
        totals = [h for h in hits if kind in (EXACT_AMOUNT, CENTS_DROPPED) and printed_as_total(h, facts.totals[n], above)]
        anchored = bool(totals)
        hits = totals + [h for h in hits if h not in totals]      # the total first: the window scrolls to it
        pin_hits = [h for h in found if h.key == PIN]
        pages.append(PageFinding(n, kind, anchored, {d for d, hs in date_hits.items() if hs}, bool(pin_hits),
                                 hits, date_hits, pin_hits))
    return ItemFindings(item, dates, pages)


def cents_dropped_hits(page, item: ClaimItem, matching: MatchingRules) -> list[Hit]:
    """Amounts printed with cents whose whole part is the claimed whole amount (never upward)."""
    whole = amount_forms(item.amount, matching).without_cents
    if not whole:
        return []
    hits = []
    for r, (tokens, cores) in enumerate(zip(page.amounts, page.amount_cores)):
        for token, (core, _) in zip(tokens, cores):
            m = CENTS.fullmatch(core)
            if m and m.group(2) != "00" and m.group(1) in whole:
                hits.append(make_hit(page, AMOUNT, EXACT, r, token.segments, matching))
    return hits
