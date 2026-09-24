"""PROTOTYPE (tools/) — date trial: fabricated claim sheets with dates written many ways.

Every sheet is one fictional writer's claim: a claim period, 1-25 rows, and
a writing style (Excel date cells, numeric day-first or month-first, month
words, ISO, Excel serial numbers, mixed words and numbers). Added after a
real claim workbook showed it: "excel_locale_swapped", a writer typing into
an Excel set to the other day/month order - a date whose day is 12 or less
is saved as a date cell with day and month SWAPPED (3/8/2026 meant 3 August,
saved as 8 March); a later day cannot be read that way and stays text in the
writer's order. Correct Excel sheets get a few dotted text dates
("13.08.2026", which Excel never converts) so a rule cannot simply treat
"any text date" as a sign of swapping. Some writers swap
day and month on some rows; some sheets are unsorted; some come from a PDF
picture and carry OCR-like noise. Each row keeps its true date, so any
reading rule can be scored. All data is fabricated.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

EXCEL_EPOCH = date(1899, 12, 30)
EXCEL_STYLES = ("excel_date_cell", "excel_serial_number", "excel_locale_swapped")


@dataclass
class Row:
    true: date | None
    cell: object                 # what the reader sees: datetime, int (serial) or text; None if blank
    swapped: bool = False        # the writer swapped day and month on this row
    receipt_dates: set = field(default_factory=set)   # dates found on receipts carrying this row's amount


@dataclass
class Sheet:
    style: str
    order: str                   # the writer's intended numeric order: "day" | "month" | "-"
    from_pdf: bool
    swapper: bool
    rows: list[Row]
    processed: date | None = None   # the day the officer checks the claim (the last true date + a delay)


def generate(cfg: dict) -> list[Sheet]:
    rnd = random.Random(cfg["seed"])
    styles, weights = zip(*cfg["writer_styles"].items())
    return [_sheet(rnd, cfg, rnd.choices(styles, weights)[0]) for _ in range(cfg["sheets"])]


def _sheet(rnd: random.Random, cfg: dict, style: str) -> Sheet:
    y0, y1 = cfg["years"]
    start = date(rnd.randint(y0, y1), 1, 1) + timedelta(days=rnd.randint(0, 364))
    span = rnd.randint(*cfg["claim_span_days"])
    n = rnd.randint(*cfg["rows_per_sheet"])
    days = sorted(start + timedelta(days=rnd.randint(0, span)) for _ in range(n))
    if rnd.random() < cfg["unsorted_share"]:
        rnd.shuffle(days)
    order = {"numeric_month_first": "month", "numeric_day_first": "day", "word_month_first": "month",
             "word_day_first": "day", "mixed_words_and_numbers": rnd.choice(["day", "month"]),
             "excel_locale_swapped": rnd.choice(["day", "month"]),
             "excel_date_cell": rnd.choice(["day", "month"])}.get(style, "-")
    numeric = style in ("numeric_month_first", "numeric_day_first", "mixed_words_and_numbers")
    swapper = numeric and rnd.random() < cfg["order_swapper_share"]
    from_pdf = style not in EXCEL_STYLES and rnd.random() < cfg["pdf_source_share"]
    zero = rnd.random() < 0.5
    sep = rnd.choice(["/", "-", "."])
    yy = rnd.random() < 0.3
    upper = rnd.random() < 0.2
    rows = []
    for d in days:
        if rnd.random() < cfg["blank_date_rate"]:
            rows.append(Row(None, None))
            continue
        swapped = swapper and rnd.random() < cfg["swap_rate_within_swapper"]
        row_order = ("month" if order == "day" else "day") if swapped else order
        if style == "excel_date_cell":
            if rnd.random() < cfg["excel_dotted_text_rate"]:
                cell = _numeric(d, order, ".", zero, yy)       # Excel never converts dotted dates
            else:
                cell = datetime(d.year, d.month, d.day)
        elif style == "excel_locale_swapped":
            if d.day <= 12:
                cell = datetime(d.year, d.day, d.month)         # read in Excel's (other) order
            else:
                cell = _numeric(d, order, "/", zero, yy)       # unreadable that way: left as text
        elif style == "excel_serial_number":
            cell = (d - EXCEL_EPOCH).days
        elif style == "iso":
            cell = f"{d.year}-{d.month:02d}-{d.day:02d}"
        elif style.startswith("word") or (style == "mixed_words_and_numbers" and rnd.random() < 0.5):
            cell = _word(rnd, cfg, d, row_order, upper)
        else:
            cell = _numeric(d, row_order, sep, zero, yy)
        if from_pdf and isinstance(cell, str) and rnd.random() < cfg["ocr_noise_rate"]:
            cell = _noise(rnd, cell)
        rows.append(Row(d, cell, swapped))
    sheet = Sheet(style, order, from_pdf, swapper, rows)
    _receipts(rnd, cfg, sheet)
    buckets = cfg["processing_delay_days"]
    low, high, _ = rnd.choices(buckets, [b[2] for b in buckets])[0]
    sheet.processed = max(days) + timedelta(days=rnd.randint(low, high))
    return sheet


def _numeric(d: date, order: str, sep: str, zero: bool, yy: bool) -> str:
    day, month = (f"{d.day:02d}", f"{d.month:02d}") if zero else (str(d.day), str(d.month))
    year = f"{d.year % 100:02d}" if yy else str(d.year)
    first, second = (day, month) if order == "day" else (month, day)
    return f"{first}{sep}{second}{sep}{year}"


def _word(rnd: random.Random, cfg: dict, d: date, order: str, upper: bool) -> str:
    name = rnd.choice(cfg["month_names"][str(d.month)])
    name = name.upper() if upper else name
    year = str(d.year) if rnd.random() < 0.6 else f"{d.year % 100:02d}"
    day = f"{d.day:02d}" if rnd.random() < 0.5 else str(d.day)
    if order == "day":
        return rnd.choice([f"{day}-{name}-{year}", f"{day} {name} {year}", f"{day} {name}, {year}"])
    return rnd.choice([f"{name} {day}, {year}", f"{name} {day} {year}", f"{name}-{day}-{year}"])


def _noise(rnd: random.Random, text: str) -> str:
    kind = rnd.choice(["O", "l", "S", "space"])
    if kind == "space":
        i = rnd.randrange(1, len(text))
        return text[:i] + " " + text[i:]
    digit = {"O": "0", "l": "1", "S": "5"}[kind]
    spots = [i for i, c in enumerate(text) if c == digit]
    if not spots:
        return text
    i = rnd.choice(spots)
    return text[:i] + kind + text[i + 1:]


def _receipts(rnd: random.Random, cfg: dict, sheet: Sheet) -> None:
    """The dates found on receipts carrying each row's amount."""
    for row in sheet.rows:
        if row.true is None:
            continue
        if rnd.random() < cfg["receipt_found_rate"]:
            row.receipt_dates.add(row.true)
        if rnd.random() < cfg["receipt_coincidence_rate"] and row.true.day <= 12:
            row.receipt_dates.add(date(row.true.year, row.true.day, row.true.month))
