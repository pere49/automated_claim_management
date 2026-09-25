"""OcrTextPanel: right pane, upper part — what OCR read on the open page.

Shows the page's text grouped into printed rows (app/layout), one row per
line, in a fixed-width font so it can be compared with the page by eye.
A status line above it says how the page was read. Stage A only: at
Stage D this panel is removed (blueprint section 7).
"""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from app.gui.document_cache import PageReading


class OcrTextPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("<b>OCR reading</b>")
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._title)
        layout.addWidget(self._status)
        layout.addWidget(self._text, 1)
        self.show_message("No document open.")

    @property
    def text(self) -> str:
        return self._text.toPlainText()

    @property
    def status(self) -> str:
        return self._status.text()

    def show_message(self, message: str) -> None:
        self._title.setText("<b>OCR reading</b>")
        self._status.setText(message)
        self._text.clear()

    def show_page(self, number: int, total: int, state: PageReading | None, still_reading: bool) -> None:
        self._title.setText(f"<b>OCR reading</b> — page {number} of {total}")
        if state is None:
            self._status.setText("Being read — this page is next; its text appears here when ready."
                                 if still_reading else "This page has not been read.")
            self._text.clear()
            return
        result = state.result
        if result.error is not None:
            self._status.setText("This page could not be read — see the Errors tab.")
            self._text.clear()
            return

        rows = state.rows or []
        parts = [f"{len(result.words)} text segments in {len(rows)} rows",
                 f"read in {result.seconds:.1f} s",
                 "processing applied: " + (", ".join(result.used_steps) if result.used_steps else "none")]
        notes = []
        if result.warning is not None:
            notes.append("Page preparation failed, so it was read unprocessed — see the Errors tab.")
        if not state.rows_grouped:
            notes.append("Rows could not be grouped: one segment per line, in engine order — see the Errors tab.")
        if not result.words:
            notes.append("No text was found on this page.")
        self._status.setText(" · ".join(parts) + ("\n" + "\n".join(notes) if notes else ""))
        self._text.setPlainText("\n".join(row.text for row in rows))
