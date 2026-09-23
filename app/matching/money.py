"""Amounts: parsing a typed amount exactly, and the printed forms of a value.

parse_typed_amount("1,200")   -> Decimal("1200.00")
amount_forms(Decimal("1200"))  -> with cents {"1,200.00", "1.200.00", "1200.00", ...}
                                  without cents {"1,200", "1200", ...}

Money is always an exact Decimal, never a float. An ambiguous typed amount
("1.200": 1.2 or 1200?) is refused, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.matching.rules import MatchingRules

_GROUPED = re.compile(r"\d{1,3}(?:[,' ]\d{3})+(?:\.\d{1,2})?")
_PLAIN = re.compile(r"\d+(?:\.\d{1,2})?")


class QueryError(ValueError):
    """A search value the officer typed cannot be used. The message says why,
    in plain words, and never repeats the value itself."""


@dataclass(frozen=True)
class AmountForms:
    with_cents: frozenset[str]
    without_cents: frozenset[str]  # empty unless the amount is whole


def parse_typed_amount(text: str, rules: MatchingRules) -> Decimal:
    """The amount as an exact Decimal with two places. Raises QueryError."""
    t = " ".join(text.split())
    for word in sorted(rules.currency_words, key=len, reverse=True):
        if t.lower().startswith(word.lower()):
            t = t[len(word):].strip()
            break
    for word in sorted(rules.currency_words, key=len, reverse=True):
        if t.lower().endswith(word.lower()):
            t = t[: -len(word)].strip()
            break
    for end in rules.no_cents_endings:
        if t.endswith(end):
            t = t[: -len(end)].strip()
    if not t:
        raise QueryError("the amount is empty")
    if t.startswith("-") or t.startswith("("):
        raise QueryError("the amount must be greater than zero")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t) or re.fullmatch(r"\d{1,3}(?:\.\d{3})+\.\d{1,2}", t):
        raise QueryError("a point between thousands is ambiguous (it could mean a small amount or thousands): "
                         "use a comma for thousands and a point only before the cents")
    if re.fullmatch(r"\d+,\d{1,2}", t):
        raise QueryError("use a point, not a comma, before the cents")
    if not (_GROUPED.fullmatch(t) or _PLAIN.fullmatch(t)):
        raise QueryError("the amount must be digits, optionally with a comma for thousands and a point "
                         "before one or two decimal digits")
    try:
        value = Decimal(re.sub(r"[,' ]", "", t)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise QueryError("the amount could not be read as a number") from exc
    if value <= 0:
        raise QueryError("the amount must be greater than zero")
    return value


def amount_forms(value: Decimal, rules: MatchingRules) -> AmountForms:
    """Every way this amount may be printed."""
    whole, cents = f"{value:.2f}".split(".")
    grouped = f"{int(whole):,}"
    with_cents: set[str] = set()
    without_cents: set[str] = set()
    for sep in rules.thousands_separators:
        g = grouped.replace(",", sep)
        with_cents.add(f"{g}.{cents}")
        if rules.one_decimal_forms and cents[1] == "0":
            with_cents.add(f"{g}.{cents[0]}")
        if cents == "00":
            without_cents.add(g)
    return AmountForms(frozenset(with_cents), frozenset(without_cents))
