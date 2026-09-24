"""Matching: finding a claimed date, amount and PIN in a document's text.

Public entry points:
    load_matching_rules()                       rules.py  (matching_rules.json)
    parse_typed_amount(text, rules) -> Decimal  money.py  (raises QueryError)
    normalise_pin(text) -> str                  pin_search.py
    Query, prepare_page, search_page,
    search_document -> DocumentMatches          search.py
    amount_texts, make_hit                      search.py  (for indexes and extra hits, Stage C)
    amount_forms                                money.py
    pin_matches, is_pin_shaped                  pin_search.py

Rules were chosen by the measured trial in tools/search_criteria_trial and
approved by the user (blueprint section 6). Every comparison is exact after
normalisation. This package imports nothing from OCR, image or window code.
"""

from app.matching.found import CORRECTED, EXACT, POSSIBLE
from app.matching.money import QueryError, parse_typed_amount
from app.matching.money import AmountForms, amount_forms
from app.matching.pin_search import is_pin_shaped, normalise_pin, pin_matches
from app.matching.rules import MatchingRules, load_matching_rules
from app.matching.search import (AMOUNT, DATE, KEYS, PIN, DocumentMatches, Hit, PageMatches, PreparedPage, Query,
                                 amount_texts, make_hit, prepare_page, search_document, search_page)

__all__ = ["AMOUNT", "CORRECTED", "DATE", "EXACT", "KEYS", "PIN", "POSSIBLE", "AmountForms", "DocumentMatches", "Hit",
           "MatchingRules", "PageMatches", "PreparedPage", "Query", "QueryError", "amount_forms", "amount_texts",
           "is_pin_shaped", "load_matching_rules", "make_hit", "normalise_pin", "parse_typed_amount", "pin_matches",
           "prepare_page", "search_document", "search_page"]
