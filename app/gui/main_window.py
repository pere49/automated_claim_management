"""MainWindow: lays out the panes and wires them to the open document and the claim.

Layout (blueprint section 7, Stage C rework — D38, D41, D42):
    Review tab:  [ files (with the Claim sheet / Receipts slots)
                 | receipts header ("Receipt claim: …", PIN toggle, Auto, Next to check)
                   / receipts (continuous scroll, a badge on every page)
                 | claim sheet ("Claim sheet: …", shown as its PDF, a button per row)
                   / status cards (Verification, TOTAL GRAND, Repeated) ]
    Errors tab:  every structured error of the session

This file only arranges widgets and routes signals between them: the
document's state, cache and OCR thread live in DocumentSession, its pages
prepared for checking in PagePreparer, the claim and its checking in
ClaimSession, the tour in Tour, highlight outlines in highlights.py, what a
checked claim shows on the receipts in claim_presenter.py, and each pane is
its own widget file. A clicked file goes to the Claim sheet slot when it is
one (a PDF whose text holds a claim table), else it opens as the receipts;
right-click chooses explicitly (a scanned claim sheet). Every claimed
amount's highlights stay on its receipt page; scrolling the receipts brings
the page's claim row to the middle of the sheet. (The OCR text and Search
panels were removed at the owner's request, D42.)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (QLabel, QMainWindow, QMessageBox, QProgressBar, QSplitter, QTabWidget, QToolBar,
                               QVBoxLayout, QWidget)

from app.checking import GREEN, ClaimCheck
from app.errors import ERROR, WARNING, StageError
from app.gui.claim_presenter import badges, claim_places, row_of_page
from app.gui.claim_session import ClaimSession
from app.gui.document_session import DocumentSession
from app.gui.error_tab import ErrorTab
from app.gui.file_panel import FilePanel
from app.gui.highlights import HighlightStyle, hit_area, shapes_for
from app.gui.ocr_worker import CANCELLED, FAILED
from app.gui.page_badges import BadgeStyle
from app.gui.page_pane import PagePane
from app.gui.page_preparer import PagePreparer
from app.gui.page_renderer import render_region
from app.gui.receipts_header import ReceiptsHeader
from app.gui.settings import GuiSettings
from app.gui.sheet_view import SheetView
from app.gui.status_cards import StatusCards
from app.gui.tour import Tour
from app.matching import AMOUNT
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
        self._toured_claim = None      # (sheet file, tab, receipts) the tour last started for
        self._style = HighlightStyle(settings.highlight_colours, settings.highlight_fill_alpha,
                                     settings.neighbour_alpha, settings.highlight_line_px)
        self._badge_style = BadgeStyle(settings.badge_font_pt, settings.badge_padding_px)

        self.session = DocumentSession(settings, reader, parent=self)
        self.pages = PagePreparer(self.session, parent=self)
        self.claims = ClaimSession(self.session, self.pages, settings, today, parent=self)
        self.tour = Tour(settings.tour_green_ms, settings.tour_yellow_ms, parent=self)
        self.files = FilePanel(settings.working_folder, settings.file_extensions)
        self.page_pane = PagePane(settings.page_gap_px, settings.render_margin_pages, settings.zoom_step,
                                  settings.min_zoom, settings.max_zoom)
        self.receipts_header = ReceiptsHeader(settings.status_colours)
        self.sheet_view = SheetView(settings, render_region)
        self.status_cards = StatusCards(settings.status_colours, settings.card_tint_alpha, settings.card_value_pt)
        self.errors = ErrorTab()

        receipts = QWidget()
        column = QVBoxLayout(receipts)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.receipts_header)
        column.addWidget(self.page_pane, 1)
        claim = QWidget()
        column = QVBoxLayout(claim)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.sheet_view, 1)
        column.addWidget(self.status_cards)
        review = QSplitter(Qt.Orientation.Horizontal)
        review.addWidget(self.files)
        review.addWidget(receipts)
        review.addWidget(claim)
        review.setStretchFactor(2, 1)
        for i in range(review.count()):     # panes never vanish by dragging; the file list hides via its toggle
            review.setCollapsible(i, False)
        self._review = review
        self._auto_panes = True             # pane sizes follow the window until the officer drags a divider
        review.splitterMoved.connect(self._on_divider_moved)

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
        self.pages.problem.connect(self.report)
        self.claims.sheet_changed.connect(self._on_sheet_changed)
        self.claims.checked.connect(self._on_checked)
        self.claims.waiting.connect(self._on_waiting)
        self.claims.problem.connect(self.report)
        self.sheet_view.item_chosen.connect(self._on_item_chosen)
        self.sheet_view.tab_changed.connect(self._on_tab_changed)
        self.sheet_view.problem.connect(self.report)
        self.receipts_header.pin_switch_changed.connect(self.claims.set_pin_required)
        self.receipts_header.auto_toggled.connect(self._on_auto)
        self.receipts_header.next_to_check.connect(self.tour.next_to_check)
        self.tour.show_item.connect(self._show_item)
        self.tour.running_changed.connect(self.receipts_header.set_auto)
        for area in (self.sheet_view, self.page_pane):
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
        """Start the OCR engine in the background, load the matching and claim
        rules, then fill the file list (which also lets read-ahead begin)."""
        self._set_status("Starting the OCR engine…")
        self.session.start()
        self.pages.start()
        self.claims.start()
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
        self.pages.document_changed()
        self.current_page = 0
        self.page_pane.show_document(self.session.page_sizes, self.session.render)
        self._update_progress()
        if not self.current_page:
            self._on_current_page(self.page_pane.current_page or 1)

    def _on_current_page(self, number: int) -> None:
        """The page mostly in view changed (scrolling, Previous/Next, the tour)."""
        if not 1 <= number <= self.session.page_count:
            return
        self.current_page = number
        self.session.set_viewed_page(number)
        if self.claims.result is not None:
            self.sheet_view.follow_row(row_of_page(self.claims.result, number))

    def _on_page_ready(self, number: int) -> None:
        self._update_progress()
        self.pages.page_arrived(number)

    def _on_finished(self, outcome: str) -> None:
        self._progress.setVisible(False)
        name = self.session.path.name if self.session.path else ""
        read, total = self.session.pages_read(), self.session.page_count
        if outcome == FAILED and read == 0:
            self._set_status(f"Could not read {name} — see the Errors tab.")
        elif outcome == CANCELLED:
            self._set_status(f"Reading {name} was stopped.")
        else:
            failed = self._failed_pages()
            detail = f", {failed} could not be read — see the Errors tab" if failed else ""
            self._set_status(f"{name}: {read} of {total} pages read{detail}.")

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
        self.receipts_header.show_file(self.session.path.name if self.session.path else None)
        names = [p.name for p in (self.claims.sheet_path, self.session.path) if p]
        self.setWindowTitle(f"{' + '.join(names)} — {WINDOW_TITLE}" if names else WINDOW_TITLE)

    # ---------------------------------------------------------------- the claim

    def _on_sheet_changed(self, claim) -> None:
        self.sheet_view.show_claim(claim, self.claims.sheet_index if claim else 0)
        self.tour.set_results(None, restart=True)
        self._update_slots()

    def _on_tab_changed(self, index: int) -> None:
        self.sheet_view.show_sheet(self.claims.claim, index)
        self.claims.set_sheet_index(index)

    def _on_checked(self, result: ClaimCheck | None) -> None:
        self.sheet_view.show_results(result)
        self.status_cards.show_check(result)
        self.receipts_header.show_check(result, available=self.claims.pin_available)
        self.page_pane.set_badges(badges(result, self._settings.status_colours, self._settings.badge_text_colour),
                                  self._badge_style)
        shapes, missing = shapes_for(claim_places(result), self._style)
        self.page_pane.set_highlights(shapes)
        if result is None:
            self.tour.set_results(None, restart=True)
            return
        self.sheet_view.show_message("")
        self.sheet_view.follow_row(row_of_page(result, self.current_page))
        claim = (self.claims.sheet_path, self.claims.sheet_index, self.session.path)
        fresh = claim != self._toured_claim
        if missing and fresh:
            self.report(StageError("display", f"{missing} matched text position(s) could not be placed on the page, "
                                   "so they are not highlighted", file=self.session.path.name), WARNING)
        self.tour.set_results(result.items, restart=fresh)
        items = len(result.items)
        to_check = sum(1 for r in result.items if r.colour != GREEN)
        self._set_status(f"Claim checked: {items} claimed amount{'s' if items != 1 else ''}, "
                         f"{items - to_check} verified, {to_check} to check.")
        if fresh:
            self._toured_claim = claim
            if self._settings.tour_auto_start and result.items:
                self.tour.start()
        elif self.sheet_view.current_item is not None:
            self.sheet_view.select_item(self.sheet_view.current_item)   # the PIN switch changed: outline it again

    def _on_waiting(self, text: str) -> None:
        if self.claims.claim is not None:
            self.sheet_view.show_message(text)
        self._set_status(text)

    def _on_item_chosen(self, item: int) -> None:
        self.tour.chosen(item)
        self._show_item(item)

    def _show_item(self, item: int) -> None:
        result = self.claims.result
        if result is None or not 0 <= item < len(result.items):
            return
        found = result.items[item]
        self.sheet_view.select_item(item)
        it = found.item
        amount = f"{it.amount:,.2f}" if it.amount is not None else "unreadable amount"
        if found.page is None:
            self._set_status(f"{it.column} {amount}: {' · '.join(found.lines)}.")
            return
        self._set_status(f"{it.column} {amount} → page {found.page}: {' · '.join(found.lines) or 'verified'}.")
        area = next((hit_area(h) for h in found.hits if h.key == AMOUNT and hit_area(h)), ())
        if not area:
            area = next((hit_area(h) for h in found.hits if hit_area(h)), ())
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
        if self.receipts_header.auto.isEnabled():
            self.receipts_header.auto.toggle()

    @staticmethod
    def _shortcut(widget: QWidget, key: Qt.Key, slot) -> None:
        shortcut = QShortcut(QKeySequence(key), widget)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(slot)

    # ---------------------------------------------------------------- window

    def _on_error_count(self, count: int) -> None:
        index = self.tabs.indexOf(self.errors)
        self.tabs.setTabText(index, f"Errors ({count})")
        self.tabs.tabBar().setTabTextColor(index, QColor(180, 30, 30))

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._auto_panes:                    # shown, maximised on a small screen, or resized
            QTimer.singleShot(0, self._fit_panes)

    def _fit_panes(self) -> None:
        """The configured pane widths, shared out in proportion to the space the window really has."""
        if not self._auto_panes:
            return
        widths, length = self._settings.pane_widths, self._review.width()
        self._review.blockSignals(True)
        self._review.setSizes([round(w * length / sum(widths)) for w in widths])
        self._review.blockSignals(False)

    def _on_divider_moved(self, *_args) -> None:
        self._auto_panes = False

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
