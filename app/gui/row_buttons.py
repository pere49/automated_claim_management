"""RowButton: the small square left of a claim row on the sheet (D36).

Clicking it asks for the row's next amount to be shown. Its fill is the
row's status: green when every amount in the row is verified, else the
worst colour of its amounts; grey (and inert) until the claim is checked.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem


class RowButton(QGraphicsRectItem):
    def __init__(self, row: int, rect: QRectF, on_click: Callable[[int], None]) -> None:
        super().__init__(rect)
        self.row = row                       # the claim row's grid row
        self._on_click = on_click
        self.colour_name = "grey"
        self.enabled = False
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self._hover = False

    def set_colour(self, name: str, colour: QColor, enabled: bool) -> None:
        self.colour_name, self.enabled = name, enabled
        self.setBrush(QBrush(colour))
        self._pen()
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def click(self) -> None:
        """What a mouse click does (tests call it directly)."""
        if self.enabled:
            self._on_click(self.row)

    def mousePressEvent(self, event) -> None:
        if self.enabled and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.click()
        else:
            event.ignore()

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self._pen()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self._pen()

    def _pen(self) -> None:
        pen = QPen(QColor(20, 20, 20) if self._hover and self.enabled else QColor(90, 90, 90), 2 if self._hover else 1)
        pen.setCosmetic(True)
        self.setPen(pen)
