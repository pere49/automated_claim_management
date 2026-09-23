"""MainWindow: lays out the panes and wires them to the open document.

Layout (blueprint section 7, Stage A):
    Review tab:  [ files | page | OCR reading / search fields ]
    Errors tab:  every structured error of the session

This file only arranges widgets and routes signals between them; the
document's state, the cache and the OCR thread live in DocumentSession,
and each pane is its own widget file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QProgressBar, QSplitter, QTabWidget, QToolBar

from app.errors import ERROR, StageError
from app.gui.document_session import DocumentSession
from app.gui.error_tab import ErrorTab
from app.gui.file_panel import FilePanel
from app.gui.ocr_text_panel import OcrTextPanel
from app.gui.ocr_worker import CANCELLED, FAILED
from app.gui.page_pane import PagePane
from app.gui.search_panel import SearchPanel
from app.gui.settings import GuiSettings
from app.ocr import OcrReader

WINDOW_TITLE = "Claim Verifier"


class MainWindow(QMainWindow):
    def __init__(self, settings: GuiSettings, reader: OcrReader | None = None) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self._settings = settings
        self.resize(*settings.window_size)
        self.current_page = 0

        self.session = DocumentSession(settings, reader, parent=self)
        self.files = FilePanel(settings.working_folder, settings.file_extensions)
        self.page_pane = PagePane(settings.zoom_step, settings.min_zoom, settings.max_zoom)
        self.ocr_panel = OcrTextPanel()
        self.search_panel = SearchPanel()
        self.errors = ErrorTab()

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.ocr_panel)
        right.addWidget(self.search_panel)
        right.setSizes(list(settings.right_pane_heights))
        review = QSplitter(Qt.Orientation.Horizontal)
        review.addWidget(self.files)
        review.addWidget(self.page_pane)
        review.addWidget(right)
        review.setSizes(list(settings.pane_widths))
        review.setStretchFactor(1, 1)
        for splitter in (review, right):  # panes never vanish by dragging; the file list hides via its toggle
            for i in range(splitter.count()):
                splitter.setCollapsible(i, False)

        self.tabs = QTabWidget()
        self.tabs.addTab(review, "Review")
        self.tabs.addTab(self.errors, "Errors (0)")
        self.setCentralWidget(self.tabs)

        toolbar = QToolBar("View")
        toolbar.setMovable(False)
        self.toggle_files = QAction("File list", self)
        self.toggle_files.setCheckable(True)
        self.toggle_files.setChecked(True)
        self.toggle_files.setToolTip("Show or hide the list of files")
        self.toggle_files.toggled.connect(self.files.setVisible)
        refresh = QAction("Refresh file list", self)
        refresh.triggered.connect(self.files.refresh)
        toolbar.addAction(self.toggle_files)
        toolbar.addAction(refresh)
        self.addToolBar(toolbar)

        self._status = QLabel()
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(260)
        self._progress.setVisible(False)
        self.statusBar().addWidget(self._status, 1)
        self.statusBar().addPermanentWidget(self._progress)

        self.files.file_chosen.connect(self._on_file_chosen)
        self.files.listed.connect(self.session.set_read_ahead_files)
        self.files.problem.connect(self.report)
        self.page_pane.previous_requested.connect(lambda: self._go_to(self.current_page - 1))
        self.page_pane.next_requested.connect(lambda: self._go_to(self.current_page + 1))
        self.errors.count_changed.connect(self._on_error_count)
        self.session.problem.connect(self.report)
        self.session.engine_ready.connect(lambda: self._set_status("OCR engine ready."))
        self.session.opened.connect(self._on_opened)
        self.session.page_ready.connect(self._on_page_ready)
        self.session.finished.connect(self._on_finished)
        self.session.file_state_changed.connect(self.files.set_state)

    # ---------------------------------------------------------------- public

    def show_fitted(self) -> None:
        """Show at the configured size, or maximized if that does not fit the screen."""
        available = self.screen().availableGeometry()
        width, height = self._settings.window_size
        if width > available.width() or height > available.height():
            self.showMaximized()
        else:
            self.show()

    def start(self) -> None:
        """Start the OCR engine in the background, then fill the file list
        (which also lets read-ahead begin)."""
        self._set_status("Starting the OCR engine…")
        self.session.start()
        self.files.refresh()

    def report(self, error: StageError, level: str = ERROR) -> None:
        """Send one structured error to the Errors tab."""
        self.errors.add(error, level)
        self._set_status(f"New {level} recorded — see the Errors tab.")

    def confirm(self, title: str, text: str) -> bool:
        """Ask the officer a yes/no question; separate so tests can answer it."""
        answer = QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    # ---------------------------------------------------------------- files and pages

    def _on_file_chosen(self, path: Path) -> None:
        """Switching files loses nothing: every reading stays in the cache."""
        if path == self.session.path:
            return
        self.current_page = 0
        if not self.session.open(path):
            self.files.mark_open(self.session.path)
            self._set_status(f"Could not open {path.name} — see the Errors tab.")
            return
        self.files.mark_open(path)
        self.setWindowTitle(f"{path.name} — {WINDOW_TITLE}")

    def _on_opened(self, page_count: int) -> None:
        self._update_progress()
        self._go_to(1)

    def _on_page_ready(self, number: int) -> None:
        self._update_progress()
        if number == self.current_page:
            self._show_ocr(number)

    def _on_finished(self, outcome: str) -> None:
        self._progress.setVisible(False)
        name = self.session.path.name if self.session.path else ""
        read, total = self.session.pages_read(), self.session.page_count
        if outcome == FAILED and read == 0:
            self.ocr_panel.show_message("This file could not be read — see the Errors tab.")
            self._set_status(f"Could not read {name}.")
            return
        if outcome == CANCELLED:
            self._set_status(f"Reading {name} was stopped.")
        else:
            failed = self._failed_pages()
            detail = f", {failed} could not be read — see the Errors tab" if failed else ""
            self._set_status(f"{name}: {read} of {total} pages read{detail}.")
        if self.current_page:
            self._show_ocr(self.current_page)

    def _go_to(self, number: int) -> None:
        total = self.session.page_count
        if not 1 <= number <= total:
            return
        self.current_page = number
        self.session.set_viewed_page(number)
        try:
            pixmap = self.session.render(number)
        except StageError as exc:
            self.report(exc)
            self.page_pane.show_message(f"Page {number} could not be displayed — see the Errors tab.")
        else:
            self.page_pane.show_page(pixmap, number, total)
        self._show_ocr(number)

    def _show_ocr(self, number: int) -> None:
        self.ocr_panel.show_page(number, self.session.page_count, self.session.reading(number), self.session.busy)

    def _update_progress(self) -> None:
        busy = self.session.busy
        self._progress.setVisible(busy)
        if busy:
            read, total = self.session.pages_read(), self.session.page_count
            self._progress.setRange(0, total)
            self._progress.setValue(read)
            self._set_status(f"Reading {self.session.path.name}: {read} of {total} pages done…")

    def _failed_pages(self) -> int:
        doc = self.session.current
        return sum(1 for p in doc.pages.values() if p.result.error is not None) if doc else 0

    # ---------------------------------------------------------------- window

    def _on_error_count(self, count: int) -> None:
        index = self.tabs.indexOf(self.errors)
        self.tabs.setTabText(index, f"Errors ({count})")
        self.tabs.tabBar().setTabTextColor(index, QColor(180, 30, 30))

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        kept = self.session.cache.files_with_readings()
        if kept and not self.confirm(
                "Close the application?",
                f"The OCR readings of {kept} file{'s' if kept != 1 else ''} are kept only while the application "
                "is open. Closing discards them (nothing is saved to disk), and they will be read again next time."
                "\n\nClose anyway?"):
            event.ignore()
            return
        self._set_status("Closing…")
        self.session.shutdown()
        event.accept()
