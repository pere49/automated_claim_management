"""ToggleSwitch: an on/off switch — a rounded track with a sliding knob (D42).

Used for "PIN required". When on, the track takes the colour it is given
(the PIN status: green when the company PIN is on every receipt, red when
it is missing somewhere); when off it is grey. "ON" / "OFF" is written in
the track so the state never depends on colour alone. The knob slides.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QWidget

_OFF = QColor("#8c959f")


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_colour = QColor("#1a7f37")
        self._off_colour = _OFF
        self._knob = 0.0                              # 0 = off, 1 = on
        self._slide = QPropertyAnimation(self, b"knob", self)
        self._slide.setDuration(120)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.toggled.connect(self._on_toggled)

    def set_colours(self, on: str, off: str) -> None:
        self._on_colour, self._off_colour = QColor(on), QColor(off)
        self.update()

    def set_state(self, checked: bool) -> None:
        """Set without announcing it (the knob jumps, no slide)."""
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._slide.stop()
        self._knob = 1.0 if checked else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(58, 24)

    def _get_knob(self) -> float:
        return self._knob

    def _set_knob(self, value: float) -> None:
        self._knob = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _on_toggled(self, checked: bool) -> None:
        self._slide.stop()
        self._slide.setStartValue(self._knob)
        self._slide.setEndValue(1.0 if checked else 0.0)
        self._slide.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2
        track = QColor(self._on_colour if self.isChecked() else self._off_colour)
        if not self.isEnabled():
            track.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)
        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(8, int(rect.height() * 0.45)))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 235 if self.isEnabled() else 150))
        knob_size = rect.height() - 4
        if self.isChecked():
            painter.drawText(rect.adjusted(radius * 0.6, 0, -knob_size - 4, 0), Qt.AlignmentFlag.AlignCenter, "ON")
        else:
            painter.drawText(rect.adjusted(knob_size + 4, 0, -radius * 0.6, 0), Qt.AlignmentFlag.AlignCenter, "OFF")
        x = rect.left() + 2 + self._knob * (rect.width() - knob_size - 4)
        painter.setBrush(QColor(255, 255, 255) if self.isEnabled() else QColor(235, 235, 235))
        painter.drawEllipse(QRectF(x, rect.top() + 2, knob_size, knob_size))
