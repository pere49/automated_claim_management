"""Claim-sheet amounts: one cell -> an exact Decimal, or a plain reason why not.

Excel gives numbers as int or float; a float is converted through its
shortest exact text (2406.94 -> "2406.94"), never through binary arithmetic.
A typed amount with more than two decimals is not rounded silently: it is
reported. Sums Excel calculated (a Total) carry float noise
(4340.9400000000005) and are taken to the cent. PDF and scanned sheets give
text ("1,060.00", "-" for zero). An empty cell, a dash or zero means nothing
was claimed.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.claims.rules import ClaimRules

CENT = Decimal("0.01")
_NOISE = Decimal("0.000001")
_PLAIN = re.compile(r"\d+(?:\.\d{1,2})?")
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?")


def read_amount(value: object, rules: ClaimRules, calculated: bool = False) -> tuple[Decimal | None, str | None]:
    """(amount, problem). (None, None) when nothing is claimed in the cell.
    `calculated`: a sum Excel worked out (float noise is taken to the cent)."""
    if value is None or isinstance(value, bool):
        return None, None if value is None else "not an amount"
    if isinstance(value, date):
        return None, "a date where an amount belongs"
    if isinstance(value, int):
        return _checked(Decimal(value))
    if isinstance(value, float):
        exact = Decimal(repr(value))
        rounded = exact.quantize(CENT)
        if exact != rounded:
            if not (calculated and abs(exact - rounded) < _NOISE):
                return None, "the amount has more than two decimals"
        return _checked(rounded)
    text = " ".join(str(value).split())
    if not text or text in rules.empty_marks:
        return None, None
    words = text.split()
    if len(words) == 2 and words[0].upper() in rules.currency_codes:
        text = words[1]
    elif len(words) == 2 and words[1].upper() in rules.currency_codes:
        text = words[0]
    if text.startswith("-") or text.startswith("("):
        return None, "a negative amount"
    if not (_PLAIN.fullmatch(text) or _GROUPED.fullmatch(text)):
        return None, "not a number"
    try:
        return _checked(Decimal(text.replace(",", "")))
    except InvalidOperation:
        return None, "not a number"


def read_rate(value: object, rules: ClaimRules) -> tuple[Decimal, str | None]:
    """The row's Rate: blank or zero counts as 1 (as the sheet's own formulas do)."""
    rate, problem = read_amount(value, rules, calculated=True)
    if problem:
        return Decimal(1), "the Rate could not be read, so 1 was used"
    return (rate if rate else Decimal(1)), None


def _checked(value: Decimal) -> tuple[Decimal | None, str | None]:
    if value < 0:
        return None, "a negative amount"
    if value == 0:
        return None, None
    return value.quantize(CENT), None
