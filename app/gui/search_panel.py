"""SearchPanel: right pane, lower part — the typed search fields.

Stage A: present but not wired. The button stays disabled until Stage B
connects it to the matching module (blueprint section 6). At Stage C this
panel is replaced by the Excel row navigator.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class SearchPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Search this page", parent)
        self.date_or_keyword = QLineEdit()
        self.pin = QLineEdit()
        self.total_amount = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.setEnabled(False)
        self.search_button.setToolTip("Searching is added in the next stage (Stage B).")
        note = QLabel("<i>Not active yet — searching is added in the next stage.</i>")
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Date or keyword", self.date_or_keyword)
        form.addRow("PIN", self.pin)
        form.addRow("Total amount", self.total_amount)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.search_button)
        layout.addWidget(note)
        layout.addStretch(1)
