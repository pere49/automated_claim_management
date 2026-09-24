"""DocumentSession: the open PDF, the OCR thread, and the cache behind them.

Owns the background OCR thread and the DocumentCache. Opening a file shows
it at once (pages are rendered on demand by page_renderer.py) and asks the
worker to read only the pages the cache does not already hold, the page on
screen first. Every page read is stored in the cache, whichever file it
belongs to, so switching files never loses finished work; the cache lasts
until the application closes.

Read-ahead (gui_settings.json "read_ahead"): when nothing else needs the
OCR engine, the other files in the working folder are read in the
background, in list order, so they are ready when opened. Opening a file
always takes over from read-ahead (after the page being read finishes).
A file whose reading ran to an end (even with failed pages) is not read
ahead again this run, so a broken file is never retried in a loop; opening
it retries its failed pages. An interrupted read-ahead is resumed later.

Background requests (Stage C): a scanned claim sheet must be read by OCR
while the receipts stay open. request_reading(path) puts it before any
read-ahead (read-ahead switched on or not); document_done(path) says when a
file's reading has run to an end, whichever file it is.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot

from app.errors import ERROR, WARNING, StageError
from app.gui import page_renderer
from app.gui.document_cache import CachedDocument, DocumentCache, PageReading, file_key
from app.gui.ocr_worker import CANCELLED, FAILED, FINISHED, OcrWorker
from app.gui.settings import GuiSettings
from app.layout import RowRules, TextRow, group_rows, load_row_rules, ungrouped_rows
from app.ocr import OcrReader, PageResult


class DocumentSession(QObject):
    engine_ready = Signal()
    opened = Signal(int)            # page count of the newly opened document
    page_ready = Signal(int)        # 1-based page number of the open document whose reading has arrived
    finished = Signal(str)          # FINISHED | CANCELLED | FAILED, for the open document
    file_state_changed = Signal(object, str)   # path, short state text for the file list
    problem = Signal(object, str)   # StageError, ERROR | WARNING
    document_done = Signal(object)  # path of any file whose reading ran to an end (even with failed pages)

    _warm_up = Signal()
    _read = Signal(int, str, object)

    def __init__(self, settings: GuiSettings, reader: OcrReader | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._row_rules: RowRules | None = None
        self.cache = DocumentCache()
        self.current: CachedDocument | None = None
        self._job = 0
        self._jobs: dict[int, CachedDocument] = {}
        self._running: CachedDocument | None = None   # document the latest job is reading
        self._candidates: list[Path] = []
        self._requested: list[Path] = []                # read in the background before any read-ahead
        self._awaited: set[Path] = set()                # requested and not yet read to an end
        self._read_ahead_done: set = set()             # FileKeys whose reading ran to an end this run
        self._stopped = False

        self._thread = QThread()
        self._thread.setObjectName("ocr-worker")
        self._worker = OcrWorker(settings.pdf_render_dpi, reader)
        self._worker.moveToThread(self._thread)
        self._warm_up.connect(self._worker.warm_up)
        self._read.connect(self._worker.read_document)
        self._worker.engine_ready.connect(self.engine_ready)
        self._worker.document_counted.connect(self._on_counted)
        self._worker.page_read.connect(self._on_page_read)
        self._worker.job_done.connect(self._on_job_done)
        self._worker.problem.connect(self.problem)
        self._thread.start()
        app = QCoreApplication.instance()
        if app is not None:  # also stop cleanly when the application quits without the window closing
            app.aboutToQuit.connect(self.shutdown)

    # ---------------------------------------------------------------- public

    def start(self) -> None:
        """Load the row rules and start the OCR engine in the background.
        Call once, after the window has connected to `problem`."""
        try:
            self._row_rules = load_row_rules()
        except StageError as exc:
            self.problem.emit(exc, ERROR)
        self._warm_up.emit()

    @property
    def has_document(self) -> bool:
        return self.current is not None

    @property
    def path(self) -> Path | None:
        return self.current.path if self.current else None

    @property
    def page_count(self) -> int:
        return (self.current.page_count or 0) if self.current else 0

    @property
    def busy(self) -> bool:
        """The open document is being read."""
        return self.current is not None and self._running is self.current

    def reading(self, number: int) -> PageReading | None:
        return self.current.pages.get(number) if self.current else None

    def pages_read(self) -> int:
        return self.current.pages_read if self.current else 0

    def open(self, path: Path) -> bool:
        """Show `path` and read whatever the cache lacks. False (and a
        reported problem) if the file cannot be opened at all."""
        try:
            key = file_key(path)
            doc = self.cache.get_or_create(key)
            doc.page_sizes = page_renderer.page_sizes(path, self._settings.pdf_render_dpi)
            doc.page_count = len(doc.page_sizes)
        except StageError as exc:
            self.problem.emit(exc, ERROR)
            return False
        self.current = doc
        self.opened.emit(doc.page_count)
        if self._running is doc:
            self._worker.set_priority(1)       # already being read (read-ahead): just put page 1 first
        elif self._needs_reading(doc):
            self._start_job(doc, priority=1)   # takes over from any read-ahead of another file
        else:
            self.finished.emit(FINISHED)       # fully cached; any read-ahead carries on
        return True

    def set_viewed_page(self, number: int) -> None:
        """The officer is looking at this page: read it next if still needed."""
        if self.busy:
            self._worker.set_priority(number)

    def set_read_ahead_files(self, paths: list[Path]) -> None:
        """The files read-ahead may read, in order (the working folder's list)."""
        self._candidates = list(paths)
        for path in paths:
            self.file_state_changed.emit(path, self._state_text(self.cache.get(path)))
        self._maybe_read_ahead()

    def request_reading(self, path: Path) -> None:
        """Read this file in the background (before any read-ahead), without
        showing it. document_done(path) follows — at once if it is already read."""
        doc = self.cache.get(path)
        if doc is not None and doc.complete and not self._pages_to_read(doc):
            self.document_done.emit(path)
            return
        self._awaited.add(path)
        if path not in self._requested:
            self._requested.insert(0, path)
        self._read_ahead_done.discard(doc.key if doc else None)
        self._maybe_read_ahead()

    def cached(self, path: Path) -> CachedDocument | None:
        """The readings held for this file, if any."""
        return self.cache.get(path)

    @property
    def page_sizes(self) -> list[tuple[int, int]]:
        return list(self.current.page_sizes or []) if self.current else []

    def render(self, number: int):
        """The open document's page as (pixmap, scale to page pixels). Raises StageError(stage="display")."""
        return page_renderer.render_page(self.current.path, number, self._settings.pdf_render_dpi,
                                         self._settings.display_dpi)

    def shutdown(self) -> None:
        """Stop the background thread. Safe to call more than once."""
        if self._stopped:
            return
        self._stopped = True
        self._worker.supersede(-1)
        self._thread.quit()
        if not self._thread.wait(self._settings.shutdown_wait_seconds * 1000):
            self._thread.terminate()
            self._thread.wait()

    # ---------------------------------------------------------------- jobs

    def _needs_reading(self, doc: CachedDocument) -> bool:
        return doc.page_count is None or bool(self._pages_to_read(doc))

    @staticmethod
    def _pages_to_read(doc: CachedDocument) -> list[int]:
        """Pages never read, plus pages whose reading failed (retried on open)."""
        if doc.page_count is None:
            return []
        return [n for n in range(1, doc.page_count + 1)
                if n not in doc.pages or doc.pages[n].result.error is not None]

    def _start_job(self, doc: CachedDocument, priority: int) -> None:
        if self._stopped:
            return
        self._job += 1
        self._worker.supersede(self._job)
        self._worker.set_priority(priority)
        self._jobs[self._job] = doc
        self._running = doc
        already_read = sorted(n for n, r in doc.pages.items() if r.result.error is None)
        self._read.emit(self._job, str(doc.path), already_read)
        self.file_state_changed.emit(doc.path, self._state_text(doc))

    def _maybe_read_ahead(self) -> None:
        if self._running is not None or self._stopped:
            return
        while self._requested:
            path = self._requested.pop(0)
            try:
                doc = self.cache.get_or_create(file_key(path))
            except StageError as exc:
                self.problem.emit(exc, ERROR)
                continue
            if doc.page_count is not None and not self._pages_to_read(doc):
                self.document_done.emit(path)
                continue
            self._start_job(doc, priority=0)
            return
        if not self._settings.read_ahead:
            return
        for path in self._candidates:
            try:
                key = file_key(path)
            except StageError:
                continue  # listed but gone; the file list will show it on refresh
            if key in self._read_ahead_done:
                continue
            doc = self.cache.get_or_create(key)
            if doc.page_count is not None and not self._pages_to_read(doc):
                continue
            self._start_job(doc, priority=0)
            return

    # ---------------------------------------------------------------- from the worker

    @Slot(int, int)
    def _on_counted(self, job_id: int, count: int) -> None:
        doc = self._jobs.get(job_id)
        if doc is not None and doc.page_count is None:
            doc.page_count = count

    @Slot(int, object)
    def _on_page_read(self, job_id: int, result: PageResult) -> None:
        doc = self._jobs.get(job_id)
        if doc is None or not self.cache.is_current(doc):
            return  # the file changed on disk since this job started
        rows, grouped = self._rows_for(doc, result)
        doc.pages[result.page_number] = PageReading(result, rows, grouped)
        self.file_state_changed.emit(doc.path, self._state_text(doc))
        if doc is self.current:
            self.page_ready.emit(result.page_number)

    @Slot(int, str)
    def _on_job_done(self, job_id: int, outcome: str) -> None:
        doc = self._jobs.pop(job_id, None)
        if doc is None:
            return
        doc.failed = outcome == FAILED
        if outcome != CANCELLED:
            # Ran to an end (even if pages failed): read-ahead does not come back to it this run,
            # so a broken file is never retried in a loop. An interrupted one is resumed later.
            self._read_ahead_done.add(doc.key)
        latest = job_id == self._job
        if latest:
            self._running = None
        self.file_state_changed.emit(doc.path, self._state_text(doc))
        if latest and doc is self.current:
            self.finished.emit(outcome)
        if outcome == CANCELLED and doc.path in self._awaited and doc.path not in self._requested:
            self._requested.insert(0, doc.path)      # a requested reading interrupted: it comes back first
        if outcome != CANCELLED:
            self._awaited.discard(doc.path)
            self.document_done.emit(doc.path)
        if latest:
            self._maybe_read_ahead()

    # ---------------------------------------------------------------- internal

    def _state_text(self, doc: CachedDocument | None) -> str:
        if doc is None:
            return ""
        if doc is self._running:
            total = f"/{doc.page_count}" if doc.page_count else ""
            return f"reading {doc.pages_read}{total}"
        if doc.failed and not doc.pages:
            return "could not open"
        if doc.page_count and doc.pages_read >= doc.page_count:
            failed = sum(1 for p in doc.pages.values() if p.result.error is not None)
            return f"read, {failed} failed" if failed else "read"
        if doc.pages:
            return f"{doc.pages_read}/{doc.page_count} read" if doc.page_count else f"{doc.pages_read} read"
        return ""

    def _rows_for(self, doc: CachedDocument, result: PageResult) -> tuple[list[TextRow], bool]:
        """Group one page's text into rows; on any failure fall back to one
        row per segment, and report it — never lose the page's text."""
        if self._row_rules is None:
            return ungrouped_rows(result.words), False
        try:
            return group_rows(result.words, self._row_rules), True
        except Exception as exc:
            error = exc if isinstance(exc, StageError) else StageError(
                "layout", "could not group this page's text into rows", cause=exc)
            error.file, error.page = doc.path.name, result.page_number
            self.problem.emit(error, WARNING)
            return ungrouped_rows(result.words), False
