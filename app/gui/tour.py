"""Tour: the Auto walk through every claimed amount, and its manual interruptions (D31).

Checking is done all at once, so the live demonstration is a replay: Auto
shows each amount in sheet order on its receipt, lingering green_ms on a
green one and yellow_ms on one to check. Choosing an amount by hand pauses
the tour without moving it; Auto resumes where the tour stopped. Next to
check jumps to the next amount that is not green (after the one shown) and
pauses the tour. At the last amount the tour stops.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from app.checking import GREEN, ItemResult


class Tour(QObject):
    show_item = Signal(int)            # item index to show
    running_changed = Signal(bool)

    def __init__(self, green_ms: int, yellow_ms: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._green_ms, self._yellow_ms = green_ms, yellow_ms
        self._results: list[ItemResult] = []
        self._next = 0                 # the next amount the tour will show
        self._shown: int | None = None # the amount on screen (by the tour or by hand)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    @property
    def position(self) -> int:
        return self._next

    def set_results(self, results: list[ItemResult] | None, restart: bool) -> None:
        """New findings. restart: a new claim — the tour starts again from the first amount."""
        self._results = list(results or [])
        if restart or self._next > len(self._results):
            self._next, self._shown = 0, None
        if not self._results:
            self.pause()

    def start(self) -> None:
        if not self._results:
            return
        if self._next >= len(self._results):
            self._next = 0
        self.running_changed.emit(True)
        self._step()

    def pause(self) -> None:
        was = self.running
        self._timer.stop()
        if was:
            self.running_changed.emit(False)

    def chosen(self, item: int) -> None:
        """The officer chose an amount: the tour pauses where it was."""
        self.pause()
        self._shown = item

    def next_to_check(self) -> None:
        self.pause()
        if not self._results:
            return
        start = (self._shown + 1) if self._shown is not None else 0
        count = len(self._results)
        for k in range(count):
            i = (start + k) % count
            if self._results[i].colour != GREEN:
                self._shown = i
                self.show_item.emit(i)
                return

    def _step(self) -> None:
        if self._next >= len(self._results):
            self._finish()
            return
        i = self._next
        self._next += 1
        self._shown = i
        self.show_item.emit(i)
        if self._next >= len(self._results):
            self._finish()           # the last amount stays on screen
            return
        self._timer.start(self._green_ms if self._results[i].colour == GREEN else self._yellow_ms)

    def _finish(self) -> None:
        self._timer.stop()
        self.running_changed.emit(False)
