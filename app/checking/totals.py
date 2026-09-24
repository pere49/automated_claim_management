"""The sums (D30) and the one Total status (D37), exact to the cent.

The sheet's own arithmetic: every row's amounts x its Rate, added up (A),
against the Total written on the sheet (T); the rows whose own Total
disagrees with their amounts x Rate are named (a typing slip, or an OCR
misread on a scanned sheet). The verified amounts: the green ones x Rate (V).

Total status (owner, D37; shown as TOTAL GRAND, D42): every amount verified
(A = V) and A = T -> green "Total matched"; every amount verified but the
sheet's arithmetic wrong -> yellow "Excel mistake"; any amount not verified
-> red "Not matched". Derived: no Total on the sheet -> yellow "No total"
when every amount is verified. The small line under it gives the figures:
"4,570.00 of 4,900.00" (verified of the sheet's Total), "amounts 4,900.00 ·
sheet 5,000.00", "4,900.00", "amounts 4,900.00".
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.checking.model import GREEN, RED, YELLOW, ItemResult, Status, Totals
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


def total_status(t: Totals, results: list[ItemResult]) -> Status:
    grand = f"{t.grand_total:,.2f}" if t.grand_total is not None else "none"
    rows = (f"; rows whose own Total does not add up: {', '.join(map(str, t.rows_disagreeing))}"
            if t.rows_disagreeing else "")
    detail = f"Amounts on the sheet {t.claimed:,.2f} · verified {t.approved:,.2f} · Total on the sheet {grand}{rows}"
    if not results or any(r.colour != GREEN for r in results):
        whole = t.grand_total if t.grand_total is not None else t.claimed
        return Status(RED, "Not matched", detail, f"{t.approved:,.2f} of {whole:,.2f}")
    if t.grand_total is None:
        return Status(YELLOW, "No total", detail, f"amounts {t.claimed:,.2f}")
    if t.claimed != t.grand_total or t.rows_disagreeing:
        return Status(YELLOW, "Excel mistake", detail, f"amounts {t.claimed:,.2f} · sheet {t.grand_total:,.2f}")
    return Status(GREEN, "Total matched", detail, f"{t.grand_total:,.2f}")
