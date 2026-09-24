"""Claims: reading a claim sheet — Excel, a PDF of it, or a scanned picture.

Public entry points:
    load_claim_rules()                               rules.py  (claim_rules.json)
    sheet_kind(), looks_like_claim_sheet(),
    read_claim_file() -> ClaimFile                   reader.py
    ClaimFile, ClaimSheet, ClaimRow, ClaimItem,
    DateReading, and the kind / how-read constants   model.py

Each file has one job: excel.py (workbook cells), pdf_text.py (text layer
and drawn lines), image_grid.py (lines found in a picture), table_grid.py
(words placed in ruled cells), layout.py (where the claim table is),
amounts.py and sheet_dates.py (one cell's value), sheet_builder.py (grid ->
ClaimSheet). Imports nothing from the window code.

The readers load only when first used: the decision package (app/checking)
uses these records without pulling in openpyxl, pymupdf or OpenCV.
"""

from app.claims.model import (CLAIM_PERIOD, EMPTY, EXCEL, NO_FUTURE, ONE_MEANING, PDF_TEXT, SCANNED, SHEET_ORDER,
                              UNDECIDED, UNREADABLE, ClaimFile, ClaimItem, ClaimRow, ClaimSheet, DateReading,
                              SheetColumns)
from app.claims.rules import ClaimRules, load_claim_rules

_READERS = ("looks_like_claim_sheet", "read_claim_file", "sheet_kind")

__all__ = ["CLAIM_PERIOD", "EMPTY", "EXCEL", "NO_FUTURE", "ONE_MEANING", "PDF_TEXT", "SCANNED", "SHEET_ORDER",
           "UNDECIDED", "UNREADABLE", "ClaimFile", "ClaimItem", "ClaimRow", "ClaimRules", "ClaimSheet", "DateReading",
           "SheetColumns", "load_claim_rules", *_READERS]


def __getattr__(name: str):
    if name in _READERS:
        from app.claims import reader
        return getattr(reader, name)
    raise AttributeError(f"module 'app.claims' has no attribute {name!r}")
