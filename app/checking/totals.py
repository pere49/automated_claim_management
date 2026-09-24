"""Grand totals (D30), exact to the cent.

Grand total 1 — the sheet's own arithmetic: every row's amounts x its Rate,
added up, against the grand Total; the rows whose own Total disagrees with
their amounts x Rate are named (pointing at a typing slip, or an OCR misread
on a scanned sheet). Grand total 2 — the green amounts x Rate against the
grand Total: equal only when every amount was verified.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.checking.model import GREEN, ItemResult, Totals
from app.claims import ClaimSheet

CENT = Decimal("0.01")


def totals(sheet: ClaimSheet, results: list[ItemResult]) -> Totals:
    claimed = Decimal(0)
    disagreeing = []
    for row in sheet.rows:
        value = _cents(sum((it.amount for it in row.items if it.amount is not None), Decimal(0)) * row.rate)
        claimed += value
        unreadable = any(it.amount is None for it in row.items)
        if unreadable or (row.total is not None and row.total != value):
            disagreeing.append(row.row)
    approved = sum((_cents(r.item.amount * r.item.rate) for r in results if r.colour == GREEN and r.item.amount),
                   Decimal(0))
    grand = sheet.grand_total
    return Totals(grand, claimed, None if grand is None else claimed == grand, disagreeing, approved,
                  None if grand is None else approved == grand)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
