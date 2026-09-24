"""Reading a claim file — the public entry of app/claims.

    sheet_kind(path, rules)              EXCEL, PDF_TEXT or SCANNED (a picture: needs OCR first)
    looks_like_claim_sheet(path, rules)  cheap check used to route a clicked file
    read_claim_file(path, rules, today, scanned_words=..., dpi=...) -> ClaimFile

Excel tabs and PDF pages without a claim table are skipped (and named);
a file with none at all is an error. Every failure is a StageError
("claim sheet") naming the file — never its contents.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.claims.excel import read_workbook
from app.claims.image_grid import grid_from_picture
from app.claims.layout import find_layout
from app.claims.model import EXCEL, PDF_TEXT, SCANNED, ClaimFile, ClaimSheet
from app.claims.pdf_text import has_text_layer, text_pages
from app.claims.pictures import page_picture
from app.claims.rules import ClaimRules
from app.claims.sheet_builder import build_sheet
from app.claims.table_grid import Word
from app.errors import StageError

EXCEL_SUFFIXES = (".xlsx", ".xlsm")
REFUSED_SUFFIXES = (".xls",)
PICTURE_SUFFIXES = (".jpg", ".jpeg", ".png", ".heic", ".heif")


def sheet_kind(path: Path, rules: ClaimRules) -> str:
    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return EXCEL
    if suffix in REFUSED_SUFFIXES:
        raise StageError("claim sheet", "old .xls workbooks cannot be read: open the file in Excel and save it "
                         "as .xlsx", file=path.name)
    if suffix == ".pdf":
        return PDF_TEXT if has_text_layer(path, rules) else SCANNED
    if suffix in PICTURE_SUFFIXES:
        return SCANNED
    raise StageError("claim sheet", "this kind of file cannot be a claim sheet (use Excel or a PDF)", file=path.name)


def looks_like_claim_sheet(path: Path, rules: ClaimRules) -> bool:
    """True for an Excel file, or a PDF whose text layer holds a claim table.
    False for a picture (not knowable before OCR) and anything unreadable."""
    try:
        kind = sheet_kind(path, rules)
        if kind == EXCEL:
            return True
        if kind == PDF_TEXT:
            return any(find_layout(p.grid, rules) is not None for p in text_pages(path, rules))
    except StageError:
        return False
    return False


def read_claim_file(path: Path, rules: ClaimRules, today: date,
                    scanned_words: dict[int, list[Word]] | None = None, dpi: int = 300) -> ClaimFile:
    """Read every claim table in the file. A scanned sheet needs its OCR
    segments per page (in the frame of the page drawn at `dpi`). Raises
    StageError(stage="claim sheet")."""
    kind = sheet_kind(path, rules)
    sheets: list[ClaimSheet] = []
    skipped: list[str] = []
    active = 0
    if kind == EXCEL:
        tabs, saved_on = read_workbook(path)
        for name, grid in tabs:
            sheet = build_sheet(name, grid, list(range(1, len(grid) + 1)), rules, today)
            if sheet is None:
                skipped.append(name)
                continue
            if name == saved_on:
                active = len(sheets)
            sheets.append(sheet)
    elif kind == PDF_TEXT:
        for page in text_pages(path, rules):
            _add(sheets, skipped, f"page {page.number}", page.grid, rules, today)
    else:
        if not scanned_words:
            raise StageError("claim sheet", "this claim sheet is a picture: it must be read by OCR first",
                             file=path.name)
        for number in sorted(scanned_words):
            grid = grid_from_picture(page_picture(path, number, dpi), scanned_words[number], rules)
            _add(sheets, skipped, f"page {number}", grid, rules, today)
    if not sheets:
        raise StageError("claim sheet", "no claim table was found (a header row with a Date column and the expense "
                         "columns named in claim_rules.json)", file=path.name)
    return ClaimFile(path, kind, sheets, active, skipped)


def _add(sheets: list[ClaimSheet], skipped: list[str], name: str, grid: list, rules: ClaimRules, today: date) -> None:
    sheet = build_sheet(name, grid, list(range(1, len(grid) + 1)), rules, today)
    if sheet is None:
        skipped.append(name)
    else:
        sheets.append(sheet)
