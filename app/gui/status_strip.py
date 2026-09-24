"""StatusStrip: right pane, top — the claim at a glance, kept small (D30, D32).

Three indicators — Verification (green: all verified / yellow: manual check
required), PIN (green: detected / red: not detected on a paired receipt /
grey: not required), Repeated pages (green / yellow / red) — the officer's
"PIN required" switch (set by the PIN scan, D23), and the tour's Auto and
Next to check buttons (D31).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QRadioButton, QVBoxLayout

from app.checking import ClaimCheck


class StatusStrip(QFrame):
    pin_switch_changed = Signal(bool)
    auto_toggled = Signal(bool)
    next_to_check = Signal()

    def __init__(self, colours: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._colours = colours
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.verification, self.pin, self.repeats = QLabel(), QLabel(), QLabel()
        for label in (self.verification, self.pin, self.repeats):
            label.setWordWrap(False)
        self.pin_yes, self.pin_no = QRadioButton("Yes"), QRadioButton("No")
        self._group = QButtonGroup(self)
        self._group.addButton(self.pin_yes)
        self._group.addButton(self.pin_no)
        self.pin_yes.toggled.connect(self._on_switch)
        self.auto = QPushButton("▶ Auto")
        self.auto.setCheckable(True)
        self.auto.setToolTip("Walk through every claimed amount on its receipt (Space)")
        self.auto.toggled.connect(self._on_auto)
        self.next = QPushButton("Next to check")
        self.next.setToolTip("Jump to the next amount that needs a manual check (N)")
        self.next.clicked.connect(self.next_to_check)

        indicators = QHBoxLayout()
        indicators.setSpacing(18)
        indicators.addWidget(self.verification)
        indicators.addWidget(self.pin)
        indicators.addWidget(self.repeats)
        indicators.addStretch(1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("PIN required:"))
        controls.addWidget(self.pin_yes)
        controls.addWidget(self.pin_no)
        controls.addStretch(1)
        controls.addWidget(self.auto)
        controls.addWidget(self.next)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        layout.addLayout(indicators)
        layout.addLayout(controls)
        self.show_check(None, available=False)

    # ---------------------------------------------------------------- public

    def show_check(self, result: ClaimCheck | None, available: bool = True) -> None:
        if result is None:
            for label, name in ((self.verification, "Verification"), (self.pin, "PIN"), (self.repeats, "Repeated pages")):
                label.setText(f"{self._dot('grey')} {name}: —")
            self.set_pin_switch(None, enabled=False)
            for button in (self.auto, self.next):
                button.setEnabled(False)
            return
        self.verification.setText(f"{self._dot(result.verification.colour)} Verification: {result.verification.text}")
        self.pin.setText(f"{self._dot(result.pin.colour)} PIN: {result.pin.text}")
        self.repeats.setText(f"{self._dot(result.repeated_pages.colour)} Repeated pages: {result.repeated_pages.text}")
        self.set_pin_switch(result.pin_required, enabled=available)
        for button in (self.auto, self.next):
            button.setEnabled(bool(result.items))

    def set_pin_switch(self, required: bool | None, enabled: bool) -> None:
        for button in (self.pin_yes, self.pin_no):
            button.blockSignals(True)
        self._group.setExclusive(required is not None)
        self.pin_yes.setChecked(required is True)
        self.pin_no.setChecked(required is False)
        self._group.setExclusive(True)
        for button in (self.pin_yes, self.pin_no):
            button.setEnabled(enabled)
            button.blockSignals(False)

    def set_auto(self, running: bool) -> None:
        self.auto.blockSignals(True)
        self.auto.setChecked(running)
        self.auto.setText("❚❚ Pause" if running else "▶ Auto")
        self.auto.blockSignals(False)

    @property
    def texts(self) -> list[str]:
        """The three indicators as plain text (for tests and copying)."""
        return [label.text().split("</span>")[-1].strip() for label in (self.verification, self.pin, self.repeats)]

    # ---------------------------------------------------------------- internal

    def _dot(self, colour: str) -> str:
        return f"<span style='color:{self._colours[colour]}; font-size:14pt'>●</span>"

    def _on_switch(self, checked: bool) -> None:
        if self.pin_yes.isChecked() or self.pin_no.isChecked():
            self.pin_switch_changed.emit(self.pin_yes.isChecked())

    def _on_auto(self, running: bool) -> None:
        self.set_auto(running)
        self.auto_toggled.emit(running)
