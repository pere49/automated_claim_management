"""SheetGrid: right pane, middle — the claim sheet, with tabs, reasons and grand totals.

One tab per claim sheet in the file (an Excel workbook may hold several
weeks). The columns up to the date stay in view while the amounts scroll. Clicking a claimed amount — or moving onto it with the arrow keys —
selects it (item_selected); the line under the table says why it is green,
yellow or red. Grand total 1 (the sheet's own arithmetic) and Grand total 2
(the verified amounts against the grand Total) sit at the bottom (D30).
"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QTabBar, QVBoxLayout, QWidget

from app.checking import ClaimCheck
from app.claims import ClaimFile
from app.gui.frozen_table import FrozenTable
from app.gui.sheet_model import SheetModel


class SheetGrid(QWidget):
    item_selected = Signal(int)          # an item index, chosen by the officer
    tab_changed = Signal(int)

    def __init__(self, cell_colours: dict[str, str], status_colours: dict[str, str], column_max_px: int = 130,
                 parent=None) -> None:
        super().__init__(parent)
        self._column_max_px = column_max_px
        self._status_colours = status_colours
        self._result: ClaimCheck | None = None
        self._quiet = False
        self._just_selected: int | None = None     # a click that changed the current cell is announced once
        self.title = QLabel("<b>Claim sheet</b>")
        self.tabs = QTabBar()
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)
        self.model = SheetModel(cell_colours, self)
        self.table = FrozenTable()
        self.table.setModel(self.model)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.selectionModel().currentChanged.connect(self._on_current)
        self.table.clicked.connect(self._on_clicked)
        self.reason = QLabel()
        self.reason.setWordWrap(True)
        self.reason.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.total_1, self.total_2 = QLabel(), QLabel()
        totals = QHBoxLayout()
        totals.addWidget(self.total_1, 1)
        totals.addWidget(self.total_2, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.tabs)
        layout.addWidget(self.message)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.reason)
        layout.addLayout(totals)
        self.show_claim(None)

    # ---------------------------------------------------------------- public

    def show_claim(self, claim: ClaimFile | None, index: int = 0) -> None:
        self._quiet = True
        while self.tabs.count():
            self.tabs.removeTab(0)
        if claim is not None:
            for sheet in claim.sheets:
                self.tabs.addTab(sheet.name.strip() or "sheet")
            self.tabs.setCurrentIndex(index)
        self.tabs.setVisible(bool(claim) and len(claim.sheets) > 1)
        self._quiet = False
        self.title.setText(f"<b>Claim sheet</b> — {claim.path.name}" if claim else "<b>Claim sheet</b>")
        self.model.set_sheet(claim.sheets[index] if claim else None)
        self._fit_columns()
        self.show_results(None)
        self.message.setText("" if claim else "Choose a claim sheet (Excel, or a PDF of it) from the list: click it, "
                                              "or right-click a file → Use as claim sheet.")
        self.message.setVisible(not claim)

    def show_sheet(self, claim: ClaimFile, index: int) -> None:
        self.model.set_sheet(claim.sheets[index])
        self._fit_columns()
        self.show_results(None)

    def show_results(self, result: ClaimCheck | None) -> None:
        self._result = result
        self.model.set_results(result.items if result else None)
        self.reason.setText("")
        if result is None:
            self.total_1.setText("")
            self.total_2.setText("")
            return
        t = result.totals
        grand = f"{t.grand_total:,.2f}" if t.grand_total is not None else "no grand Total"
        rows = f" — rows {', '.join(map(str, t.rows_disagreeing))} do not add up" if t.rows_disagreeing else ""
        self.total_1.setText(self._dot("green" if t.grand_total_1 else "red") +
                             f" Grand total 1: amounts {t.claimed:,.2f}, Total {grand}{rows}")
        self.total_2.setText(self._dot("green" if t.grand_total_2 else "yellow") +
                             f" Grand total 2: verified {t.approved:,.2f} of {grand}")

    def show_waiting(self, text: str) -> None:
        if self.model.sheet is not None:
            self.reason.setText(text)

    def select_item(self, item: int) -> None:
        index = self.model.index_of(item)
        if not index.isValid():
            return
        self._quiet = True
        self.table.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.table.scrollTo(index)
        self._quiet = False
        self._explain(item)

    @property
    def current_item(self) -> int | None:
        return self.model.item_at(self.table.currentIndex())

    # ---------------------------------------------------------------- internal

    def _fit_columns(self) -> None:
        self.table.resizeColumnsToContents()
        for c in range(self.model.columnCount()):
            if self.table.columnWidth(c) > self._column_max_px:
                self.table.setColumnWidth(c, self._column_max_px)
        date = self.model.date_position
        self.table.set_frozen_columns(date + 1 if date is not None else 0)   # the date stays in view

    def _explain(self, item: int) -> None:
        if self._result is None:
            return
        r = self._result.items[item]
        it = r.item
        when = f"{r.date_used:%d %b %Y}" if r.date_used else "no date"
        amount = f"{it.amount:,.2f}" if it.amount is not None else "unreadable amount"
        self.reason.setText(f"{self._dot(r.colour)} Row {it.row} · {it.column} · {amount} · {when} — "
                            f"{r.status.lower()}: {r.detail}")

    def _dot(self, colour: str) -> str:
        return f"<span style='color:{self._status_colours[colour]}; font-size:14pt'>●</span>"

    def _on_current(self, current, _previous) -> None:
        item = self.model.item_at(current)
        if item is not None and not self._quiet:
            self._just_selected = item
            self._explain(item)
            self.item_selected.emit(item)

    def _on_clicked(self, index) -> None:
        """A click on the amount already chosen shows it again (e.g. after scrolling away)."""
        item = self.model.item_at(index)
        if item is None or self._quiet:
            return
        if self._just_selected == item:
            self._just_selected = None
            return
        self._explain(item)
        self.item_selected.emit(item)

    def _on_tab(self, index: int) -> None:
        if not self._quiet and index >= 0:
            self.tab_changed.emit(index)
