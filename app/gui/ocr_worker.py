"""OcrWorker: runs OCR on a background thread so the window never freezes.

Lives on its own QThread (document_session.py creates it) and talks to the
window only through signals. One job = the missing pages of one document:
render the file, then read the pages not yet in the cache, one at a time.

Order: the page the officer is looking at is read first (set_priority()),
then the rest in page order — so the page on screen is never stuck behind
pages nobody is looking at.

Job control: every request carries a job id. The window calls supersede()
and set_priority() directly (not through signals — a plain attribute write)
so a running job sees them between pages. A page mid-read cannot be
interrupted — it finishes first, and its result is still delivered, so no
finished work is thrown away.

Error boundary: nothing here raises into Qt. Engine start-up and file
loading failures end the job and are reported through `problem`; a page's
own failure is attached to its PageResult (and also reported), and the rest
of the document is still read. Anything unexpected is wrapped as a
StageError(stage="worker").
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.errors import ERROR, WARNING, StageError
from app.ocr import OcrReader, OcrStageError, PageResult

# job outcomes, sent with job_done
FINISHED, CANCELLED, FAILED = "finished", "cancelled", "failed"


class OcrWorker(QObject):
    engine_ready = Signal()
    document_counted = Signal(int, int)     # job id, page count of the rendered file
    page_read = Signal(int, object)         # job id, PageResult
    job_done = Signal(int, str)             # job id, FINISHED | CANCELLED | FAILED
    problem = Signal(object, str)           # StageError, ERROR | WARNING

    def __init__(self, dpi: int, reader: OcrReader | None = None) -> None:
        super().__init__()
        self._dpi = dpi
        self._reader = reader or OcrReader()
        self._latest_job = 0
        self._priority_page = 0

    # ---- called directly from the window's thread: plain int assignments

    def supersede(self, job_id: int) -> None:
        """Mark every job older than job_id as unwanted."""
        self._latest_job = job_id

    def set_priority(self, page_number: int) -> None:
        """Read this page next, if the running job still needs it (0 = none)."""
        self._priority_page = page_number

    # ---- slots, run on the worker thread

    @Slot()
    def warm_up(self) -> None:
        """Start the OCR engine ahead of the first document."""
        if self._start_engine():
            self.engine_ready.emit()

    @Slot(int, str, object)
    def read_document(self, job_id: int, path_text: str, skip_pages: object) -> None:
        """Read every page of the file except those in `skip_pages` (already cached)."""
        path = Path(path_text)
        if not self._wanted(job_id):
            self.job_done.emit(job_id, CANCELLED)
            return
        try:
            outcome = self._run_job(job_id, path, set(skip_pages or ()))
        except Exception as exc:  # boundary: nothing escapes into Qt's event loop
            self.problem.emit(StageError("worker", "reading this document stopped unexpectedly",
                                         file=path.name, cause=exc), ERROR)
            outcome = FAILED
        self.job_done.emit(job_id, outcome)

    # ---- internal

    def _wanted(self, job_id: int) -> bool:
        return job_id == self._latest_job

    def _start_engine(self) -> bool:
        if self._reader.ready:
            return True
        try:
            self._reader.start()
            return True
        except StageError as exc:
            self.problem.emit(exc, ERROR)
        except Exception as exc:
            self.problem.emit(StageError("startup", "the OCR engine could not be started", cause=exc), ERROR)
        return False

    def _run_job(self, job_id: int, path: Path, skip: set[int]) -> str:
        if not self._start_engine():
            return FAILED
        try:
            pages = self._reader.load_pages(path, self._dpi)
        except StageError as exc:
            exc.file = exc.file or path.name
            self.problem.emit(exc, ERROR)
            return FAILED
        if not pages:
            self.problem.emit(StageError("load", "the file has no pages", file=path.name), ERROR)
            return FAILED
        self.document_counted.emit(job_id, len(pages))

        todo = {p.number: p for p in pages if p.number not in skip}
        while todo:
            if not self._wanted(job_id):
                return CANCELLED
            number = self._priority_page if self._priority_page in todo else min(todo)
            result = self._read_one(todo.pop(number))
            if result.warning is not None:
                self.problem.emit(result.warning, WARNING)
            if result.error is not None:
                self.problem.emit(result.error, ERROR)
            self.page_read.emit(job_id, result)
        return FINISHED

    def _read_one(self, page) -> PageResult:
        """Per-page boundary: read_page() is documented never to raise, but
        one page must not end the document even if it does."""
        try:
            return self._reader.read_page(page)
        except Exception as exc:
            error = OcrStageError("ocr", "this page could not be read", file=page.source.name,
                                  page=page.number, cause=exc)
            return PageResult(page.number, [], [], None, [], 0.0, error=error)
