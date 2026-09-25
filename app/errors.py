"""The one structured error shape used by every module in this application.

This system runs offline; a screenshot of the error tab is the entire
diagnostic session. So every failure, from any module, is turned into a
StageError carrying: which stage failed, a plain-language description,
file/page context where known, and — when it wraps another exception —
that exception with its full traceback.

    .summary    one line, for a list view
    .full_text  summary plus traceback, for the expanded view

Modules may subclass it (the OCR module's OcrStageError does) so a caller
can tell where an error came from, but the shape never changes.

Never put document text, names, amounts or PINs into `detail`.
"""

from __future__ import annotations

import traceback
from datetime import datetime


class StageError(Exception):
    """A failure at one clearly named stage, with enough context to diagnose
    it from a screenshot alone."""

    def __init__(self, stage: str, detail: str, *, file: str | None = None,
                 page: int | None = None, cause: BaseException | None = None) -> None:
        self.stage = stage      # short stage name, e.g. "config", "load", "ocr", "gui"
        self.detail = detail    # plain-English description; do not embed the exception text here
        self.file = file
        self.page = page
        self.cause = cause
        self.when = datetime.now()
        if cause is not None:
            _release_frames(cause)
        super().__init__(self.summary)

    @property
    def summary(self) -> str:
        """One line: what happened, where, and when — for a list of errors."""
        where = self.file or "?"
        if self.page:
            where += f" page {self.page}"
        line = f"[{self.when:%H:%M:%S}] {self.stage}: {where} - {self.detail}"
        if self.cause is not None:
            line += f" ({type(self.cause).__name__}: {self.cause})"
        return line

    @property
    def full_text(self) -> str:
        """The summary plus a traceback, when this wraps another exception:
        everything needed to find the exact line that failed."""
        if self.cause is None:
            return self.summary
        tb = "".join(traceback.format_exception(type(self.cause), self.cause, self.cause.__traceback__))
        return f"{self.summary}\n\n{tb.strip()}"


def _release_frames(exc: BaseException) -> None:
    """Drop the local variables held by the finished stack frames of `exc`
    (and of the exceptions chained to it). The traceback text is unaffected —
    it needs only file names and line numbers — but objects those frames held
    are released: without this, a PDF that failed to open stays locked by
    Windows for as long as the error is kept (found by test_ocr_integration)."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        traceback.clear_frames(exc.__traceback__)  # skips frames still running
        exc = exc.__cause__ or exc.__context__


# How serious an error is, for display. A warning means the work still went
# ahead in a reduced way (e.g. a page read unprocessed); an error means
# something was not done at all.
ERROR, WARNING = "error", "warning"
