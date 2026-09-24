"""The claim sheet's overlay: where rows and cells fall on its cropped picture, and the marks drawn there.

Positions come from the claim reader as fractions of the page (SheetPlace);
Frame turns them into the scene coordinates of the picture cropped to
`crop`. The marks: an amount's tint in its status colour, the "No receipt
found" label, and the blue outline of the row in view and of the amount
shown (D36, D39).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsSimpleTextItem

from app.claims import Box


@dataclass(frozen=True)
class Frame:
    """Page fractions -> scene coordinates of a picture of the page cropped to `crop`."""
    crop: Box
    width: float                 # the picture's size in scene units
    height: float

    def rect(self, box: Box) -> QRectF:
        left, top = self._point(box.left, box.top)
        right, bottom = self._point(box.right, box.bottom)
        return QRectF(QPointF(left, top), QPointF(right, bottom))

    def _point(self, fx: float, fy: float) -> tuple[float, float]:
        c = self.crop
        return ((fx - c.left) / (c.right - c.left) * self.width, (fy - c.top) / (c.bottom - c.top) * self.height)


def crop_box(printed: Box, margin: float) -> Box:
    return Box(max(0.0, printed.left - margin), max(0.0, printed.top - margin), min(1.0, printed.right + margin),
               min(1.0, printed.bottom + margin))


def tint(rect: QRectF, colour: str, alpha: int) -> QGraphicsRectItem:
    fill = QColor(colour)
    fill.setAlpha(alpha)
    item = QGraphicsRectItem(rect)
    item.setBrush(QBrush(fill))
    item.setPen(QPen(Qt.PenStyle.NoPen))
    return item


def label(cell: QRectF, text: str, colour: str, height: float) -> QGraphicsItem:
    """Small text on a light backing, right-aligned on the cell and centred on its row."""
    item = QGraphicsSimpleTextItem(text)
    font = QFont()
    font.setPixelSize(max(4, int(height)))
    font.setBold(True)
    item.setFont(font)
    item.setBrush(QBrush(QColor(colour)))
    box = item.boundingRect()
    pad = height * 0.2
    back = QGraphicsRectItem(QRectF(0, 0, box.width() + 2 * pad, box.height()))
    back.setBrush(QBrush(QColor(255, 255, 255, 215)))
    back.setPen(QPen(Qt.PenStyle.NoPen))
    item.setParentItem(back)
    item.setPos(pad, 0)
    back.setPos(cell.right() - back.rect().width(), cell.center().y() - box.height() / 2)
    return back


def outline(rect: QRectF, colour: str, width: int) -> QGraphicsRectItem:
    item = QGraphicsRectItem(rect)
    pen = QPen(QColor(colour), width)
    pen.setCosmetic(True)
    item.setPen(pen)
    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    return item
