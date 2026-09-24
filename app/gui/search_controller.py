"""SearchController: runs a search over the open document and keeps it current.

The officer's typed values become a matching Query (app/matching). Every page
of the open document that has been read is searched; pages still being read
are searched as their readings arrive (the result updates by itself).
Moving through pages never re-runs a search. Opening another file clears the
search: results belong to one document.

Each page's text is tokenised once (matching.prepare_page) and reused. That
work is done ahead of any search: when a page's reading arrives, and for the
pages already read of a file just opened, one page per idle moment — so a
search itself is only lookups. A page that cannot be searched is reported to
the Errors tab once, and the rest are still searched. Nothing here ever puts
a searched value into an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from app.errors import ERROR, WARNING, StageError
from app.matching import (DocumentMatches, MatchingRules, PreparedPage, Query, QueryError, load_matching_rules,
                          normalise_pin, parse_typed_amount, prepare_page, search_document)


@dataclass
class SearchOutcome:
    matches: DocumentMatches
    searched: int            # pages searched (read)
    total: int               # pages in the document
    unreadable: int          # pages whose OCR failed (nothing to search)
    still_reading: bool
    first: bool              # True for a new search, False for a live update


class SearchController(QObject):
    updated = Signal(object)          # SearchOutcome
    cleared = Signal()
    problem = Signal(object, str)     # StageError, level

    def __init__(self, session: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._rules: MatchingRules | None = None
        self._query: Query | None = None
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
        """Load the matching rules; report and disable searching if they are unusable."""
        try:
            self._rules = load_matching_rules()
        except StageError as exc:
            self.problem.emit(exc, ERROR)

    @property
    def available(self) -> bool:
        return self._rules is not None

    @property
    def active(self) -> bool:
        return self._query is not None

    def build_query(self, when: date | None, amount_text: str, pin_text: str) -> Query:
        """The typed values as a Query. Raises QueryError (field name first in the message)."""
        if self._rules is None:
            raise QueryError("searching is unavailable: the matching rules could not be loaded (see the Errors tab)")
        amount = None
        if amount_text.strip():
            try:
                amount = parse_typed_amount(amount_text, self._rules)
            except QueryError as exc:
                raise QueryError(f"Amount: {exc}") from exc
        pin = normalise_pin(pin_text) or None
        query = Query(date=when, amount=amount, pin=pin)
        if not query.keys:
            raise QueryError("enter at least one of the date, the PIN or the amount")
        return query

    def run(self, query: Query) -> None:
        """Search every read page of the open document for `query`."""
        self._query = query
        self._search(first=True)

    def refresh(self) -> None:
        """Search again, if a search is active (e.g. reading finished)."""
        if self._query is not None:
            self._search(first=False)

    def page_arrived(self, number: int) -> None:
        """A page's reading arrived: prepare it now, and update an active search."""
        self._prepare(number)
        self.refresh()

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

    @property
    def rules(self) -> MatchingRules | None:
        return self._rules

    def clear(self) -> None:
        self._query = None
        self.cleared.emit()

    def document_changed(self) -> None:
        """Another file was opened: its results are not this search's. Its
        already-read pages are prepared one per idle moment."""
        self._prepared, self._path, self._reported = {}, self._session.path, set()
        if self._query is not None:
            self.clear()
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
            self._report(number, StageError("matching", "this page's text could not be prepared for searching",
                                            file=_name(session), page=number, cause=exc))
            return None
        self._prepared[number] = (reading, prepared)
        return prepared

    def _search(self, first: bool) -> None:
        session = self._session
        if session.path != self._path:
            self._prepared, self._path = {}, session.path
        total = session.page_count
        pages: dict[int, PreparedPage] = {}
        unreadable = 0
        for number in range(1, total + 1):
            reading = session.reading(number)
            if reading is not None and reading.result.error is not None:
                unreadable += 1
                continue
            prepared = self._prepare(number)
            if prepared is not None:
                pages[number] = prepared
        matches = search_document(pages, self._query, self._rules)
        for error in matches.errors:
            error.file = _name(session)
            self._report(error.page, error)
        read = sum(1 for n in range(1, total + 1) if session.reading(n) is not None)
        self.updated.emit(SearchOutcome(matches, read, total, unreadable, session.busy, first))

    def _report(self, page: int, error: StageError) -> None:
        """Report a page's failure once per document, however often it is searched."""
        if (page, error.stage) not in self._reported:
            self._reported.add((page, error.stage))
            self.problem.emit(error, WARNING)


def _name(session: Any) -> str | None:
    return session.path.name if session.path else None
