"""run(): start the review application.

Loads the window settings, opens the main window (or, if the settings
cannot be loaded, a window explaining why), and routes any exception that
escapes a Qt event handler to the Errors tab instead of the console — the
last-resort error boundary for the window's own code.
"""

from __future__ import annotations

import sys
from types import TracebackType

from PySide6.QtWidgets import QApplication

from app.errors import ERROR, StageError
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from app.gui.startup_failure_window import StartupFailureWindow


def run(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Claim Verifier")
    window = build_window()
    install_exception_hook(window.report)
    window.show_fitted()
    window.start()
    return app.exec()


def build_window() -> MainWindow | StartupFailureWindow:
    try:
        settings = load_settings()
    except StageError as exc:
        return StartupFailureWindow(exc)
    except Exception as exc:
        return StartupFailureWindow(StageError("config", "the window settings could not be loaded", cause=exc))
    return MainWindow(settings)


def install_exception_hook(report) -> None:
    """Send any exception escaping a Qt slot or event handler to `report`."""

    def hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        try:
            error = exc if isinstance(exc, StageError) else StageError(
                "gui", "an unexpected error occurred in the window", cause=exc)
            report(error, ERROR)
        except Exception:
            sys.__excepthook__(exc_type, exc, tb)  # the error tab itself failed: last resort

    sys.excepthook = hook
