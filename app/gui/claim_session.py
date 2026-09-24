"""ClaimSession: the claim sheet and its receipts, checked together (Stage C).

The two slots: the claim sheet (a file read by app/claims — a text PDF at
once, a scanned sheet after OCR has read it in the background)
and the receipts (the document open in the viewer). When both are ready —
the receipts read to the end, the sheet read — every claimed amount is
checked at once (app/checking): the PIN scan, the repeated pages, the
pairing, the verdicts, the totals. Changing the sheet tab checks it afresh;
flipping the PIN switch only decides again. Opening other receipts puts the
PIN switch back to what the scan says.

Nothing here raises into Qt: every failure becomes a StageError on
`problem` (never with claim values in it), and the check is simply absent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.checking import ClaimCheck, analyse_receipts, decide, find_all, load_checking_rules
from app.claims import SCANNED, ClaimFile, load_claim_rules, looks_like_claim_sheet, read_claim_file, sheet_kind
from app.company_pin import load_company_pin
from app.errors import ERROR, WARNING, StageError
from app.gui.ocr_worker import FAILED
from app.gui.settings import GuiSettings


class ClaimSession(QObject):
    sheet_changed = Signal(object)        # ClaimFile, or None when there is no sheet
    checked = Signal(object)              # ClaimCheck, or None when nothing is checked
    waiting = Signal(str)                 # what the check is waiting for, in plain words
    problem = Signal(object, str)         # StageError, ERROR | WARNING

    def __init__(self, session, pages, settings: GuiSettings, today: Callable[[], date] = date.today,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session, self._pages, self._settings, self._today = session, pages, settings, today
        self._claim_rules = self._checking_rules = None
        self._pin: str | None = None
        self.sheet_path: Path | None = None
        self.claim: ClaimFile | None = None
        self.sheet_index = 0
        self.result: ClaimCheck | None = None
        self.pin_switch: bool | None = None      # the officer's choice; None: the PIN scan decides
        self._scanned_waiting = False
        self._facts = None
        self._facts_for = None
        self._findings = None
        self._reported: set = set()                # checking failures already reported, per claim and receipts
        self._receipts_outcome: str | None = None  # how the receipts' reading last ended (None: still going)
        session.opened.connect(self._on_receipts_opened)
        session.finished.connect(self._on_receipts_finished)
        session.page_ready.connect(lambda number: self.run())    # keeps "Reading the receipts: n of N" current
        session.document_done.connect(self._on_document_done)

    # ---------------------------------------------------------------- public

    def start(self) -> None:
        """Load the claim and checking rules and the company PIN; report what is missing."""
        for load, name in ((load_claim_rules, "_claim_rules"), (load_checking_rules, "_checking_rules")):
            try:
                setattr(self, name, load())
            except StageError as exc:
                self.problem.emit(exc, ERROR)
        try:
            self._pin = load_company_pin(self._settings.company_pin_file, self._settings.company_pin_key)
        except StageError as exc:
            self.problem.emit(exc, ERROR)
        if self._pin is None:
            self.problem.emit(StageError("config", "no company PIN is set, so the PIN checks are off",
                                         file=self._settings.company_pin_file.name), WARNING)

    @property
    def available(self) -> bool:
        return None not in (self._claim_rules, self._checking_rules, self._pages.rules)

    @property
    def sheet(self):
        return self.claim.sheets[self.sheet_index] if self.claim else None

    @property
    def pin_available(self) -> bool:
        return self._pin is not None

    def is_claim_sheet(self, path: Path) -> bool:
        """A PDF whose text holds a claim table (a scanned
        sheet is only known as one when the officer says so)."""
        return self._claim_rules is not None and looks_like_claim_sheet(path, self._claim_rules)

    def set_sheet(self, path: Path) -> None:
        self.clear_sheet(announce=False)
        if self._claim_rules is None:
            self.problem.emit(StageError("claim sheet", "claim sheets cannot be read: the claim rules could not be "
                                         "loaded (see the Errors tab)", file=path.name), ERROR)
            return
        self.sheet_path = path
        try:
            kind = sheet_kind(path, self._claim_rules)
        except StageError as exc:
            self._failed(exc)
            return
        if kind == SCANNED:
            self._scanned_waiting = True
            self.waiting.emit(f"Reading the claim sheet {path.name} (a scanned picture) with OCR…")
            self.sheet_changed.emit(None)
            self._session.request_reading(path)
            return
        self._read(path, None)

    def clear_sheet(self, announce: bool = True) -> None:
        self.sheet_path, self.claim, self.sheet_index, self._scanned_waiting = None, None, 0, False
        self._findings, self.result = None, None
        if announce:
            self.sheet_changed.emit(None)
            self.checked.emit(None)

    def set_sheet_index(self, index: int) -> None:
        if self.claim and 0 <= index < len(self.claim.sheets) and index != self.sheet_index:
            self.sheet_index = index
            self._findings = None
            self.run()

    def set_pin_required(self, required: bool) -> None:
        self.pin_switch = required
        self.run()

    def run(self) -> None:
        """Check the claim if the sheet and the receipts are both ready."""
        if self.claim is None:
            return
        if not self.available:
            self._not_checked("The claim cannot be checked: the checking or matching rules could not be loaded — "
                              "see the Errors tab.")
            return
        session = self._session
        if not session.has_document:
            self._not_checked("Choose the receipts PDF from the list to check this claim.")
            return
        read, total = session.pages_read(), session.page_count
        if session.busy or not (session.current and session.current.complete):
            # checked only once every page has a reading (a page that failed counts, and is reported)
            if session.busy or self._receipts_outcome is None:
                why = (f"Reading the receipts: {read} of {total} pages — the claim is checked when every page "
                       "has been read.")
            elif self._receipts_outcome == FAILED:
                why = "The receipts could not be read — see the Errors tab."
            else:
                why = f"Reading the receipts stopped at {read} of {total} pages — click them again to finish."
            self._not_checked(why)
            return
        try:
            key = (session.path, session.pages_read())
            if self._facts is None or self._facts_for != key:
                pages, unread = self._pages.prepared_pages()
                self._facts = analyse_receipts(pages, session.page_count, unread, self._pin, self._checking_rules,
                                               self._pages.rules)
                self._facts_for, self._findings = key, None
            if self._findings is None:
                self._findings = find_all(self.sheet, self._facts, self._pin, self._pages.rules)
            required = self._pin is not None and (bool(self._facts.pin_pages) if self.pin_switch is None
                                                   else self.pin_switch)
            self.result = decide(self.sheet, self._findings, self._facts, required)
        except Exception as exc:
            error = exc if isinstance(exc, StageError) else StageError(
                "checking", "the claim could not be checked", file=session.path.name if session.path else None,
                cause=exc)
            key = (session.path, self.sheet_path, self.sheet_index, error.stage, error.detail)
            if key not in self._reported:       # once per claim and receipts, however often it is retried
                self._reported.add(key)
                self.problem.emit(error, ERROR)
            self.result = None
        self.checked.emit(self.result)

    # ---------------------------------------------------------------- internal

    def _read(self, path: Path, scanned_words) -> None:
        try:
            claim = read_claim_file(path, self._claim_rules, self._today(), scanned_words=scanned_words,
                                    dpi=self._settings.pdf_render_dpi)
        except StageError as exc:
            self._failed(exc)
            return
        except Exception as exc:
            self._failed(StageError("claim sheet", "the claim sheet could not be read", file=path.name, cause=exc))
            return
        self.claim, self.sheet_index, self._findings = claim, claim.active, None
        self.sheet_changed.emit(claim)
        self.run()

    def _failed(self, error: StageError) -> None:
        self.problem.emit(error, ERROR)
        self.clear_sheet()

    def _not_checked(self, why: str) -> None:
        self.result = None
        self.checked.emit(None)
        self.waiting.emit(why)

    def _on_receipts_opened(self, _count: int) -> None:
        self._facts = self._findings = self.result = None
        self.pin_switch = None
        self._receipts_outcome = None
        self.run()

    def _on_receipts_finished(self, outcome: str) -> None:
        self._receipts_outcome = outcome
        self.run()

    def _on_document_done(self, path: Path) -> None:
        if not (self._scanned_waiting and path == self.sheet_path):
            return
        self._scanned_waiting = False
        doc = self._session.cached(path)
        words = {}
        for number, reading in sorted((doc.pages if doc else {}).items()):
            if reading.result.error is None:
                words[number] = [_segment(w) for w in reading.result.words]
        if not words:
            self._failed(StageError("claim sheet", "OCR could not read the scanned claim sheet", file=path.name))
            return
        self._read(path, words)


def _segment(word) -> tuple[float, float, float, float, str]:
    box = word.page_box or word.box
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    return min(xs), min(ys), max(xs), max(ys), word.text
