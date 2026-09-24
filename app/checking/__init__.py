"""Checking: pairing a claim sheet's amounts with receipt pages (Stage C, D23-D33).

THE DECISION PACKAGE for Stage C: imports nothing from OCR, image or window
code — only app/matching (finding values on a page), app/layout and
app/claims (the claim sheet as read).

Public entry points:
    load_checking_rules()                     rules.py   (checking_rules.json)
    analyse_receipts() -> ReceiptFacts        receipts.py
    find_all(), decide(), check_claim()       engine.py
    ClaimCheck, ItemResult, Totals, Status,
    PASS / CAUTION / REVIEW, colours, reasons model.py

One file per job: labels.py (a label on a row), page_facts.py (what one page
says), repeats.py (repeated pages), findings.py (one amount on its pages),
assignment.py (pairing), verdict.py (the finding and its reason), totals.py.
"""

from app.checking.engine import check_claim, decide, find_all
from app.checking.findings import ItemFindings
from app.checking.model import (ALREADY_PAIRED, AMOUNT_UNREADABLE, CAUTION, DATE_CONTRADICTED, DATE_MISSING,
                                DATE_UNDECIDED, DATE_UNREADABLE, DOUBLE_CLAIM, GREEN, GREY, NO_DATE, NO_PIN, NOT_FOUND,
                                NOT_TOTAL, OTHER_BUYER, PAIRED, PASS, POSSIBLE_ONLY, RED, REPEAT_COPY, REVIEW, YELLOW,
                                ClaimCheck, ItemResult, Status, Totals)
from app.checking.receipts import ReceiptFacts, analyse_receipts
from app.checking.rules import CheckingRules, load_checking_rules

__all__ = ["ALREADY_PAIRED", "AMOUNT_UNREADABLE", "CAUTION", "DATE_CONTRADICTED", "DATE_MISSING", "DATE_UNDECIDED",
           "DATE_UNREADABLE", "DOUBLE_CLAIM", "GREEN", "GREY", "NO_DATE", "NO_PIN", "NOT_FOUND", "NOT_TOTAL",
           "OTHER_BUYER", "PAIRED", "PASS", "POSSIBLE_ONLY", "RED", "REPEAT_COPY", "REVIEW", "YELLOW", "CheckingRules",
           "ClaimCheck", "ItemFindings", "ItemResult", "ReceiptFacts", "Status", "Totals", "analyse_receipts",
           "check_claim", "decide", "find_all", "load_checking_rules"]
