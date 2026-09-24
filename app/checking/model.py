"""The results of checking a claim sheet against its receipts (blueprint section 4).

Each claimed amount gets an ItemResult: the system finding (PASS / CAUTION /
REVIEW — never a plain true or false), the colour the officer sees (green /
yellow / red), the page it was paired with (or the nearest candidate to
show), a reason code and a plain-words detail. The detail may name amounts,
dates and pages: it is for the window only, never for logs or errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.claims import ClaimItem

PASS, CAUTION, REVIEW = "PASS", "CAUTION", "REVIEW"
GREEN, YELLOW, RED, GREY = "green", "yellow", "red", "grey"

# reason codes
PAIRED = "paired"
AMOUNT_UNREADABLE = "amount unreadable"
NO_DATE = "no date"
DATE_UNREADABLE = "date unreadable"
DATE_UNDECIDED = "date undecided"
DATE_CONTRADICTED = "date contradicted"
NOT_FOUND = "amount not found"
POSSIBLE_ONLY = "possible match only"
DATE_MISSING = "date not on the receipt"
NOT_TOTAL = "not the receipt's total"
NO_PIN = "no company PIN"
OTHER_BUYER = "another buyer's PIN"
ALREADY_PAIRED = "receipt already paired"
REPEAT_COPY = "receipt is a repeat"
DOUBLE_CLAIM = "one receipt, two claims"


@dataclass
class ItemResult:
    item: ClaimItem
    status: str                          # PASS | CAUTION | REVIEW
    colour: str                          # GREEN | YELLOW | RED
    page: int | None                     # the paired page (green, red) or the nearest candidate (yellow)
    date_used: date | None               # the claimed date as used (it may have been settled by the receipt)
    reason: str                          # a reason code above
    detail: str                          # plain words, for the window only
    hits: list = field(default_factory=list)    # app.matching Hits to highlight on `page`


@dataclass
class Totals:
    grand_total: Decimal | None
    claimed: Decimal                     # the sheet's amounts x Rate, row by row
    grand_total_1: bool | None           # claimed == grand Total (None: no grand Total)
    rows_disagreeing: list[int]          # sheet rows whose own Total is not their amounts x Rate
    approved: Decimal                    # the green amounts x Rate
    grand_total_2: bool | None           # approved == grand Total


@dataclass
class Status:
    colour: str
    text: str


@dataclass
class ClaimCheck:
    items: list[ItemResult]
    pin_required: bool
    pin_on_pages: list[int]
    repeats: list[tuple[int, int]]       # (earlier page, the page repeating it)
    unread_pages: list[int]
    totals: Totals
    verification: Status
    pin: Status
    repeated_pages: Status
