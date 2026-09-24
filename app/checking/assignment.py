"""Pairing claimed amounts with receipt pages (D28, D29, D26's receipt step).

1. The date used. A date the sheet decided is used — unless it could be read
   either way and the receipts carrying the amount show only the other
   reading (the guard: the row goes to the officer). A date the sheet left
   open is settled when exactly one of its two readings is printed on a page
   carrying the amount.
2. Two passes over the claims in sheet order — every exact amount first,
   then the amounts matched with their cents dropped — so a claim of 500
   cannot take the 500.34 receipt a claim of 500.34 needs. A page qualifies
   when it prints the amount as its total, the date, and (when required) the
   company PIN, names no other buyer, is not the later copy of a repeated
   page, and is not already paired. The first page that qualifies is paired
   with the claim and leaves every later search (the owner's rule).
3. One receipt for two claims: a claim left unpaired whose amount and date are
   on the later copy of a page paired with a claim of the same amount and
   date — both are red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.checking.findings import CENTS_DROPPED, EXACT_AMOUNT, ItemFindings
from app.checking.receipts import ReceiptFacts


@dataclass
class Pairing:
    page_of: dict[int, int] = field(default_factory=dict)      # item index -> paired page
    date_of: dict[int, date] = field(default_factory=dict)     # item index -> the date used
    red: set[int] = field(default_factory=set)
    contradicted: set[int] = field(default_factory=set)

    @property
    def taken(self) -> dict[int, int]:
        return {page: i for i, page in self.page_of.items()}


def pair_items(findings: list[ItemFindings], facts: ReceiptFacts, pin_required: bool) -> Pairing:
    pairing = Pairing()
    for i, f in enumerate(findings):
        _settle_date(i, f, pairing)
    repeat_of = facts.repeat_of
    taken: dict[int, int] = {}
    for kind in (EXACT_AMOUNT, CENTS_DROPPED):
        for i, f in enumerate(findings):
            when = pairing.date_of.get(i)
            if i in pairing.page_of or when is None:
                continue
            for p in f.pages:
                if (p.amount == kind and p.anchored and when in p.dates and (p.pin or not pin_required)
                        and p.page not in taken and p.page not in repeat_of and p.page not in facts.other_buyer):
                    taken[p.page] = i
                    pairing.page_of[i] = p.page
                    break
    for i, f in enumerate(findings):
        when = pairing.date_of.get(i)
        if i in pairing.page_of or when is None:
            continue
        for p in f.pages:
            j = taken.get(repeat_of.get(p.page))
            if (p.page in repeat_of and p.amount in (EXACT_AMOUNT, CENTS_DROPPED) and when in p.dates and j is not None
                    and findings[j].item.amount == f.item.amount and pairing.date_of.get(j) == when):
                pairing.red |= {i, j}
    return pairing


def _settle_date(i: int, f: ItemFindings, pairing: Pairing) -> None:
    reading = f.item.date
    with_amount = [p for p in f.pages if p.amount in (EXACT_AMOUNT, CENTS_DROPPED)]
    if reading.value is not None:
        if len(reading.candidates) == 2:
            other = next(d for d in reading.candidates if d != reading.value)
            if not any(reading.value in p.dates for p in with_amount) and any(other in p.dates for p in with_amount):
                pairing.contradicted.add(i)
                return
        pairing.date_of[i] = reading.value
    elif reading.open:
        seen = {d for p in with_amount for d in p.dates}
        if len(seen) == 1:
            pairing.date_of[i] = seen.pop()
