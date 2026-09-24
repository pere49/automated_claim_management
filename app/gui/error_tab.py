"""ErrorTab: every structured error and warning of this session.

Newest first, one line each (StageError.summary). Selecting a line shows
its full detail (StageError.full_text, with the traceback) underneath, and
both can be copied. This is the offline diagnostic channel: a screenshot of
this tab should be enough to find the problem without reproducing it.
Entries are kept for the whole session and never cleared.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from app.errors import ERROR, StageError

_ENTRY_ROLE = Qt.ItemDataRole.UserRole
_LEVEL_COLOURS = {ERROR: QColor(180, 30, 30)}
_WARNING_COLOUR = QColor(160, 100, 0)


@dataclass(frozen=True)
class ErrorEntry:
    level: str
    summary: str
    full_text: str

    @property
    def line(self) -> str:
        return f"{self.level.upper():8}{self.summary}"


class ErrorTab(QWidget):
    count_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entries: list[ErrorEntry] = []

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._show_detail)
        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._detail.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._detail.setPlaceholderText("Select an entry above to see its full detail.")
        self._empty = QLabel("No errors so far.")
        copy_one = QPushButton("Copy selected")
        copy_all = QPushButton("Copy all")
        copy_one.clicked.connect(lambda: self._copy(self._detail.toPlainText()))
        copy_all.clicked.connect(lambda: self._copy("\n\n".join(e.full_text for e in self.entries)))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._list)
        splitter.addWidget(self._detail)
        splitter.setSizes([300, 300])
        buttons = QHBoxLayout()
        buttons.addWidget(self._empty, 1)
        buttons.addWidget(copy_one)
        buttons.addWidget(copy_all)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(splitter, 1)

    def add(self, error: StageError, level: str) -> None:
        """Record one error. Never raises: a broken error must still show."""
        try:
            entry = ErrorEntry(level, error.summary, error.full_text)
        except Exception as exc:  # an error object that cannot describe itself
            entry = ErrorEntry(level, f"(unreadable error of type {type(error).__name__}: {exc!r})", repr(error))
        self.entries.append(entry)
        item = QListWidgetItem(entry.line)
        item.setData(_ENTRY_ROLE, len(self.entries) - 1)
        item.setForeground(QBrush(_LEVEL_COLOURS.get(level, _WARNING_COLOUR)))
        self._list.insertItem(0, item)
        count = len(self.entries)
        self._empty.setText(f"{count} {'entry' if count == 1 else 'entries'} this session, newest first.")
        self.count_changed.emit(len(self.entries))

    def _show_detail(self, item: QListWidgetItem | None, _previous=None) -> None:
        self._detail.setPlainText(self.entries[item.data(_ENTRY_ROLE)].full_text if item else "")

    @staticmethod
    def _copy(text: str) -> None:
        if text:
            QGuiApplication.clipboard().setText(text)
