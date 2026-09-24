"""StatusCards: under the claim sheet — the claim at a glance, three cards (D42).

    ┃ VERIFICATION      ┃ TOTAL GRAND            ┃ REPEATED
    ┃ p. 1, 3, 4        ┃ Not matched            ┃ None
    ┃ 1 no receipt      ┃ 4,570.00 of 4,900.00   ┃

Each card: a bar and a light tint in its status colour (green, yellow, red;
grey until the claim is checked), the title in capitals, the status in large
words, one small line with the figures (D42 "3a"), and the details in the
tooltip. Verification names the receipt pages that failed (D38), TOTAL GRAND
is the one Total status (D37), Repeated the repeated pages (D29). Words that
do not fit shrink with "…" rather than squeeze the sheet.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from app.checking import ClaimCheck, Status
from app.gui.elided_label import ElidedLabel

_WAITING = Status("grey", "—", "the claim has not been checked yet")


class _Card(QFrame):
    def __init__(self, title: str, value_pt: float, tint_alpha: int, colours: dict[str, str]) -> None:
        super().__init__()
        self.setObjectName("card")
        self._alpha, self._colours = tint_alpha, colours
        self.title = QLabel(title.upper())
        font = self.title.font()
        font.setBold(True)
        font.setPointSizeF(max(6.0, font.pointSizeF() * 0.85))
        font.setLetterSpacing(font.SpacingType.PercentageSpacing, 108)
        self.title.setFont(font)
        self.value = ElidedLabel(value_pt, bold=True)
        self.note = ElidedLabel(max(6.0, self.title.font().pointSizeF()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 5, 8, 5)
        layout.setSpacing(0)
        for label in (self.title, self.value, self.note):
            label.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(label)
        self.status = _WAITING
        self.show_status(_WAITING)

    def show_status(self, status: Status) -> None:
        self.status = status
        colour = QColor(self._colours[status.colour])
        tint = QColor(colour)
        tint.setAlpha(self._alpha)
        self.setStyleSheet(
            f"QFrame#card {{ background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, {tint.alpha()}); "
            f"border-left: 6px solid {colour.name()}; border-radius: 5px; }}")
        self.title.setStyleSheet(f"background: transparent; border: none; color: {colour.darker(130).name()};")
        text = status.text if status.text.startswith("p. ") else status.text[:1].upper() + status.text[1:]
        self.value.set_full(text)
        self.note.set_full(status.note)
        self.setToolTip(status.detail or text)


class StatusCards(QFrame):
    def __init__(self, colours: dict[str, str], tint_alpha: int, value_pt: float, parent=None) -> None:
        super().__init__(parent)
        self.verification = _Card("Verification", value_pt, tint_alpha, colours)
        self.total = _Card("Total grand", value_pt, tint_alpha, colours)
        self.repeats = _Card("Repeated", value_pt, tint_alpha, colours)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        layout.addWidget(self.verification, 3)
        layout.addWidget(self.total, 3)
        layout.addWidget(self.repeats, 2)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def show_check(self, result: ClaimCheck | None) -> None:
        if result is None:
            for card in (self.verification, self.total, self.repeats):
                card.show_status(_WAITING)
            return
        self.verification.show_status(result.verification)
        self.total.show_status(result.total)
        self.repeats.show_status(result.repeated_pages)

    @property
    def texts(self) -> dict[str, str]:
        """Each card's colour, words and small line, e.g. {"Total grand": "red: Not matched | 4,570.00 of …"}."""
        return {card.title.text().capitalize(): f"{card.status.colour}: {card.status.text}"
                                                 + (f" | {card.status.note}" if card.status.note else "")
                for card in (self.verification, self.total, self.repeats)}
