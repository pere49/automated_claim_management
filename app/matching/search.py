"""Searching a document for a claimed date, amount and PIN.

    rules = load_matching_rules()
    query = Query(date=date(2026, 8, 12), amount=Decimal("760.00"), pin="A012345678Z")
    page = prepare_page(rows, rules)        # once per page (rows: app/layout TextRows)
    result = search_document({1: page, 2: ...}, query, rules)
    result.best_page, result.pages_with("amount"), result.places()

Every page is searched; one page that cannot be searched is recorded on its
own PageMatches.error and the rest carry on. Nothing here reads OCR, images
or the window: a page is its printed rows, and each match names the row
segments it was found in (their .source is the caller's own object, used for
highlighting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from app.errors import StageError
from app.matching.amount_search import amount_cores, find_amount
from app.matching.date_search import find_date, text_cores
from app.matching.dates import DateForms, date_forms
from app.matching.found import CORRECTED, EXACT, POSSIBLE, Found
from app.matching.money import AmountForms, amount_forms
from app.matching.pin_search import find_pin, normalise_pin
from app.matching.rules import MatchingRules
from app.matching.tokens import Token, row_tokens, split_fused

AMOUNT, DATE, PIN = "amount", "date", "pin"
KEYS = (DATE, AMOUNT, PIN)


@dataclass(frozen=True)
class Query:
    date: date | None = None
    amount: Decimal | None = None
    pin: str | None = None

    @property
    def keys(self) -> tuple[str, ...]:
        values = {DATE: self.date, AMOUNT: self.amount, PIN: self.pin}
        return tuple(k for k in KEYS if values[k] not in (None, ""))


@dataclass
class PreparedPage:
    """One page's text, tokenised and trimmed once, reused for every search."""
    rows: list[Any]                       # app/layout TextRows
    plain: list[list[Token]]              # tokens without joining (dates, PINs)
    amounts: list[list[Token]]            # decimal tails joined, fused words split (amounts)
    plain_cores: list[list[str]]          # label-trimmed, lower case
    amount_cores: list[list[tuple[str, bool]]]   # trimmed for amounts; currency attached or not


@dataclass(frozen=True)
class _Forms:
    """A query's printed forms, built once per search."""
    amount: AmountForms | None
    date: DateForms | None
    pin: str | None


@dataclass(frozen=True)
class Hit:
    key: str                              # AMOUNT | DATE | PIN
    strength: str                         # EXACT | CORRECTED | POSSIBLE
    row: int
    segments: tuple[Any, ...]             # layout Segments holding the value
    neighbours: tuple[Any, ...]           # up to rules.neighbours_each_side segments each side, same row


@dataclass
class PageMatches:
    page: int
    hits: list[Hit] = field(default_factory=list)
    error: StageError | None = None

    def found(self, key: str) -> bool:
        return any(h.key == key and h.strength in (EXACT, CORRECTED) for h in self.hits)

    def possible(self, key: str) -> bool:
        return not self.found(key) and any(h.key == key and h.strength == POSSIBLE for h in self.hits)


@dataclass
class DocumentMatches:
    query: Query
    pages: dict[int, PageMatches]         # every page searched, by page number

    def pages_with(self, key: str) -> list[int]:
        return sorted(n for n, p in self.pages.items() if p.found(key))

    def pages_possible(self, key: str) -> list[int]:
        return sorted(n for n, p in self.pages.items() if p.possible(key))

    def corrected(self, key: str) -> bool:
        """Some find of this key needed an OCR character correction."""
        return any(h.key == key and h.strength == CORRECTED for p in self.pages.values() for h in p.hits)

    def places(self, key: str | None = None) -> list[tuple[int, Hit]]:
        """Every hit, in page then row order (for "next match")."""
        out = [(n, h) for n in sorted(self.pages) for h in sorted(self.pages[n].hits, key=lambda h: h.row)
               if key is None or h.key == key]
        return out

    def complete_pages(self) -> list[int]:
        """Pages where every searched key is found."""
        keys = self.query.keys
        return sorted(n for n, p in self.pages.items() if keys and all(p.found(k) for k in keys))

    @property
    def best_page(self) -> int | None:
        """The page to show: all keys found; else the most keys found, then
        the most possible; the lowest page number on a tie. None if nothing."""
        keys = self.query.keys
        scored = [(sum(p.found(k) for k in keys), sum(p.possible(k) for k in keys), -n)
                  for n, p in self.pages.items()]
        best = max(scored, default=None)
        return -best[2] if best and (best[0] or best[1]) else None

    @property
    def errors(self) -> list[StageError]:
        return [p.error for p in self.pages.values() if p.error is not None]


# ---------------------------------------------------------------- public


def prepare_page(rows: list[Any], rules: MatchingRules) -> PreparedPage:
    """Tokenise a page's rows once. Rows are app/layout TextRows."""
    plain = [row_tokens(r.segments, False, rules.tail_join_gap_per_height) for r in rows]
    amounts = [split_fused(row_tokens(r.segments, True, rules.tail_join_gap_per_height)) for r in rows]
    return PreparedPage(rows, plain, amounts, text_cores(plain), amount_cores(amounts, rules))


def search_page(page: PreparedPage, query: Query, rules: MatchingRules, forms: _Forms | None = None) -> list[Hit]:
    """Every place on the page where a searched key is found."""
    forms = forms or _forms(query, rules)
    hits: list[Hit] = []
    if forms.date is not None:
        hits += _hits(DATE, find_date(forms.date, page.plain, page.plain_cores), page, rules)
    if forms.amount is not None:
        hits += _hits(AMOUNT, find_amount(forms.amount, page.amounts, page.amount_cores, rules), page, rules)
    if forms.pin:
        hits += _hits(PIN, find_pin(forms.pin, page.plain, page.plain_cores, rules), page, rules)
    return hits


def search_document(pages: Mapping[int, PreparedPage], query: Query, rules: MatchingRules) -> DocumentMatches:
    """Search every page. A page that fails is recorded, never raised."""
    result = DocumentMatches(query, {})
    forms = _forms(query, rules)
    for number in sorted(pages):
        try:
            result.pages[number] = PageMatches(number, search_page(pages[number], query, rules, forms))
        except Exception as exc:
            result.pages[number] = PageMatches(number, error=StageError(
                "matching", "this page could not be searched", page=number, cause=exc))
    return result


# ---------------------------------------------------------------- internal


def _forms(query: Query, rules: MatchingRules) -> _Forms:
    return _Forms(amount_forms(query.amount, rules) if query.amount is not None else None,
                  date_forms(query.date, rules) if query.date is not None else None,
                  normalise_pin(query.pin) if query.pin else None)


def _hits(key: str, found: list[Found], page: PreparedPage, rules: MatchingRules) -> list[Hit]:
    out = []
    n = rules.neighbours_each_side
    for f in found:
        segs = page.rows[f.row].segments
        first, last = min(f.segments), max(f.segments)
        around = [i for i in range(max(0, first - n), min(len(segs), last + n + 1)) if i not in f.segments]
        out.append(Hit(key, f.strength, f.row, tuple(segs[i] for i in f.segments), tuple(segs[i] for i in around)))
    return out
