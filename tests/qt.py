"""Shared Qt set-up for GUI tests: one off-screen QApplication, and a helper
that runs the event loop until a condition holds."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def wait_until(condition, seconds: float = 10.0) -> bool:
    app = qt_app()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        if condition():
            return True
    return condition()
