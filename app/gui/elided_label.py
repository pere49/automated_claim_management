"""ElidedLabel: plain words that shrink with "…" when there is no room, never widening their pane.

A long list of receipt pages once squeezed the claim sheet (2026-09-24); the
whole text stays available (the caller puts it in a tooltip).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    def __init__(self, point_size: float | None = None, bold: bool = False) -> None:
        super().__init__()
        font = self.font()
        if point_size:
            font.setPointSizeF(point_size)
        font.setBold(bold)
        self.setFont(font)
        self._full = ""

    @property
    def full_text(self) -> str:
        return self._full

    def set_full(self, text: str) -> None:
        self._full = text
        self.updateGeometry()
        self._elide()

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 4, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance("…") + 4, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, self.width() - 2)))
