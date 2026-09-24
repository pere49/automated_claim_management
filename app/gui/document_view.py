"""DocumentView: the whole document as one continuous vertical scroll.

Pages are laid out top to bottom in page pixels (the OCR's own frame), each
centred, with a gap between them. Only pages on screen, plus a margin above
and below, have their picture drawn; pages further away are released, so a
long claim stays light. Pages on screen are drawn at once; the margin pages
one at a time when the window is idle, so a jump shows its page promptly. A page that cannot be drawn shows a plain notice and
is reported once through `problem`.

Highlights are overlay shapes placed in the same page pixels, so zooming and
scrolling cost nothing; each page may carry a badge in its top-right corner
(page_badges.py). The view fits the page width until the officer zooms
with Ctrl + wheel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF, QWheelEvent
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QWidget)

from app.errors import ERROR, StageError
from app.gui.page_badges import Badge, BadgeItem, BadgeStyle

RenderFn = Callable[[int], tuple[QPixmap, float]]  # page number -> (picture, scale to page pixels)

_PAGE_Z, _PICTURE_Z, _HIGHLIGHT_Z, _BADGE_Z = 0, 1, 2, 3


@dataclass(frozen=True)
class Shape:
    """One highlight outline: a polygon in page pixels on one page."""
    page: int
    points: tuple[tuple[float, float], ...]
    colour: QColor
    fill_alpha: int          # 0 = outline only
    line_px: float
    dashed: bool = False


class DocumentView(QGraphicsView):
    current_page_changed = Signal(int)
    problem = Signal(object, str)

    def __init__(self, gap_px: int, margin_pages: int, zoom_step: float, min_zoom: float, max_zoom: float,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gap, self._margin = gap_px, margin_pages
        self._zoom_step, self._min_zoom, self._max_zoom = zoom_step, min_zoom, max_zoom
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setBackgroundBrush(QBrush(QColor(128, 128, 128)))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)  # a steady width to fit to
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._render: RenderFn | None = None
        self._rects: list[QRectF] = []                    # page n is self._rects[n - 1], in scene coordinates
        self._pictures: dict[int, QGraphicsPixmapItem] = {}
        self._failed: set[int] = set()
        self._highlights: list[QGraphicsPolygonItem] = []
        self._badges: list[BadgeItem] = []
        self._current = 0
        self._fit = True
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh)
        self._ahead: list[int] = []
        self._ahead_timer = QTimer(self)
        self._ahead_timer.setSingleShot(True)
        self._ahead_timer.setInterval(0)
        self._ahead_timer.timeout.connect(self._draw_ahead)
        self.verticalScrollBar().valueChanged.connect(self._schedule_refresh)
        self.horizontalScrollBar().valueChanged.connect(self._schedule_refresh)

    # ---------------------------------------------------------------- public

    @property
    def page_count(self) -> int:
        return len(self._rects)

    @property
    def current_page(self) -> int:
        return self._current

    @property
    def drawn_pages(self) -> list[int]:
        return sorted(self._pictures)

    def set_document(self, sizes: list[tuple[int, int]], render: RenderFn) -> None:
        """Lay out a new document (page sizes in page pixels) and show page 1."""
        self.clear_document()
        self._render = render
        widest = max(w for w, _ in sizes)
        y = 0.0
        for number, (w, h) in enumerate(sizes, start=1):
            rect = QRectF((widest - w) / 2, y, w, h)
            self._rects.append(rect)
            frame = QGraphicsRectItem(rect)
            frame.setBrush(QBrush(Qt.GlobalColor.white))
            frame.setPen(QPen(QColor(90, 90, 90), 0))
            frame.setZValue(_PAGE_Z)
            self._scene.addItem(frame)
            y += h + self._gap
        self._scene.setSceneRect(QRectF(-self._gap, -self._gap, widest + 2 * self._gap, y + self._gap))
        self.fit_width()
        self.go_to_page(1)
        self._refresh()

    def clear_document(self) -> None:
        self._scene.clear()
        self._rects, self._pictures, self._highlights, self._badges, self._ahead = [], {}, [], [], []
        self._failed = set()
        self._render = None
        self._current = 0

    def go_to_page(self, number: int) -> None:
        """Scroll so the top of page `number` is at the top of the view."""
        if not 1 <= number <= self.page_count:
            return
        rect = self._rects[number - 1]
        top = self.mapFromScene(QPointF(rect.center().x(), rect.top() - self._gap / 2))
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + int(top.y()))
        self._refresh()

    def show_area(self, number: int, points: tuple[tuple[float, float], ...]) -> None:
        """Scroll so this area of page `number` (page pixels) is in the middle of the view."""
        if not 1 <= number <= self.page_count or not points:
            return
        origin = self._rects[number - 1].topLeft()
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        self.centerOn(QPointF(origin.x() + (min(xs) + max(xs)) / 2, origin.y() + (min(ys) + max(ys)) / 2))
        self._refresh()

    def fit_width(self) -> None:
        self._fit = True
        if not self._rects:
            return
        widest = max(r.width() for r in self._rects) + 2 * self._gap
        scale = max(self.viewport().width() - 4, 1) / widest
        anchor = self._current or 1
        self.resetTransform()
        self.scale(scale, scale)
        self.go_to_page(anchor)

    def set_highlights(self, shapes: list[Shape]) -> None:
        for item in self._highlights:
            self._scene.removeItem(item)
        self._highlights = []
        for shape in shapes:
            if not 1 <= shape.page <= self.page_count:
                continue
            origin = self._rects[shape.page - 1].topLeft()
            polygon = QPolygonF([QPointF(origin.x() + x, origin.y() + y) for x, y in shape.points])
            item = QGraphicsPolygonItem(polygon)
            pen = QPen(shape.colour, shape.line_px)
            pen.setCosmetic(True)
            if shape.dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
            item.setPen(pen)
            if shape.fill_alpha:
                fill = QColor(shape.colour)
                fill.setAlpha(shape.fill_alpha)
                item.setBrush(QBrush(fill))
            item.setZValue(_HIGHLIGHT_Z)
            self._scene.addItem(item)
            self._highlights.append(item)

    @property
    def highlight_count(self) -> int:
        return len(self._highlights)

    def set_badges(self, badges: list[Badge], style: BadgeStyle) -> None:
        """One badge per page at most, in the page's top-right corner (replaces the previous ones)."""
        for item in self._badges:
            self._scene.removeItem(item)
        self._badges = []
        for badge in badges:
            if not 1 <= badge.page <= self.page_count:
                continue
            item = BadgeItem(badge, style)
            item.setPos(self._rects[badge.page - 1].topRight())
            item.setZValue(_BADGE_Z)
            self._scene.addItem(item)
            self._badges.append(item)

    @property
    def badges(self) -> dict[int, Badge]:
        return {item.badge.page: item.badge for item in self._badges}

    # ---------------------------------------------------------------- events

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return
        factor = self._zoom_step if event.angleDelta().y() > 0 else 1 / self._zoom_step
        if self._min_zoom <= self.transform().m11() * factor <= self._max_zoom:
            self._fit = False
            self.scale(factor, factor)
            self._schedule_refresh()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit_width()
        self._schedule_refresh()

    # ---------------------------------------------------------------- internal

    def _schedule_refresh(self, *_args) -> None:
        self._refresh_timer.start()

    def _refresh(self) -> None:
        """Draw pages near the screen, release far ones, update the current page."""
        if not self._rects:
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        keep_from = keep_to = None
        for number, rect in enumerate(self._rects, start=1):
            if rect.intersects(visible):
                keep_from = number if keep_from is None else keep_from
                keep_to = number
        if keep_from is None:
            return
        on_screen = range(keep_from, keep_to + 1)
        keep_from, keep_to = max(1, keep_from - self._margin), min(self.page_count, keep_to + self._margin)
        for number in [n for n in self._pictures if not keep_from <= n <= keep_to]:
            self._scene.removeItem(self._pictures.pop(number))
        for number in on_screen:  # what the officer sees is drawn now ...
            if number not in self._pictures and number not in self._failed:
                self._draw(number)
        self._ahead = [n for n in range(keep_from, keep_to + 1)
                       if n not in on_screen and n not in self._pictures and n not in self._failed]
        if self._ahead:  # ... the pages just above and below at the next idle moment
            self._ahead_timer.start()
        centre_y = visible.center().y()
        current = min(range(1, self.page_count + 1),
                      key=lambda n: 0 if self._rects[n - 1].top() <= centre_y <= self._rects[n - 1].bottom()
                      else min(abs(self._rects[n - 1].top() - centre_y), abs(self._rects[n - 1].bottom() - centre_y)))
        if current != self._current:
            self._current = current
            self.current_page_changed.emit(current)

    def _draw_ahead(self) -> None:
        """Draw one page near the screen, then yield to the event loop for the next."""
        while self._ahead:
            number = self._ahead.pop(0)
            if 1 <= number <= self.page_count and number not in self._pictures and number not in self._failed:
                self._draw(number)
                break
        if self._ahead:
            self._ahead_timer.start()

    def _draw(self, number: int) -> None:
        rect = self._rects[number - 1]
        try:
            pixmap, scale = self._render(number)
        except Exception as exc:
            self._failed.add(number)
            error = exc if isinstance(exc, StageError) else StageError(
                "display", "could not display this page", page=number, cause=exc)
            error.page = error.page or number
            self.problem.emit(error, ERROR)
            notice = QGraphicsSimpleTextItem(f"Page {number} could not be displayed — see the Errors tab.")
            notice.setScale(max(rect.width() / 900, 1))
            notice.setPos(rect.left() + rect.width() * 0.05, rect.top() + rect.height() * 0.05)
            notice.setZValue(_PICTURE_Z)
            self._scene.addItem(notice)
            return
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        item.setScale(scale)
        item.setPos(rect.topLeft())
        item.setZValue(_PICTURE_Z)
        self._scene.addItem(item)
        self._pictures[number] = item
