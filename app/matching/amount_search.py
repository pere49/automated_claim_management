"""Finding a claimed amount on one page (trial winner A9, join at decimal tails).

A token matches when, after trimming what belongs to the printer rather than
the value (a leading mark such as ERCA's "*", an attached currency word, a
"/=" ending, one tax-code letter, sentence punctuation), it equals one of
the amount's printed forms.
  with cents     matches on its own
  without cents  only with a currency word or "/=" attached or right beside
                 it, or at the end of a total line ("TOTAL 1,200")
Faded decimal point ("430 00 KSh"): a separate repair, reported POSSIBLE.

A token's trimmed core does not depend on the amount searched, so it is
computed once per page (amount_cores) and each search is set lookups.
"""

from __future__ import annotations

import re

from app.matching.found import EXACT, POSSIBLE, Found
from app.matching.money import AmountForms
from app.matching.rules import MatchingRules
from app.matching.tokens import Token

_CENTS_AT_END = re.compile(r"\d[.,]\d{2}$")
_NUMBER = re.compile(r"\d[\d,]*")
_TWO_DIGITS = re.compile(r"\d{2}")

Core = tuple[str, bool]  # trimmed token, and whether a currency word / no-cents ending was attached


def amount_cores(rows: list[list[Token]], rules: MatchingRules) -> list[list[Core]]:
    """The trimmed core of every token (once per page)."""
    return [[trim(t.text, rules) for t in tokens] for tokens in rows]


def find_amount(forms: AmountForms, rows: list[list[Token]], cores: list[list[Core]],
                rules: MatchingRules) -> list[Found]:
    """Every place the amount is printed. `rows` are fused-split tokens with
    decimal tails joined; `cores` are amount_cores(rows)."""
    found: list[Found] = []
    for r, (tokens, row_cores) in enumerate(zip(rows, cores)):
        texts = None
        exact_segments: set[int] = set()
        for i, (tok, (core, attached)) in enumerate(zip(tokens, row_cores)):
            if core in forms.with_cents:
                hit = True
            elif core in forms.without_cents:
                texts = texts or [t.text for t in tokens]
                hit = _no_cents_counts(texts, i, attached, rules)
            else:
                continue
            if hit:
                found.append(Found(r, tok.segments, EXACT))
                exact_segments.update(tok.segments)
        for segments, text in _faded(tokens, rules):
            if not exact_segments.intersection(segments) and trim(text, rules)[0] in forms.with_cents:
                found.append(Found(r, segments, POSSIBLE))
    return found


def trim(token: str, rules: MatchingRules) -> Core:
    """The token's core, and whether a currency word or no-cents ending was attached."""
    if not any(c.isdigit() for c in token):
        return token, False  # every printed form holds a digit: nothing to trim
    t, attached = token, False
    while t and t[0] in rules.amount_prefix_marks:
        t = t[1:]
    while t and t[-1] in ".,;:" and not _CENTS_AT_END.search(t):
        t = t[:-1]
    for end in rules.no_cents_endings:
        if t.endswith(end):
            t, attached = t[: -len(end)], True
    low = t.lower()
    for cur in rules.currency_longest_first:
        if low.startswith(cur) and t[len(cur):len(cur) + 1].isdigit():
            t, low, attached = t[len(cur):], low[len(cur):], True
            break
    for cur in rules.currency_longest_first:
        if low.endswith(cur) and t[: -len(cur)][-1:].isdigit():
            t, attached = t[: -len(cur)], True
            break
    if len(t) > 1 and t[-1] in rules.tax_code_letters and t[-2].isdigit():
        t = t[:-1]
    return t, attached


def _is_currency(text: str, rules: MatchingRules) -> bool:
    return text.strip(".,:;").lower() in rules.currency_lower


def _no_cents_counts(texts: list[str], i: int, attached: bool, rules: MatchingRules) -> bool:
    after = texts[i + 1] if i + 1 < len(texts) else None
    if attached or (i > 0 and _is_currency(texts[i - 1], rules)) or (after is not None and _is_currency(after, rules)):
        return True
    return after is None and _label_before(texts, i, rules)


def _label_before(texts: list[str], i: int, rules: MatchingRules) -> bool:
    return any(i - n >= 0 and " ".join(texts[i - n:i]).lower().rstrip(":") in rules.total_labels for n in (1, 2, 3))


def _faded(tokens: list[Token], rules: MatchingRules) -> list[tuple[tuple[int, ...], str]]:
    """Number, exactly two digits, currency word: a decimal point OCR could not see."""
    out = []
    for i in range(len(tokens) - 2):
        a, b, c = tokens[i], tokens[i + 1], tokens[i + 2]
        if _TWO_DIGITS.fullmatch(b.text) and _NUMBER.fullmatch(a.text) and _is_currency(c.text, rules):
            out.append((tuple(sorted(set(a.segments) | set(b.segments))), f"{a.text}.{b.text}"))
    return out
