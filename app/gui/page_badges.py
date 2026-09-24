"""Page badges: the solid label in each receipt page's top-right corner (D35).

A badge says what the page shows wrong for its claimed amount ("Date 09 Aug
≠ 10 Aug", "PIN missing", "Repeated p. 3") or ✓, filled in the page's
status colour. It is drawn at a fixed size on screen whatever the zoom, and
anchored to the page's top-right corner so it scrolls with its page.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QGraphicsItem


@dataclass(frozen=True)
class Badge:
    page: int
    lines: tuple[str, ...]
    fill: QColor
    text: QColor


@dataclass(frozen=True)
class BadgeStyle:
    font_pt: int
    padding_px: int


class BadgeItem(QGraphicsItem):
    """One badge; its position is its top-right corner."""

    def __init__(self, badge: Badge, style: BadgeStyle) -> None:
        super().__init__()
        self.badge = badge
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self._font = QFont()
        self._font.setPointSize(style.font_pt)
        self._font.setBold(True)
        metrics = QFontMetricsF(self._font)
        self._pad = style.padding_px
        self._line_height = metrics.height()
        self._ascent = metrics.ascent()
        width = max((metrics.horizontalAdvance(line) for line in badge.lines), default=0) + 2 * self._pad
        height = self._line_height * max(1, len(badge.lines)) + 2 * self._pad
        self._rect = QRectF(-width, 0, width, height)
        self.setToolTip("\n".join(badge.lines))

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.badge.fill)
        painter.drawRoundedRect(self._rect, 3, 3)
        painter.setPen(self.badge.text)
        painter.setFont(self._font)
        for i, line in enumerate(self.badge.lines):
            painter.drawText(QPointF(self._rect.left() + self._pad, self._pad + self._ascent + i * self._line_height),
                             line)
