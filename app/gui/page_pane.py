"""PagePane: the middle pane — the open receipt page.

Previous/Next here only move through the document's pages; they never run
a search (blueprint section 7: the PDF-side navigation is independent of
the claim rows). The page is fitted to the pane's width whenever a page is
shown or the pane is resized, until the officer zooms with Ctrl + wheel.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)


class PageView(QGraphicsView):
    """A page image with fit-to-width and Ctrl + wheel zoom."""

    def __init__(self, zoom_step: float, min_zoom: float, max_zoom: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom_step, self._min_zoom, self._max_zoom = zoom_step, min_zoom, max_zoom
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._fit = True

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(self._item.boundingRect())
        self.fit_width()

    def fit_width(self) -> None:
        self._fit = True
        width = self._item.boundingRect().width()
        if width <= 0:
            return
        scale = max(self.viewport().width() - 2, 1) / width
        self.resetTransform()
        self.scale(scale, scale)
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return
        factor = self._zoom_step if event.angleDelta().y() > 0 else 1 / self._zoom_step
        if self._min_zoom <= self.transform().m11() * factor <= self._max_zoom:
            self._fit = False
            self.scale(factor, factor)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit_width()


class PagePane(QWidget):
    previous_requested = Signal()
    next_requested = Signal()

    def __init__(self, zoom_step: float, min_zoom: float, max_zoom: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._prev = QPushButton("◀  Previous page")
        self._next = QPushButton("Next page  ▶")
        self._fit = QPushButton("Fit width")
        self._position = QLabel()
        self._position.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prev.clicked.connect(self.previous_requested)
        self._next.clicked.connect(self.next_requested)

        self._view = PageView(zoom_step, min_zoom, max_zoom)
        self._fit.clicked.connect(self._view.fit_width)
        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._message)
        self._stack.addWidget(self._view)

        bar = QHBoxLayout()
        bar.addWidget(self._prev)
        bar.addWidget(self._position, 1)
        bar.addWidget(self._next)
        bar.addWidget(self._fit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(bar)
        layout.addWidget(self._stack, 1)
        self.show_message("Choose a PDF from the list on the left.")

    @property
    def position_text(self) -> str:
        return self._position.text()

    def show_page(self, pixmap: QPixmap, number: int, total: int) -> None:
        self._stack.setCurrentWidget(self._view)
        self._view.set_pixmap(pixmap)
        self._set_position(number, total)

    def show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)
        self._set_position(0, 0)

    def _set_position(self, number: int, total: int) -> None:
        self._position.setText(f"Page {number} of {total}" if total else "")
        self._prev.setEnabled(number > 1)
        self._next.setEnabled(0 < number < total)
        self._fit.setEnabled(total > 0)
