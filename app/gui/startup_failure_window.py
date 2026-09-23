"""StartupFailureWindow: shown instead of the main window when the window's
own settings cannot be loaded, so the officer sees why — with the full
detail to screenshot — rather than the application silently not opening."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from app.errors import ERROR, StageError
from app.gui.error_tab import ErrorTab


class StartupFailureWindow(QMainWindow):
    def __init__(self, error: StageError) -> None:
        super().__init__()
        self.setWindowTitle("Claim Verifier — could not start")
        self.resize(900, 500)
        self.errors = ErrorTab()
        heading = QLabel("<b>The application could not start.</b> The problem is shown below; "
                         "a screenshot of this window is enough to diagnose it.")
        heading.setWordWrap(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(heading)
        layout.addWidget(self.errors, 1)
        self.setCentralWidget(body)
        self.report(error)

    def show_fitted(self) -> None:
        self.show()

    def start(self) -> None:
        pass

    def report(self, error: StageError, level: str = ERROR) -> None:
        self.errors.add(error, level)
