"""PagePane: the middle pane — the open document, scrolled continuously.

Previous/Next page jump one page; they never run a search (blueprint
section 7). The position label follows whichever page is mostly in view.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.gui.document_view import DocumentView, RenderFn, Shape
from app.gui.page_badges import Badge, BadgeStyle


class PagePane(QWidget):
    current_page_changed = Signal(int)
    problem = Signal(object, str)

    def __init__(self, gap_px: int, margin_pages: int, zoom_step: float, min_zoom: float, max_zoom: float,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._prev = QPushButton("◀  Previous page")
        self._next = QPushButton("Next page  ▶")
        self._fit = QPushButton("Fit width")
        self._position = QLabel()
        self._position.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.view = DocumentView(gap_px, margin_pages, zoom_step, min_zoom, max_zoom)
        self.view.current_page_changed.connect(self._on_current)
        self.view.problem.connect(self.problem)
        self._prev.clicked.connect(lambda: self.view.go_to_page(self.view.current_page - 1))
        self._next.clicked.connect(lambda: self.view.go_to_page(self.view.current_page + 1))
        self._fit.clicked.connect(self.view.fit_width)
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._message)
        self._stack.addWidget(self.view)

        bar = QHBoxLayout()
        bar.addWidget(self._prev)
        bar.addWidget(self._position, 1)
        bar.addWidget(self._next)
        bar.addWidget(self._fit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(bar)
        layout.addWidget(self._stack, 1)
        self.show_message("Choose a file from the list on the left.")

    @property
    def position_text(self) -> str:
        return self._position.text()

    @property
    def current_page(self) -> int:
        return self.view.current_page

    def show_document(self, sizes: list[tuple[int, int]], render: RenderFn) -> None:
        self._stack.setCurrentWidget(self.view)
        self.view.set_document(sizes, render)
        self._update_position(self.view.current_page)

    def show_message(self, text: str) -> None:
        self.view.clear_document()
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)
        self._update_position(0)

    def go_to_page(self, number: int) -> None:
        self.view.go_to_page(number)

    def show_area(self, number: int, points: tuple[tuple[float, float], ...]) -> None:
        self.view.show_area(number, points)

    def set_highlights(self, shapes: list[Shape]) -> None:
        self.view.set_highlights(shapes)

    def set_badges(self, badges: list[Badge], style: BadgeStyle) -> None:
        self.view.set_badges(badges, style)

    def _on_current(self, number: int) -> None:
        self._update_position(number)
        self.current_page_changed.emit(number)

    def _update_position(self, number: int) -> None:
        total = self.view.page_count
        self._position.setText(f"Page {number} of {total}" if total and number else "")
        self._prev.setEnabled(number > 1)
        self._next.setEnabled(0 < number < total)
        self._fit.setEnabled(total > 0)
