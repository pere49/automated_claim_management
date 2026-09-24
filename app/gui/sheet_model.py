"""SheetModel: the claim sheet as a table, each claimed amount coloured by its finding.

Shows the claim table from its first data row to its Total row, one column
per sheet column, headed by the sheet's own headers (the expense columns by
their names). A date shows as read (03 Aug 2026) — the tooltip says how it
was read and what the cell holds; an amount shows with two decimals, zero as
a dash. Each claimed amount's cell is coloured green / yellow / red once the
claim is checked; its tooltip gives the reason.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from app.checking import ItemResult
from app.claims import EMPTY, ONE_MEANING, ClaimSheet


class SheetModel(QAbstractTableModel):
    def __init__(self, cell_colours: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._colours = {k: QColor(v) for k, v in cell_colours.items()}
        self.sheet: ClaimSheet | None = None
        self._results: dict[int, ItemResult] = {}
        self._rows: list[int] = []          # grid rows shown
        self._cols: list[int] = []          # grid columns shown
        self._items: dict[tuple[int, int], int] = {}      # (grid row, grid col) -> item index
        self._dates: dict[int, object] = {}              # grid row -> DateReading
        self._money: set[int] = set()                    # columns holding amounts (two decimals)

    # ---------------------------------------------------------------- public

    def set_sheet(self, sheet: ClaimSheet | None) -> None:
        self.beginResetModel()
        self.sheet, self._results = sheet, {}
        self._rows, self._cols, self._items, self._dates = [], [], {}, {}
        if sheet is not None:
            last = sheet.end_row if sheet.end_row < len(sheet.grid) else len(sheet.grid) - 1
            self._rows = [r for r in range(sheet.first_data_row, last + 1)
                          if r == sheet.end_row or any(_content(v) for v in sheet.grid[r])]   # template rows of zeros hidden
            used = {c for r in [sheet.header_row] + self._rows for c, v in enumerate(sheet.grid[r]) if _filled(v)}
            self._cols = sorted(used)
            self._items = {(it.grid_row, it.grid_col): it.index for it in sheet.items}
            self._dates = {row.grid_row: row.date for row in sheet.rows}
            cols = sheet.columns
            self._money = set(cols.expenses) | {c for c in (cols.rate, cols.total) if c is not None}
        self.endResetModel()

    def set_results(self, results: list[ItemResult] | None) -> None:
        self._results = {r.item.index: r for r in results or []}
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, len(self._cols) - 1))

    def item_at(self, index: QModelIndex) -> int | None:
        if not index.isValid():
            return None
        return self._items.get((self._rows[index.row()], self._cols[index.column()]))

    @property
    def date_position(self) -> int | None:
        """The table column showing the dates."""
        if self.sheet is None or self.sheet.columns.date not in self._cols:
            return None
        return self._cols.index(self.sheet.columns.date)

    def index_of(self, item: int) -> QModelIndex:
        for (r, c), i in self._items.items():
            if i == item and r in self._rows and c in self._cols:
                return self.index(self._rows.index(r), self._cols.index(c))
        return QModelIndex()

    # ---------------------------------------------------------------- Qt

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cols)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or self.sheet is None:
            return None
        if orientation == Qt.Orientation.Vertical:
            return str(self.sheet.row_numbers[self._rows[section]])
        c = self._cols[section]
        if c in self.sheet.columns.expenses:
            return self.sheet.columns.expenses[c]
        return _text(self.sheet.grid[self.sheet.header_row][c]) or ""

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.sheet is None:
            return None
        r, c = self._rows[index.row()], self._cols[index.column()]
        value = self.sheet.grid[r][c]
        item = self._items.get((r, c))
        result = self._results.get(item) if item is not None else None
        if role == Qt.ItemDataRole.DisplayRole:
            if c == self.sheet.columns.date and r in self._dates:
                return _date_text(self._dates[r], value)
            return _text(value, money=c in self._money)
        if role == Qt.ItemDataRole.BackgroundRole and result is not None:
            return self._colours[result.colour]
        if role == Qt.ItemDataRole.ToolTipRole:
            if result is not None:
                return f"{result.status}: {result.detail}"
            if item is not None:
                problem = self.sheet.items[item].problem
                return problem or "not checked yet — the receipts have not all been read"
            if c == self.sheet.columns.date and r in self._dates:
                return _date_tip(self._dates[r], value)
            return _text(value, money=c in self._money) or None
        if role == Qt.ItemDataRole.FontRole and self.sheet.grand_total_cell == (r, c):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float, Decimal)):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


def _filled(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def _content(value: object) -> bool:
    """Something written in the cell: not empty, not a zero or a dash."""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return value != 0
    return _filled(value) and str(value).strip() not in ("-", "–", "—")


def _text(value: object, money: bool = True) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return f"{value:%d/%m/%Y}"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
        if not money:
            return format(number.normalize(), "f")      # 4740150, not 4.74015E+6
        return "–" if number == 0 else f"{number:,.2f}"
    return " ".join(str(value).split())


def _date_text(reading, value: object) -> str:
    if reading.value is not None:
        return f"{reading.value:%d %b %Y}"
    if reading.open:
        a, b = reading.candidates
        return f"{a:%d %b} or {b:%d %b %Y}?"
    return _text(value)


def _date_tip(reading, value: object) -> str:
    cell = _text(value) or "empty"
    if reading.how == EMPTY:
        return "no date in this row"
    if reading.value is None and reading.open:
        return f"the cell holds {cell}: it could be either date; the receipts may settle it"
    if reading.value is None:
        return f"the cell holds {cell}: not a date that could be read"
    if reading.how == ONE_MEANING:
        return f"the cell holds {cell}"
    return f"the cell holds {cell}: read as {reading.value:%d %b %Y} (decided by the {reading.how})"
