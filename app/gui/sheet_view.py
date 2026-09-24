"""SheetView: right pane — the claim sheet shown as its PDF, a button per claim row (D36, D39).

The sheet's page, cropped to its printed area, fills the pane's width and
scrolls up and down. Left of each claim row sits a small square button: its
colour is the row's status (green when every amount in the row is
verified, else the worst colour of its amounts). Clicking it shows the
row's first amount on its receipt, the next click the next amount, and
after the last the first again (item_chosen). An amount that failed is
tinted in its colour; one with no receipt also says "No receipt found".
The row whose receipt page is in view (follow_row) and the amount shown
(select_item) are outlined and brought to the middle of the pane. Several
claim sheets in one file show as tabs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from statistics import median

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QLabel, QTabBar, QVBoxLayout, QWidget

from app.checking import GREEN, P_NO_RECEIPT, RED, YELLOW, ClaimCheck
from app.claims import ClaimFile, ClaimSheet
from app.errors import ERROR, StageError
from app.gui.row_buttons import RowButton
from app.gui.settings import GuiSettings
from app.gui.sheet_canvas import SheetCanvas
from app.gui.sheet_overlay import Frame, crop_box, label, outline, tint

RenderRegion = Callable[[Path, int, int, tuple[float, float, float, float]], QPixmap]
NO_RECEIPT_TEXT = "No receipt found"
_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}
_TINT_Z, _LABEL_Z, _OUTLINE_Z, _BUTTON_Z = 1, 2, 3, 4


class SheetView(QWidget):
    item_chosen = Signal(int)            # an item index, asked for by a row button
    tab_changed = Signal(int)
    problem = Signal(object, str)

    def __init__(self, settings: GuiSettings, render: RenderRegion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._s, self._render = settings, render
        self._quiet = False
        self.title = QLabel("<b>Claim sheet:</b> —")
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.tabs = QTabBar()
        self.tabs.setVisible(False)
        self.tabs.currentChanged.connect(self._on_tab)
        self.canvas = SheetCanvas(settings.zoom_step, settings.min_zoom, settings.max_zoom)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.tabs)
        layout.addWidget(self.message)
        layout.addWidget(self.canvas, 1)
        self._reset()
        self.show_claim(None)

    # ---------------------------------------------------------------- public

    def show_claim(self, claim: ClaimFile | None, index: int = 0) -> None:
        self._quiet = True
        while self.tabs.count():
            self.tabs.removeTab(0)
        if claim is not None:
            for sheet in claim.sheets:
                self.tabs.addTab(sheet.name.strip() or "sheet")
            self.tabs.setCurrentIndex(index)
        self.tabs.setVisible(bool(claim) and len(claim.sheets) > 1)
        self._quiet = False
        self.title.setText(f"<b>Claim sheet:</b> {claim.path.name}" if claim else "<b>Claim sheet:</b> —")
        self.show_message("" if claim else "Choose a claim sheet (a PDF of it) from the list: click it, or "
                                           "right-click a file → Use as claim sheet.")
        if claim is None:
            self._reset()
            self.canvas.clear()
            return
        self.show_sheet(claim, index)

    def show_sheet(self, claim: ClaimFile, index: int) -> None:
        self._reset()
        self.canvas.clear()
        sheet = claim.sheets[index]
        self._sheet = sheet
        for row in sheet.rows:
            for item in row.items:
                self._item_row[item.index] = row.grid_row
            self._row_items[row.grid_row] = [item.index for item in row.items]
        place = sheet.place
        if place is None:
            self.show_message("This claim sheet cannot be shown: where its rows are on the page is not known.")
            return
        crop = crop_box(place.printed, self._s.sheet_margin_frac)
        try:
            picture = self._render(claim.path, place.page, self._s.display_dpi,
                                   (crop.left, crop.top, crop.right, crop.bottom))
        except StageError as exc:
            self.problem.emit(exc, ERROR)
            self._draw_problem = ("The claim sheet could not be drawn — see the Errors tab. Its amounts are still "
                                  "checked; the tour and the statuses work.")
            self.show_message("")
            return
        self._frame = Frame(crop, picture.width(), picture.height())
        bands = {row.grid_row: self._frame.rect(place.row_band(row.grid_row)) for row in sheet.rows
                 if place.row_band(row.grid_row) is not None}
        size = median(r.height() for r in bands.values()) * self._s.row_button_frac if bands else 0
        gutter = size * 1.6
        self.canvas.show_picture(picture, gutter)
        for grid_row, band in bands.items():
            rect = QRectF(-gutter + (gutter - size) / 2, band.center().y() - size / 2, size, size)
            button = RowButton(grid_row, rect, self._on_row)
            button.set_colour("grey", QColor(self._s.status_colours["grey"]), enabled=False)
            count = len(self._row_items[grid_row])
            button.setToolTip(f"{count} claimed amount{'s' if count > 1 else ''} — click to show "
                              f"{'each in turn' if count > 1 else 'it'} on its receipt")
            self.canvas.add(button, _BUTTON_Z)
            self._buttons[grid_row] = button
            self._bands[grid_row] = band

    def show_results(self, result: ClaimCheck | None) -> None:
        for item in self._marks:
            self.canvas.remove(item)
        self._marks = []
        self._result = result
        colours = self._s.status_colours
        for grid_row, button in self._buttons.items():
            if result is None:
                button.set_colour("grey", QColor(colours["grey"]), enabled=False)
                continue
            worst = max((result.items[i].colour for i in self._row_items[grid_row]), key=_ORDER.get, default=GREEN)
            button.set_colour(worst, QColor(colours[worst]), enabled=True)
        if result is None or self._frame is None or self._sheet is None:
            return
        for r in result.items:
            cell = self._cell(r.item.index)
            if r.colour == GREEN or cell is None:
                continue
            self._mark(tint(cell, colours[r.colour], self._s.tint_alpha), _TINT_Z)
            if P_NO_RECEIPT in r.problems:
                self._mark(label(cell, NO_RECEIPT_TEXT, colours[RED], cell.height() * self._s.label_height_frac),
                           _LABEL_Z)

    def show_message(self, text: str) -> None:
        """A passing message (what the check waits for); a drawing problem stays until another sheet is shown."""
        text = " ".join(t for t in (self._draw_problem, text) if t)
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def select_item(self, item: int) -> None:
        """The amount shown on its receipt: outlined, its row outlined and brought to the middle."""
        row = self._item_row.get(item)
        if row is None:
            return
        self.current_item = item
        self._outline_row(row)
        self._set_outline("_item_outline", self._cell(item))
        self._centre(row)

    def follow_row(self, row: int | None) -> None:
        """The receipt page in view belongs to this claim row (None: to none). The sheet
        moves only when the row changes."""
        if row == self.current_row:
            return
        if row is None or row not in self._bands:
            self.current_row = None
            self._set_outline("_row_outline", None)
            self._set_outline("_item_outline", None)
            return
        self._outline_row(row)
        if self.current_item is not None and self._item_row.get(self.current_item) != row:
            self._set_outline("_item_outline", None)
        self._centre(row)

    def row_of(self, item: int) -> int | None:
        return self._item_row.get(item)

    @property
    def buttons(self) -> dict[int, RowButton]:
        return dict(self._buttons)

    @property
    def marks(self) -> list:
        return list(self._marks)

    # ---------------------------------------------------------------- internal

    def _reset(self) -> None:
        self._sheet: ClaimSheet | None = None
        self._result: ClaimCheck | None = None
        self._frame: Frame | None = None
        self._buttons: dict[int, RowButton] = {}
        self._bands: dict[int, QRectF] = {}
        self._row_items: dict[int, list[int]] = {}
        self._item_row: dict[int, int] = {}
        self._marks: list = []
        self._row_outline = self._item_outline = None
        self._draw_problem = ""
        self.current_row: int | None = None
        self.current_item: int | None = None

    def _on_row(self, row: int) -> None:
        items = self._row_items.get(row, [])
        if not items:
            return
        if self.current_item in items:
            chosen = items[(items.index(self.current_item) + 1) % len(items)]
        else:
            chosen = items[0]
        self.item_chosen.emit(chosen)

    def _cell(self, item: int) -> QRectF | None:
        if self._sheet is None or self._frame is None or self._sheet.place is None:
            return None
        it = next((i for i in self._sheet.items if i.index == item), None)
        box = self._sheet.place.cell(it.grid_row, it.grid_col) if it else None
        return self._frame.rect(box) if box else None

    def _mark(self, item, z: float) -> None:
        self.canvas.add(item, z)
        self._marks.append(item)

    def _outline_row(self, row: int) -> None:
        self.current_row = row
        self._set_outline("_row_outline", self._bands.get(row))

    def _set_outline(self, name: str, rect: QRectF | None) -> None:
        old = getattr(self, name)
        if old is not None:
            self.canvas.remove(old)
        new = None
        if rect is not None:
            width = self._s.current_line_px + (1 if name == "_item_outline" else 0)
            new = outline(rect, self._s.current_colour, width)
            self.canvas.add(new, _OUTLINE_Z)
        setattr(self, name, new)

    def _centre(self, row: int) -> None:
        band = self._bands.get(row)
        if band is not None:
            self.canvas.centre_on(band.center().y())

    def _on_tab(self, index: int) -> None:
        if not self._quiet and index >= 0:
            self.tab_changed.emit(index)
