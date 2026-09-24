"""MainWindow: lays out the panes and wires them to the open document and the claim.

Layout (blueprint section 7, Stage C — D32):
    Review tab:  [ files (with the Claim sheet / Receipts slots)
                 | receipts (continuous scroll)
                 | status strip (small) / claim sheet (most of the height) / OCR text | Search tabs ]
    Errors tab:  every structured error of the session

This file only arranges widgets and routes signals between them: the
document's state, cache and OCR thread live in DocumentSession, the claim
and its checking in ClaimSession, searching in SearchController, the tour in
Tour, highlight outlines in highlights.py, and each pane is its own widget
file. A clicked file goes to the Claim sheet slot when it is one (an Excel
file, or a PDF whose text holds a claim table), else it opens as the
receipts; right-click chooses explicitly (a scanned claim sheet).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QLabel, QMainWindow, QMessageBox, QProgressBar, QSplitter, QTabWidget, QToolBar,
                               QWidget)

from app.checking import ClaimCheck
from app.errors import ERROR, WARNING, StageError
from app.gui.claim_session import ClaimSession
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
from app.gui.sheet_grid import SheetGrid
from app.gui.status_strip import StatusStrip
from app.gui.tour import Tour
from app.matching import AMOUNT, QueryError
from app.ocr import OcrReader

WINDOW_TITLE = "Claim Verifier"


class MainWindow(QMainWindow):
    def __init__(self, settings: GuiSettings, reader: OcrReader | None = None,
                 today: Callable[[], date] = date.today) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self._settings = settings
        self.resize(*settings.window_size)
        self.current_page = 0
        self._places: list = []        # every search hit in page order, for Previous / Next match
        self._place = -1
        self._toured_claim = None      # (sheet file, tab, receipts) the tour last started for
        self._style = HighlightStyle(settings.highlight_colours, settings.highlight_fill_alpha,
                                     settings.neighbour_alpha, settings.highlight_line_px)

        self.session = DocumentSession(settings, reader, parent=self)
        self.search = SearchController(self.session, parent=self)
        self.claims = ClaimSession(self.session, self.search, settings, today, parent=self)
        self.tour = Tour(settings.tour_green_ms, settings.tour_yellow_ms, parent=self)
        self.files = FilePanel(settings.working_folder, settings.file_extensions)
        self.page_pane = PagePane(settings.page_gap_px, settings.render_margin_pages, settings.zoom_step,
                                  settings.min_zoom, settings.max_zoom)
        self.status_strip = StatusStrip(settings.status_colours)
        self.sheet_grid = SheetGrid(settings.cell_colours, settings.status_colours, settings.sheet_column_max_px)
        self.ocr_panel = OcrTextPanel()
        self.search_panel = SearchPanel(settings.highlight_colours)
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.addTab(self.ocr_panel, "OCR text")
        self.bottom_tabs.addTab(self.search_panel, "Search")
        self.errors = ErrorTab()

        right = QSplitter(Qt.Orientation.Vertical)
        for widget in (self.status_strip, self.sheet_grid, self.bottom_tabs):
            right.addWidget(widget)
        right.setSizes(list(settings.right_pane_heights))
        right.setStretchFactor(1, 1)
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

        self.files.file_chosen.connect(self._on_file_clicked)
        self.files.sheet_requested.connect(self._use_as_sheet)
        self.files.receipts_requested.connect(self._on_file_chosen)
        self.files.sheet_cleared.connect(self.claims.clear_sheet)
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
        self.claims.sheet_changed.connect(self._on_sheet_changed)
        self.claims.checked.connect(self._on_checked)
        self.claims.waiting.connect(self._on_waiting)
        self.claims.problem.connect(self.report)
        self.sheet_grid.item_selected.connect(self._on_item_chosen)
        self.sheet_grid.tab_changed.connect(self._on_tab_changed)
        self.status_strip.pin_switch_changed.connect(self.claims.set_pin_required)
        self.status_strip.auto_toggled.connect(self._on_auto)
        self.status_strip.next_to_check.connect(self.tour.next_to_check)
        self.tour.show_item.connect(self._show_item)
        self.tour.running_changed.connect(self.status_strip.set_auto)
        for area in (self.sheet_grid, self.page_pane):    # never inside the typing fields
            self._shortcut(area, Qt.Key.Key_Space, self._toggle_auto)
            self._shortcut(area, Qt.Key.Key_N, self.tour.next_to_check)

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
        """Start the OCR engine in the background, load the search and claim
        rules, then fill the file list (which also lets read-ahead begin)."""
        self._set_status("Starting the OCR engine…")
        self.session.start()
        self.search.start()
        self.claims.start()
        self.search_panel.set_available(self.search.available)
        self.files.refresh()
        self._update_slots()

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

    def _on_file_clicked(self, path: Path) -> None:
        if self.claims.is_claim_sheet(path):
            self._use_as_sheet(path)
        else:
            self._on_file_chosen(path)

    def _use_as_sheet(self, path: Path) -> None:
        if path != self.claims.sheet_path:
            self.claims.set_sheet(path)
        self._update_slots()

    def _on_file_chosen(self, path: Path) -> None:
        """The receipts. Switching files loses nothing: every reading stays in the cache."""
        if path == self.session.path:
            return
        if not self.session.open(path):
            self.files.mark_open(self.session.path)
            self._set_status(f"Could not open {path.name} — see the Errors tab.")
            return
        self.files.mark_open(path)
        self._update_slots()

    def _on_opened(self, page_count: int) -> None:
        self.search.document_changed()
        self.current_page = 0
        self.page_pane.show_document(self.session.page_sizes, self.session.render)
        self._update_progress()
        if not self.current_page:
            self._on_current_page(self.page_pane.current_page or 1)

    def _on_current_page(self, number: int) -> None:
        """The page mostly in view changed (scrolling, Previous/Next, a search, the tour)."""
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

    def _update_slots(self) -> None:
        self.files.set_slots(self.claims.sheet_path, self.session.path)
        names = [p.name for p in (self.claims.sheet_path, self.session.path) if p]
        self.setWindowTitle(f"{' + '.join(names)} — {WINDOW_TITLE}" if names else WINDOW_TITLE)

    # ---------------------------------------------------------------- the claim

    def _on_sheet_changed(self, claim) -> None:
        self.sheet_grid.show_claim(claim, self.claims.sheet_index if claim else 0)
        self.tour.set_results(None, restart=True)
        self._update_slots()

    def _on_tab_changed(self, index: int) -> None:
        self.sheet_grid.show_sheet(self.claims.claim, index)
        self.claims.set_sheet_index(index)

    def _on_checked(self, result: ClaimCheck | None) -> None:
        self.sheet_grid.show_results(result)
        self.status_strip.show_check(result, available=self.claims.pin_available)
        if result is None:
            self.tour.set_results(None, restart=True)
            return
        claim = (self.claims.sheet_path, self.claims.sheet_index, self.session.path)
        fresh = claim != self._toured_claim
        self.tour.set_results(result.items, restart=fresh)
        items = len(result.items)
        to_check = sum(1 for r in result.items if r.colour != "green")
        self._set_status(f"Claim checked: {items} claimed amount{'s' if items != 1 else ''}, "
                         f"{items - to_check} verified, {to_check} to check.")
        if fresh:
            self._toured_claim = claim
            if self._settings.tour_auto_start and result.items:
                self.tour.start()
        elif self.sheet_grid.current_item is not None:
            self._show_item(self.sheet_grid.current_item)   # the PIN switch changed: redraw this amount

    def _on_waiting(self, text: str) -> None:
        self.sheet_grid.show_waiting(text)
        self._set_status(text)

    def _on_item_chosen(self, item: int) -> None:
        self.tour.chosen(item)
        self._show_item(item)

    def _show_item(self, item: int) -> None:
        result = self.claims.result
        if result is None or not 0 <= item < len(result.items):
            return
        found = result.items[item]
        self.sheet_grid.select_item(item)
        if found.page is None:
            self.page_pane.set_highlights([])
            return
        shapes, missing = shapes_for([(found.page, hit) for hit in found.hits], self._style)
        self.page_pane.set_highlights(shapes)
        self._places, self._place = [], -1       # the search's highlights are replaced
        area = next((hit_area(h) for h in found.hits if h.key == AMOUNT and hit_area(h)), ())
        if area:
            self.page_pane.show_area(found.page, area)
        else:
            self.page_pane.go_to_page(found.page)

    def _on_auto(self, running: bool) -> None:
        if running:
            self.tour.start()
        else:
            self.tour.pause()

    def _toggle_auto(self) -> None:
        if self.status_strip.auto.isEnabled():
            self.status_strip.auto.toggle()

    @staticmethod
    def _shortcut(widget: QWidget, key: Qt.Key, slot) -> None:
        shortcut = QShortcut(QKeySequence(key), widget)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(slot)

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
        self.tour.pause()
        self.session.shutdown()
        event.accept()
