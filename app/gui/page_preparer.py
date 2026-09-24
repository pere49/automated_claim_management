"""PagePreparer: every read page of the open document, tokenised once for the checking.

Each page's text is tokenised once (matching.prepare_page) and reused — the
work is done when a page's reading arrives, and for the pages already read
of a file just opened, one page per idle moment — so checking a claim only
looks things up. A page that cannot be prepared is reported to the Errors
tab once, and the other pages are still checked. It also holds the matching
rules the checking uses. Nothing here ever puts a document's text or a
claimed value into an error.

(Until 2026-09-24 this was the search controller behind the typed search;
the Search panel was removed at the owner's request, D42.)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.errors import ERROR, WARNING, StageError
from app.matching import MatchingRules, PreparedPage, load_matching_rules, prepare_page


class PagePreparer(QObject):
    problem = Signal(object, str)     # StageError, level

    def __init__(self, session: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._rules: MatchingRules | None = None
        self._prepared: dict[int, tuple[Any, PreparedPage]] = {}   # page -> (reading it came from, tokens)
        self._reported: set[tuple[int, str]] = set()
        self._path = None
        self._pending: list[int] = []
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(0)
        self._idle.timeout.connect(self._prepare_next)

    # ---------------------------------------------------------------- public

    def start(self) -> None:
        """Load the matching rules; report it if they are unusable (claims then cannot be checked)."""
        try:
            self._rules = load_matching_rules()
        except StageError as exc:
            self.problem.emit(exc, ERROR)

    @property
    def available(self) -> bool:
        return self._rules is not None

    @property
    def rules(self) -> MatchingRules | None:
        return self._rules

    def page_arrived(self, number: int) -> None:
        """A page's reading arrived: prepare it now."""
        self._prepare(number)

    def prepared_pages(self) -> tuple[dict[int, PreparedPage], list[int]]:
        """Every read page of the open document, prepared (the ones already
        prepared are reused), and the pages with no usable reading."""
        session = self._session
        if session.path != self._path:
            self._prepared, self._path = {}, session.path
        pages, unread = {}, []
        for number in range(1, session.page_count + 1):
            prepared = self._prepare(number)
            if prepared is None:
                unread.append(number)
            else:
                pages[number] = prepared
        return pages, unread

    def document_changed(self) -> None:
        """Another file was opened: its already-read pages are prepared one per idle moment."""
        self._prepared, self._path, self._reported = {}, self._session.path, set()
        self._pending = list(range(1, self._session.page_count + 1))
        if self._rules is not None:
            self._idle.start()

    # ---------------------------------------------------------------- internal

    def _prepare_next(self) -> None:
        while self._pending:
            if self._prepare(self._pending.pop(0)):
                break
        if self._pending:
            self._idle.start()

    def _prepare(self, number: int) -> PreparedPage | None:
        """The page's prepared text, from the cache or made now. None if the
        page has no usable reading (or it could not be prepared: reported)."""
        session = self._session
        if self._rules is None or session.path != self._path:
            return None
        reading = session.reading(number)
        if reading is None or reading.result.error is not None:
            return None
        cached = self._prepared.get(number)
        if cached is not None and cached[0] is reading:
            return cached[1]
        try:
            prepared = prepare_page(reading.rows, self._rules)
        except Exception as exc:
            self._report(number, StageError("matching", "this page's text could not be prepared for checking",
                                            file=session.path.name if session.path else None, page=number,
                                            cause=exc))
            return None
        self._prepared[number] = (reading, prepared)
        return prepared

    def _report(self, page: int, error: StageError) -> None:
        """Report a page's failure once per document, however often it is asked for."""
        if (page, error.stage) not in self._reported:
            self._reported.add((page, error.stage))
            self.problem.emit(error, WARNING)
