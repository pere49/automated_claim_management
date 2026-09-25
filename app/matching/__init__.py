"""Matching: finding a claimed date, amount and PIN in a document's text.

Public entry points:
    load_matching_rules()                       rules.py  (matching_rules.json)
    parse_typed_amount(text, rules) -> Decimal  money.py  (raises QueryError)
    normalise_pin(text) -> str                  pin_search.py
    Query, prepare_page, search_page,
    search_document -> DocumentMatches          search.py

Rules were chosen by the measured trial in tools/search_criteria_trial and
approved by the user (blueprint section 6). Every comparison is exact after
normalisation. This package imports nothing from OCR, image or window code.
"""

from app.matching.found import CORRECTED, EXACT, POSSIBLE
from app.matching.money import QueryError, parse_typed_amount
from app.matching.pin_search import normalise_pin
from app.matching.rules import MatchingRules, load_matching_rules
from app.matching.search import (AMOUNT, DATE, KEYS, PIN, DocumentMatches, Hit, PageMatches, PreparedPage, Query,
                                 prepare_page, search_document, search_page)

__all__ = ["AMOUNT", "CORRECTED", "DATE", "EXACT", "KEYS", "PIN", "POSSIBLE", "DocumentMatches", "Hit",
           "MatchingRules", "PageMatches", "PreparedPage", "Query", "QueryError", "load_matching_rules",
           "normalise_pin", "parse_typed_amount", "prepare_page", "search_document", "search_page"]
