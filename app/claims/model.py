"""The records a claim sheet is read into (blueprint section 4).

A ClaimFile holds one ClaimSheet per claim table found (a PDF page). Its
rows hold ClaimItems: one per non-zero amount in an expense column, paired
with the row's date. Reading problems are attached to the row or item they
concern — in plain words, never with the values themselves — so one bad
cell never stops the sheet. A SheetPlace says where the table sits on its
page, so the window can show the sheet as the document itself (D39).
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
PDF_TEXT, SCANNED = "pdf text", "scanned"


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


@dataclass(frozen=True)
class Box:
    """A rectangle on the claim page, in fractions of the page's width and height (0..1)."""
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class SheetPlace:
    """Where the claim table sits on its page, in fractions of the page (0..1)."""
    page: int                                        # 1-based page of the claim file
    printed: Box                                     # everything printed on the page (the view crops to it)
    rows: dict[int, tuple[float, float]]             # grid row -> (top, bottom)
    columns: dict[int, tuple[float, float]]          # grid column -> (left, right)

    def cell(self, row: int, column: int) -> Box | None:
        if row not in self.rows or column not in self.columns:
            return None
        (top, bottom), (left, right) = self.rows[row], self.columns[column]
        return Box(left, top, right, bottom)

    def row_band(self, row: int) -> Box | None:
        """The row across the whole table."""
        if row not in self.rows or not self.columns:
            return None
        top, bottom = self.rows[row]
        return Box(min(a for a, _ in self.columns.values()), top, max(b for _, b in self.columns.values()), bottom)


@dataclass
class ClaimSheet:
    name: str                           # "page N" of the claim file
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
    place: SheetPlace | None = None     # where the table sits on its page (None: not known)

    @property
    def items(self) -> list[ClaimItem]:
        return [item for row in self.rows for item in row.items]


@dataclass
class ClaimFile:
    path: Path
    kind: str                           # PDF_TEXT | SCANNED
    sheets: list[ClaimSheet]
    active: int                         # the sheet to show first
    skipped: list[str] = field(default_factory=list)   # pages without a claim table
