"""SheetCanvas: one picture with overlay items, fitted to the pane's width, scrolled vertically.

The claim sheet is shown as the document itself (D39): its cropped page
picture sits at the scene's origin, with a gutter to its left for the row
buttons. The view fits the scene's width until the officer zooms with
Ctrl + wheel; centre_on() brings a height into the middle of the view.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget


class SheetCanvas(QGraphicsView):
    def __init__(self, zoom_step: float, min_zoom: float, max_zoom: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom_step, self._min_zoom, self._max_zoom = zoom_step, min_zoom, max_zoom
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setBackgroundBrush(QBrush(QColor(128, 128, 128)))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # always shown: a scroll bar that comes and goes changes the width the picture is fitted to,
        # which makes it come and go again, for ever (found by the tests, window 420 px high)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)   # the sheet starts at the top
        self._fit = True
        self.picture: QGraphicsPixmapItem | None = None

    def show_picture(self, pixmap: QPixmap, gutter: float) -> None:
        """A new picture at the origin, with `gutter` scene units free on its left."""
        self.clear()
        self.picture = QGraphicsPixmapItem(pixmap)
        self.picture.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self.picture)
        self._scene.setSceneRect(QRectF(-gutter, 0, pixmap.width() + gutter, pixmap.height()))
        self._fit = True
        self.fit_width()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

    def clear(self) -> None:
        self._scene.clear()
        self.picture = None
        self._scene.setSceneRect(QRectF())

    def add(self, item: QGraphicsItem, z: float) -> None:
        item.setZValue(z)
        self._scene.addItem(item)

    def remove(self, item: QGraphicsItem) -> None:
        if item.scene() is self._scene:
            self._scene.removeItem(item)

    def fit_width(self) -> None:
        rect = self._scene.sceneRect()
        if rect.width() <= 0:
            return
        scale = max(self.viewport().width() - 2, 1) / rect.width()
        self.resetTransform()
        self.scale(scale, scale)

    def centre_on(self, y: float) -> None:
        self.centerOn(QPointF(self._scene.sceneRect().center().x(), y))

    def visible_rows(self) -> tuple[float, float]:
        """The scene heights on screen (top, bottom)."""
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        return rect.top(), rect.bottom()

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
