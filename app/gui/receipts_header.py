"""ReceiptsHeader: above the receipts — which receipts, the PIN toggle, and the tour (D42).

    Receipt claim: cash expense claim form-week-.PDF
    PIN required  [ON ●]                              [▶ Auto] [Next to check]

The PIN toggle is the officer's "PIN required" switch (set by the PIN scan,
D23); when on, its colour is the PIN status (green on every receipt, red
missing somewhere — the pages in its tooltip). Auto and Next to check drive
the tour (D31). The claim's other statuses sit under the claim sheet
(status_cards.py).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.checking import ClaimCheck
from app.gui.toggle_switch import ToggleSwitch


class ReceiptsHeader(QFrame):
    pin_switch_changed = Signal(bool)
    auto_toggled = Signal(bool)
    next_to_check = Signal()

    def __init__(self, colours: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._colours = colours
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.title = QLabel()
        self.title.setWordWrap(False)
        self.pin_label = QLabel("PIN required")
        self.pin_toggle = ToggleSwitch()
        self.pin_toggle.toggled.connect(self.pin_switch_changed)
        self.auto = QPushButton("▶ Auto")
        self.auto.setCheckable(True)
        self.auto.setToolTip("Walk through every claimed amount on its receipt (Space)")
        self.auto.toggled.connect(self._on_auto)
        self.next = QPushButton("Next to check")
        self.next.setToolTip("Jump to the next amount that is not green (N)")
        self.next.clicked.connect(self.next_to_check)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self.pin_label)
        controls.addWidget(self.pin_toggle)
        controls.addStretch(1)
        controls.addWidget(self.auto)
        controls.addWidget(self.next)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(3)
        layout.addWidget(self.title)
        layout.addLayout(controls)
        self.show_file(None)
        self.show_check(None, available=False)

    # ---------------------------------------------------------------- public

    def show_file(self, name: str | None) -> None:
        self.title.setText(f"<b>Receipt claim:</b> {name}" if name else "<b>Receipt claim:</b> —")
        self.title.setToolTip(name or "")

    def show_check(self, result: ClaimCheck | None, available: bool = True) -> None:
        if result is None:
            self.pin_toggle.set_state(False)
            self.pin_toggle.setEnabled(False)
            self.pin_toggle.setToolTip("the claim has not been checked yet")
            for button in (self.auto, self.next):
                button.setEnabled(False)
            return
        self.pin_toggle.set_colours(self._colours[result.pin.colour if result.pin_required else "green"],
                                    self._colours["grey"])
        self.pin_toggle.set_state(result.pin_required)
        self.pin_toggle.setEnabled(available)
        self.pin_toggle.setToolTip(result.pin.detail or result.pin.text)
        for button in (self.auto, self.next):
            button.setEnabled(bool(result.items))

    def set_auto(self, running: bool) -> None:
        self.auto.blockSignals(True)
        self.auto.setChecked(running)
        self.auto.setText("❚❚ Pause" if running else "▶ Auto")
        self.auto.blockSignals(False)

    @property
    def pin_state(self) -> str:
        """The toggle as the officer sees it, e.g. "on: red" (for tests)."""
        if not self.pin_toggle.isChecked():
            return "off"
        colour = next((name for name, value in self._colours.items()
                       if value.lower() == self.pin_toggle._on_colour.name().lower()), "?")
        return f"on: {colour}"

    # ---------------------------------------------------------------- internal

    def _on_auto(self, running: bool) -> None:
        self.set_auto(running)
        self.auto_toggled.emit(running)
