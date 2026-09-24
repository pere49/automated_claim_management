"""Claims: reading a claim sheet — a PDF of it (exported or scanned), or a picture of it.

Public entry points:
    load_claim_rules()                               rules.py  (claim_rules.json)
    sheet_kind(), looks_like_claim_sheet(),
    read_claim_file() -> ClaimFile                   reader.py
    ClaimFile, ClaimSheet, ClaimRow, ClaimItem,
    DateReading, SheetPlace, Box, and the kind /
    how-read constants                               model.py

Each file has one job: pdf_text.py (text layer and drawn lines),
image_grid.py (lines found in a picture), pictures.py (the picture itself),
table_grid.py (words placed in ruled cells, with their positions),
layout.py (where the claim table is), amounts.py and sheet_dates.py (one
cell's value), sheet_builder.py (grid -> ClaimSheet). Imports nothing from
the window code. Excel files are not read for now (D39; the reader is in
git history, commit e202fa6).

The readers load only when first used: the decision package (app/checking)
uses these records without pulling in pymupdf or OpenCV.
"""

from app.claims.model import (CLAIM_PERIOD, EMPTY, NO_FUTURE, ONE_MEANING, PDF_TEXT, SCANNED, SHEET_ORDER, UNDECIDED,
                              UNREADABLE, Box, ClaimFile, ClaimItem, ClaimRow, ClaimSheet, DateReading, SheetColumns,
                              SheetPlace)
from app.claims.rules import ClaimRules, load_claim_rules

_READERS = ("looks_like_claim_sheet", "read_claim_file", "sheet_kind")

__all__ = ["CLAIM_PERIOD", "EMPTY", "NO_FUTURE", "ONE_MEANING", "PDF_TEXT", "SCANNED", "SHEET_ORDER", "UNDECIDED",
           "UNREADABLE", "Box", "ClaimFile", "ClaimItem", "ClaimRow", "ClaimRules", "ClaimSheet", "DateReading",
           "SheetColumns", "SheetPlace", "load_claim_rules", *_READERS]


def __getattr__(name: str):
    if name in _READERS:
        from app.claims import reader
        return getattr(reader, name)
    raise AttributeError(f"module 'app.claims' has no attribute {name!r}")
