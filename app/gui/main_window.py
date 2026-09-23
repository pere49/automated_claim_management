"""MainWindow: lays out the panes and wires them to the open document.

Layout (blueprint section 7, Stage B):
    Review tab:  [ files | document (continuous scroll) | OCR reading / search ]
    Errors tab:  every structured error of the session

This file only arranges widgets and routes signals between them: the
document's state, cache and OCR thread live in DocumentSession, searching in
SearchController, highlight outlines in highlights.py, and each pane is its
own widget file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QProgressBar, QSplitter, QTabWidget, QToolBar

from app.errors import ERROR, WARNING, StageError
from app.gui.document_session import DocumentSession
from app.gui.error_tab import ErrorTab
from app.gui.file_panel import FilePanel
from app.gui.highlights import HighlightStyle, hit_area, shapes_for
from app.gui.ocr_text_panel import OcrTextPanel
from app.gui.ocr_worker import CANCELLED, FAILED
from app.gui.page_pane import PagePane
from app.gui.search_controller import SearchController, SearchOutcome
from app.gui.search_panel import SearchPanel
from app.gui.search_summary import summarise
from app.gui.settings import GuiSettings
from app.matching import QueryError
from app.ocr import OcrReader

WINDOW_TITLE = "Claim Verifier"


class MainWindow(QMainWindow):
    def __init__(self, settings: GuiSettings, reader: OcrReader | None = None) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self._settings = settings
        self.resize(*settings.window_size)
        self.current_page = 0
        self._places: list = []        # every search hit in page order, for Previous / Next match
        self._place = -1
        self._style = HighlightStyle(settings.highlight_colours, settings.highlight_fill_alpha,
                                     settings.neighbour_alpha, settings.highlight_line_px)

        self.session = DocumentSession(settings, reader, parent=self)
        self.search = SearchController(self.session, parent=self)
        self.files = FilePanel(settings.working_folder, settings.file_extensions)
        self.page_pane = PagePane(settings.page_gap_px, settings.render_margin_pages, settings.zoom_step,
                                  settings.min_zoom, settings.max_zoom)
        self.ocr_panel = OcrTextPanel()
        self.search_panel = SearchPanel(settings.highlight_colours)
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
        self.page_pane.current_page_changed.connect(self._on_current_page)
        self.page_pane.problem.connect(self.report)
        self.errors.count_changed.connect(self._on_error_count)
        self.session.problem.connect(self.report)
        self.session.engine_ready.connect(lambda: self._set_status("OCR engine ready."))
        self.session.opened.connect(self._on_opened)
        self.session.page_ready.connect(self._on_page_ready)
        self.session.finished.connect(self._on_finished)
        self.session.file_state_changed.connect(self.files.set_state)
        self.search.updated.connect(self._on_search_updated)
        self.search.cleared.connect(self._on_search_cleared)
        self.search.problem.connect(self.report)
        self.search_panel.search_requested.connect(self._on_search_requested)
        self.search_panel.clear_requested.connect(self._on_clear_requested)
        self.search_panel.next_match.connect(lambda: self._step_match(+1))
        self.search_panel.previous_match.connect(lambda: self._step_match(-1))

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
        """Start the OCR engine in the background, load the search rules, then
        fill the file list (which also lets read-ahead begin)."""
        self._set_status("Starting the OCR engine…")
        self.session.start()
        self.search.start()
        self.search_panel.set_available(self.search.available)
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
        if not self.session.open(path):
            self.files.mark_open(self.session.path)
            self._set_status(f"Could not open {path.name} — see the Errors tab.")
            return
        self.files.mark_open(path)
        self.setWindowTitle(f"{path.name} — {WINDOW_TITLE}")

    def _on_opened(self, page_count: int) -> None:
        self.search.document_changed()
        self.current_page = 0
        self.page_pane.show_document(self.session.page_sizes, self.session.render)
        self._update_progress()
        if not self.current_page:
            self._on_current_page(self.page_pane.current_page or 1)

    def _on_current_page(self, number: int) -> None:
        """The page mostly in view changed (scrolling, Previous/Next, a search)."""
        if not 1 <= number <= self.session.page_count:
            return
        self.current_page = number
        self.session.set_viewed_page(number)
        self._show_ocr(number)

    def _on_page_ready(self, number: int) -> None:
        self._update_progress()
        if number == self.current_page:
            self._show_ocr(number)
        self.search.page_arrived(number)

    def _on_finished(self, outcome: str) -> None:
        self._progress.setVisible(False)
        name = self.session.path.name if self.session.path else ""
        read, total = self.session.pages_read(), self.session.page_count
        if outcome == FAILED and read == 0:
            self.ocr_panel.show_message("This file could not be read — see the Errors tab.")
            self._set_status(f"Could not read {name}.")
        elif outcome == CANCELLED:
            self._set_status(f"Reading {name} was stopped.")
        else:
            failed = self._failed_pages()
            detail = f", {failed} could not be read — see the Errors tab" if failed else ""
            self._set_status(f"{name}: {read} of {total} pages read{detail}.")
        if self.current_page:
            self._show_ocr(self.current_page)
        self.search.refresh()

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

    # ---------------------------------------------------------------- search

    def _on_search_requested(self) -> None:
        if not self.session.has_document:
            self.search_panel.show_message("Open a file first.")
            return
        try:
            query = self.search.build_query(*self.search_panel.values())
        except QueryError as exc:
            self.search_panel.show_message(str(exc)[:1].upper() + str(exc)[1:] + ".")
            return
        self.search.run(query)

    def _on_clear_requested(self) -> None:
        self.search_panel.reset_fields()
        self.search.clear()

    def _on_search_updated(self, outcome: SearchOutcome) -> None:
        had_page = bool(self._places)
        self.search_panel.show_summary(summarise(outcome))
        self._places = outcome.matches.places()
        shapes, missing = shapes_for(self._places, self._style)
        self.page_pane.set_highlights(shapes)
        if missing and outcome.first:
            self.report(StageError("display", f"{missing} matched text position(s) could not be placed on the "
                                   "page, so they are not highlighted", file=self.session.path.name), WARNING)
        best = outcome.matches.best_page
        if best is not None and (outcome.first or not had_page):
            self._place = next(i for i, (page, _) in enumerate(self._places) if page == best)
            self._show_place()
        elif not self._places:
            self._place = -1
        self.search_panel.set_match_position(self._place + 1 if self._places else 0, len(self._places))

    def _on_search_cleared(self) -> None:
        self._places, self._place = [], -1
        self.page_pane.set_highlights([])
        self.search_panel.show_cleared()

    def _step_match(self, step: int) -> None:
        if not self._places:
            return
        self._place = (self._place + step) % len(self._places)
        self._show_place()
        self.search_panel.set_match_position(self._place + 1, len(self._places))

    def _show_place(self) -> None:
        page, hit = self._places[self._place]
        area = hit_area(hit)
        if area:
            self.page_pane.show_area(page, area)
        else:
            self.page_pane.go_to_page(page)

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
