"""Linking each claimed amount to one receipt page, each page to at most one amount (D35).

In this order, a page once linked never linked again:
1. The page the amount was paired with (assignment.py): its total, its date
   and (when required) the company PIN.
2. One receipt claimed twice (D29): the second claim goes to the repeated copy.
3. The page printing the amount: the one the finding showed as the nearest
   miss (verdict.py) when still free, else the best other free page printing it.
4. For an amount on no free page: the free page printing its date — only
   when that page is the only free page with the date and the amount is the
   only unlinked one with it (owner, "2a": never a guess). Repeated copies
   are never linked this way.
An amount left unlinked has "No receipt found".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from app.checking.assignment import Pairing
from app.checking.findings import EXACT_AMOUNT, POSSIBLE_AMOUNT, ItemFindings, PageFinding
from app.checking.receipts import ReceiptFacts

PAIRED_LINK, REPEAT_LINK, AMOUNT_LINK, DATE_LINK = "paired", "repeat", "amount", "date"


@dataclass
class Links:
    page_of: dict[int, int] = field(default_factory=dict)       # item index -> linked page
    how: dict[int, str] = field(default_factory=dict)           # item index -> *_LINK
    date_hits: dict[int, list] = field(default_factory=dict)    # item index -> date Hits on a date-linked page

    @property
    def item_of(self) -> dict[int, int]:
        return {page: i for i, page in self.page_of.items()}


def link_pages(findings: list[ItemFindings], pairing: Pairing, nearest: list[int | None],
               facts: ReceiptFacts) -> Links:
    """nearest: per amount, the page its finding showed (verdict.py)."""
    links = Links()
    used: set[int] = set()

    def link(i: int, page: int, how: str) -> None:
        links.page_of[i], links.how[i] = page, how
        used.add(page)

    for i, page in sorted(pairing.page_of.items()):
        link(i, page, PAIRED_LINK)
    repeat_of = facts.repeat_of
    for i in sorted(pairing.red - set(pairing.page_of)):
        partners = [pairing.page_of[j] for j in pairing.red if j in pairing.page_of
                    and findings[j].item.amount == findings[i].item.amount]
        copy = next((later for later, earlier in sorted(repeat_of.items())
                     if earlier in partners and later not in used), None)
        if copy is not None:
            link(i, copy, REPEAT_LINK)
    for i, f in enumerate(findings):
        if i in links.page_of:
            continue
        free = [p for p in f.pages if p.page not in used and p.amount is not None]
        if free:
            chosen = next((p for p in free if p.page == nearest[i]), None) or max(free, key=_rank)
            link(i, chosen.page, AMOUNT_LINK)

    wanted: dict[int, tuple[list[int], dict[int, list]]] = {}
    for i, f in enumerate(findings):
        if i in links.page_of:
            continue
        days = _days(f, pairing.date_of.get(i))
        pages, hits = [], {}
        for n in sorted(facts.pages):
            if n in used or n in repeat_of:
                continue
            found = [h for d in days for h in facts.date_hits(n, d)]
            if found:
                pages.append(n)
                hits[n] = found
        wanted[i] = (pages, hits)
    claimants = Counter(n for pages, _ in wanted.values() for n in pages)
    for i, (pages, hits) in wanted.items():
        if len(pages) == 1 and claimants[pages[0]] == 1:
            link(i, pages[0], DATE_LINK)
            links.date_hits[i] = hits[pages[0]]
    return links


def _rank(p: PageFinding) -> tuple:
    return bool(p.dates), p.anchored, p.amount == EXACT_AMOUNT, p.amount != POSSIBLE_AMOUNT, p.pin, -p.page


def _days(f: ItemFindings, when: date | None) -> tuple[date, ...]:
    if when is not None:
        return (when,)
    reading = f.item.date
    if reading.value is not None:
        return (reading.value,)
    return tuple(reading.candidates)
