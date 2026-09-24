"""FilePanel: the left pane — the claim files in the working folder.

Clicking a file (or pressing Enter on it) asks to open it via `file_chosen`.
The open file is shown in bold, independently of the selection, so browsing
the list with the keyboard never suggests a file is open when it is not.
Each file can carry a short state beside its name (set_state: "read",
"reading 2/4", ...), so the officer can see which files are ready.

Stage C: two slots above the list show the claim sheet and the receipts
being checked (set_slots). Right-clicking a file offers "Use as claim sheet"
and "Use as receipts" — for a scanned claim sheet, which cannot be told from
receipts before it is read.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QToolButton, QVBoxLayout,
                               QWidget)

from app.errors import ERROR, StageError

_PATH_ROLE = Qt.ItemDataRole.UserRole


class FilePanel(QWidget):
    file_chosen = Signal(Path)
    sheet_requested = Signal(Path)
    receipts_requested = Signal(Path)
    sheet_cleared = Signal()
    listed = Signal(object)          # list[Path] of the files now shown, in order
    problem = Signal(object, str)

    def __init__(self, folder: Path, extensions: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._extensions = extensions
        self._open_path: Path | None = None
        self._states: dict[Path, str] = {}
        self._sheet_path: Path | None = None

        self._title = QLabel(f"<b>Files</b> — {folder.name}")
        self._title.setToolTip(str(folder))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemClicked.connect(self._on_item)
        self._list.itemActivated.connect(self._on_item)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._menu)
        self.sheet_slot, self.receipts_slot = QLabel(), QLabel()
        for slot in (self.sheet_slot, self.receipts_slot):
            slot.setWordWrap(True)
        self._clear_sheet = QToolButton()
        self._clear_sheet.setText("✕")
        self._clear_sheet.setToolTip("Stop checking this claim sheet")
        self._clear_sheet.clicked.connect(self.sheet_cleared)
        sheet_row = QHBoxLayout()
        sheet_row.addWidget(self.sheet_slot, 1)
        sheet_row.addWidget(self._clear_sheet)
        self._empty = QLabel()
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(sheet_row)
        layout.addWidget(self.receipts_slot)
        layout.addWidget(self._title)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty)

    def refresh(self) -> None:
        """Re-scan the working folder."""
        self._list.clear()
        try:
            files = _scan(self._folder, self._extensions)
        except StageError as exc:
            self.problem.emit(exc, ERROR)
            files = []
            self._empty.setText("The working folder could not be read — see the Errors tab.")
        else:
            self._empty.setText("" if files else f"No {', '.join(self._extensions)} files in this folder.")
        for path in files:
            item = QListWidgetItem()
            item.setData(_PATH_ROLE, str(path))
            item.setToolTip(str(path))
            self._list.addItem(item)
            self._label(item)
        self._empty.setVisible(not files)
        self.mark_open(self._open_path)
        self.listed.emit(files)

    def set_slots(self, sheet: Path | None, receipts: Path | None) -> None:
        """Show which claim sheet and which receipts are being checked."""
        self._sheet_path = sheet
        self.sheet_slot.setText(f"<b>Claim sheet:</b> {sheet.name}" if sheet else "<b>Claim sheet:</b> — (click an "
                                "Excel file, or right-click → Use as claim sheet)")
        self.receipts_slot.setText(f"<b>Receipts:</b> {receipts.name}" if receipts else "<b>Receipts:</b> — (click a PDF)")
        self._clear_sheet.setEnabled(sheet is not None)
        for i in range(self._list.count()):
            self._label(self._list.item(i))

    def set_state(self, path: Path, state: str) -> None:
        """Show a short state beside this file's name ("" clears it)."""
        self._states[path] = state
        for i in range(self._list.count()):
            item = self._list.item(i)
            if Path(item.data(_PATH_ROLE)) == path:
                self._label(item)

    def file_names(self) -> list[str]:
        return [Path(self._list.item(i).data(_PATH_ROLE)).name for i in range(self._list.count())]

    def state_of(self, name: str) -> str:
        return next((s for p, s in self._states.items() if p.name == name), "")

    def _label(self, item: QListWidgetItem) -> None:
        path = Path(item.data(_PATH_ROLE))
        state = self._states.get(path, "")
        marks = [m for m in ("claim sheet" if path == self._sheet_path else "", state) if m]
        item.setText(f"{path.name}   — {' · '.join(marks)}" if marks else path.name)

    def mark_open(self, path: Path | None) -> None:
        """Show `path` as the open file (bold and selected); None clears it."""
        self._open_path = path
        self._list.blockSignals(True)
        self._list.clearSelection()
        for i in range(self._list.count()):
            item = self._list.item(i)
            is_open = path is not None and Path(item.data(_PATH_ROLE)) == path
            font = item.font()
            font.setBold(is_open)
            item.setFont(font)
            if is_open:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def _on_item(self, item: QListWidgetItem) -> None:
        self.file_chosen.emit(Path(item.data(_PATH_ROLE)))

    def _menu(self, at: QPoint) -> None:
        item = self._list.itemAt(at)
        if item is None:
            return
        path = Path(item.data(_PATH_ROLE))
        menu = QMenu(self)
        menu.addAction("Use as claim sheet", lambda: self.sheet_requested.emit(path))
        menu.addAction("Use as receipts", lambda: self.receipts_requested.emit(path))
        menu.exec(self._list.viewport().mapToGlobal(at))


def _scan(folder: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Files in `folder` (not sub-folders) with one of `extensions`, by name."""
    try:
        return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions),
                      key=lambda p: p.name.lower())
    except Exception as exc:
        raise StageError("files", "could not list the working folder", file=str(folder), cause=exc) from exc
