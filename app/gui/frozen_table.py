"""FrozenTable: a table whose first columns stay in view while the rest scroll sideways.

Qt's frozen-column pattern: a second, borderless view of the same model and
the same selection lies over the left edge, showing only the frozen columns;
row heights, column widths and vertical scrolling are kept in step. Used for
the claim sheet so a row's date stays beside its amounts (like Excel's
"freeze panes").
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView


class FrozenTable(QTableView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._count = 0
        self.frozen = QTableView(self)
        self.frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.frozen.verticalHeader().hide()
        self.frozen.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.frozen.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.frozen.setStyleSheet("QTableView { border: none; }")
        self.viewport().stackUnder(self.frozen)
        self.frozen.hide()
        self.horizontalHeader().sectionResized.connect(self._width_changed)
        self.verticalHeader().sectionResized.connect(lambda i, _old, new: self.frozen.setRowHeight(i, new))
        self.frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue)

    def setModel(self, model) -> None:
        super().setModel(model)
        self.frozen.setModel(model)
        self.frozen.setSelectionModel(self.selectionModel())

    def set_frozen_columns(self, count: int) -> None:
        """Keep the first `count` columns in view (call after the model changes)."""
        model = self.model()
        self._count = count if model is not None else 0
        columns = model.columnCount() if model is not None else 0
        for c in range(columns):
            self.frozen.setColumnHidden(c, c >= self._count)
            if c < self._count:
                self.frozen.setColumnWidth(c, self.columnWidth(c))
        for r in range(model.rowCount() if model is not None else 0):
            self.frozen.setRowHeight(r, self.rowHeight(r))
        self.frozen.setVisible(0 < self._count < columns)
        self._place()

    def scrollTo(self, index: QModelIndex, hint=QAbstractItemView.ScrollHint.EnsureVisible) -> None:
        if index.column() >= self._count:        # a frozen cell is always in view
            super().scrollTo(index, hint)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def _width_changed(self, index: int, _old: int, new: int) -> None:
        if index < self._count:
            self.frozen.setColumnWidth(index, new)
            self._place()

    def _place(self) -> None:
        width = sum(self.columnWidth(c) for c in range(self._count))
        self.frozen.setGeometry(self.verticalHeader().width() + self.frameWidth(), self.frameWidth(),
                                width, self.viewport().height() + self.horizontalHeader().height())
