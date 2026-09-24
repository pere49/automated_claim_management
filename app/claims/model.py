"""The records a claim sheet is read into (blueprint section 4).

A ClaimFile holds one ClaimSheet per claim table found (an Excel tab, or a
PDF page). Its rows hold ClaimItems: one per non-zero amount in an expense
column, paired with the row's date. Reading problems are attached to the
row or item they concern — in plain words, never with the values
themselves — so one bad cell never stops the sheet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

# how a claim-sheet date was read (sheet_dates.py)
EMPTY, UNREADABLE, ONE_MEANING = "empty", "unreadable", "one meaning"
SHEET_ORDER, NO_FUTURE, CLAIM_PERIOD, UNDECIDED = "sheet order", "no future date", "claim period", "undecided"

# what kind of file a claim sheet came from
EXCEL, PDF_TEXT, SCANNED = "excel", "pdf text", "scanned"


@dataclass(frozen=True)
class DateReading:
    value: date | None                  # the date used; None when empty, unreadable or still undecided
    candidates: tuple[date, ...] = ()   # every possible reading of the cell (two when day and month could swap)
    how: str = EMPTY

    @property
    def open(self) -> bool:
        """Still undecided between two readings: the receipts may settle it (app/checking)."""
        return self.value is None and len(self.candidates) == 2


@dataclass(frozen=True)
class ClaimItem:
    index: int                          # position in the sheet's item list
    row: int                            # the sheet's own row number, as the officer sees it
    grid_row: int                       # the cell in ClaimSheet.grid
    grid_col: int
    column: str                         # expense column name
    amount: Decimal | None              # None when the cell could not be read as an amount
    date: DateReading
    rate: Decimal                       # the row's Rate (1 when blank or zero)
    problem: str | None = None          # why the amount could not be read


@dataclass
class ClaimRow:
    row: int
    grid_row: int
    date: DateReading
    items: list[ClaimItem]
    rate: Decimal
    total: Decimal | None               # the row's own Total cell, when it has one
    problems: list[str] = field(default_factory=list)


@dataclass
class SheetColumns:
    date: int
    expenses: dict[int, str]            # grid column -> expense column name
    rate: int | None
    total: int | None


@dataclass
class ClaimSheet:
    name: str                           # the Excel tab's name, or "page N" of a PDF
    grid: list[list[object]]            # every cell as found (Excel values, or text from a PDF)
    header_row: int                     # grid row of the header
    first_data_row: int
    end_row: int                        # grid row of the Total row (or one past the last row)
    columns: SheetColumns
    rows: list[ClaimRow]
    grand_total: Decimal | None
    grand_total_cell: tuple[int, int] | None
    currency: str | None
    row_numbers: list[int]              # grid row -> the sheet's own row number
    problems: list[str] = field(default_factory=list)

    @property
    def items(self) -> list[ClaimItem]:
        return [item for row in self.rows for item in row.items]


@dataclass
class ClaimFile:
    path: Path
    kind: str                           # EXCEL | PDF_TEXT | SCANNED
    sheets: list[ClaimSheet]
    active: int                         # the sheet to show first
    skipped: list[str] = field(default_factory=list)   # tabs / pages without a claim table
