"""Reading a claim file — the public entry of app/claims.

    sheet_kind(path, rules)              PDF_TEXT or SCANNED (a picture: needs OCR first)
    looks_like_claim_sheet(path, rules)  cheap check used to route a clicked file
    read_claim_file(path, rules, today, scanned_words=..., dpi=...) -> ClaimFile

For now a claim sheet arrives as a PDF — exported from Excel (a text layer)
or scanned — or as a picture (owner, D39); Excel files are refused with a
plain message. PDF pages without a claim table are skipped (and named); a
file with none at all is an error. Every failure is a StageError ("claim
sheet") naming the file — never its contents. Each sheet carries where its
table sits on the page, in fractions of the page (SheetPlace).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.claims.image_grid import split_words, table_from_picture
from app.claims.layout import find_layout
from app.claims.model import PDF_TEXT, SCANNED, Box, ClaimFile, ClaimSheet, SheetPlace
from app.claims.pdf_text import has_text_layer, text_pages
from app.claims.pictures import page_picture
from app.claims.rules import ClaimRules
from app.claims.sheet_builder import build_sheet
from app.claims.table_grid import Table, Word, printed_area
from app.errors import StageError

SPREADSHEET_SUFFIXES = (".xlsx", ".xlsm", ".xls")
PICTURE_SUFFIXES = (".jpg", ".jpeg", ".png", ".heic", ".heif")


def sheet_kind(path: Path, rules: ClaimRules) -> str:
    suffix = path.suffix.lower()
    if suffix in SPREADSHEET_SUFFIXES:
        raise StageError("claim sheet", "Excel files are not read for now: use the PDF of the claim sheet",
                         file=path.name)
    if suffix == ".pdf":
        return PDF_TEXT if has_text_layer(path, rules) else SCANNED
    if suffix in PICTURE_SUFFIXES:
        return SCANNED
    raise StageError("claim sheet", "this kind of file cannot be a claim sheet (use a PDF of it)", file=path.name)


def looks_like_claim_sheet(path: Path, rules: ClaimRules) -> bool:
    """True for a PDF whose text layer holds a claim table. False for a
    picture (not knowable before OCR) and anything unreadable."""
    try:
        if sheet_kind(path, rules) == PDF_TEXT:
            return any(find_layout(p.table.cells, rules) is not None for p in text_pages(path, rules))
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
    if kind == PDF_TEXT:
        for page in text_pages(path, rules):
            place = _place(page.number, page.table, page.printed, page.size)
            _add(sheets, skipped, f"page {page.number}", page.table, place, rules, today)
    else:
        if not scanned_words:
            raise StageError("claim sheet", "this claim sheet is a picture: it must be read by OCR first",
                             file=path.name)
        for number in sorted(scanned_words):
            picture = page_picture(path, number, dpi)
            table = table_from_picture(picture, scanned_words[number], rules)
            height, width = picture.shape[:2]
            place = _place(number, table, printed_area(split_words(scanned_words[number]), table), (width, height))
            _add(sheets, skipped, f"page {number}", table, place, rules, today)
    if not sheets:
        raise StageError("claim sheet", "no claim table was found (a header row with a Date column and the expense "
                         "columns named in claim_rules.json)", file=path.name)
    return ClaimFile(path, kind, sheets, 0, skipped)


def _add(sheets: list[ClaimSheet], skipped: list[str], name: str, table: Table, place: SheetPlace, rules: ClaimRules,
         today: date) -> None:
    grid = table.cells
    sheet = build_sheet(name, grid, list(range(1, len(grid) + 1)), rules, today, place)
    if sheet is None:
        skipped.append(name)
    else:
        sheets.append(sheet)


def _place(number: int, table: Table, printed: tuple[float, float, float, float] | None,
           size: tuple[float, float]) -> SheetPlace:
    """Positions -> fractions of the page (so any drawing of the page can use them)."""
    width, height = size
    left, top, right, bottom = printed or (0.0, 0.0, width, height)
    return SheetPlace(
        page=number,
        printed=Box(_frac(left, width), _frac(top, height), _frac(right, width), _frac(bottom, height)),
        rows={r: (_frac(a, height), _frac(b, height)) for r, (a, b) in enumerate(table.row_bands)},
        columns={c: (_frac(a, width), _frac(b, width)) for c, (a, b) in enumerate(table.col_bands)},
    )


def _frac(value: float, whole: float) -> float:
    return min(1.0, max(0.0, value / whole)) if whole else 0.0
