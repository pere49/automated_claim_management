"""SearchPanel: right pane, lower part — search the open document (Stage B).

Date (calendar picker, "not set" until chosen), PIN and amount; Search (or
Enter) and Clear; the result per key with its highlight colour; and
Previous / Next match. The panel only collects input and shows results —
SearchController does the searching. At Stage C this panel is replaced by
the Excel row navigator.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QDateEdit, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from app.gui.search_summary import Summary

NOT_SET = QDate(2000, 1, 1)


class SearchPanel(QGroupBox):
    search_requested = Signal()
    clear_requested = Signal()
    previous_match = Signal()
    next_match = Signal()

    def __init__(self, colours: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__("Search this document", parent)
        self._colours = colours
        self.date_field = QDateEdit()
        self.date_field.setCalendarPopup(True)
        self.date_field.setDisplayFormat("dd/MM/yyyy")
        self.date_field.setMinimumDate(NOT_SET)
        self.date_field.setSpecialValueText("not set")
        self.date_field.setDate(NOT_SET)
        self.pin = QLineEdit()
        self.pin.setPlaceholderText("any format")
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("e.g. 1,200 or 1200.50")
        for field in (self.pin, self.amount):
            field.returnPressed.connect(self.search_requested)

        self.search_button = QPushButton("Search")
        self.search_button.setDefault(True)
        self.search_button.clicked.connect(self.search_requested)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_requested)
        self.previous_button = QPushButton("◀ Previous match")
        self.next_button = QPushButton("Next match ▶")
        self.previous_button.clicked.connect(self.previous_match)
        self.next_button.clicked.connect(self.next_match)
        self.match_position = QLabel()
        self.match_position.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self._result_grid = QGridLayout()
        self._result_grid.setColumnStretch(2, 1)
        self.shown = QLabel()
        self.shown.setWordWrap(True)
        self.progress = QLabel()
        self.progress.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self._labelled("Date", "date"), self.date_field)
        form.addRow(self._labelled("PIN", "pin"), self.pin)
        form.addRow(self._labelled("Amount", "amount"), self.amount)
        buttons = QHBoxLayout()
        buttons.addWidget(self.search_button, 1)
        buttons.addWidget(self.clear_button)
        navigation = QHBoxLayout()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.match_position, 1)
        navigation.addWidget(self.next_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.message)
        layout.addLayout(self._result_grid)
        layout.addWidget(self.shown)
        layout.addWidget(self.progress)
        layout.addLayout(navigation)
        layout.addStretch(1)
        self.show_cleared()

    # ---------------------------------------------------------------- input

    def values(self) -> tuple[date | None, str, str]:
        qd = self.date_field.date()
        when = None if qd == NOT_SET else date(qd.year(), qd.month(), qd.day())
        return when, self.amount.text(), self.pin.text()

    def reset_fields(self) -> None:
        self.date_field.setDate(NOT_SET)
        self.pin.clear()
        self.amount.clear()

    def set_available(self, available: bool) -> None:
        for widget in (self.search_button, self.date_field, self.pin, self.amount):
            widget.setEnabled(available)
        if not available:
            self.show_message("Searching is unavailable: the matching rules could not be loaded — see the Errors tab.")

    # ---------------------------------------------------------------- output

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def show_summary(self, summary: Summary) -> None:
        self.show_message("")
        self._clear_grid()
        for row, (key, label, finding) in enumerate(summary.keys):
            self._result_grid.addWidget(self._swatch(key), row, 0)
            name = QLabel(f"<b>{label}</b>")
            name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._result_grid.addWidget(name, row, 1)
            text = QLabel(finding)
            text.setWordWrap(True)
            self._result_grid.addWidget(text, row, 2)
        self.shown.setText(summary.shown)
        self.progress.setText(summary.progress)

    def show_cleared(self) -> None:
        self.show_message("")
        self._clear_grid()
        self.shown.setText("")
        self.progress.setText("")
        self.set_match_position(0, 0)

    def set_match_position(self, index: int, total: int) -> None:
        self.match_position.setText(f"match {index} of {total}" if total else "")
        self.previous_button.setEnabled(total > 1)
        self.next_button.setEnabled(total > 1)

    @property
    def result_lines(self) -> list[str]:
        """The result as plain text lines (for tests and copying)."""
        out = []
        for row in range(self._result_grid.rowCount()):
            label, finding = self._result_grid.itemAtPosition(row, 1), self._result_grid.itemAtPosition(row, 2)
            if label and finding:
                out.append(f"{label.widget().text().replace('<b>', '').replace('</b>', '')}: {finding.widget().text()}")
        return out + [t for t in (self.shown.text(), self.progress.text()) if t]

    # ---------------------------------------------------------------- internal

    def _swatch(self, key: str) -> QLabel:
        swatch = QLabel()
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(f"background: {self._colours[key]}; border-radius: 2px;")
        return swatch

    def _labelled(self, text: str, key: str) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._swatch(key))
        row.addWidget(QLabel(text))
        return box

    def _clear_grid(self) -> None:
        while self._result_grid.count():
            widget = self._result_grid.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
