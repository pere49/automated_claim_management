"""FilePanel: the left pane — the claim files in the working folder.

Clicking a file (or pressing Enter on it) asks to open it via `file_chosen`.
The open file is shown in bold, independently of the selection, so browsing
the list with the keyboard never suggests a file is open when it is not.
Each file can carry a short state beside its name (set_state: "read",
"reading 2/4", ...), so the officer can see which files are ready.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.errors import ERROR, StageError

_PATH_ROLE = Qt.ItemDataRole.UserRole


class FilePanel(QWidget):
    file_chosen = Signal(Path)
    listed = Signal(object)          # list[Path] of the files now shown, in order
    problem = Signal(object, str)

    def __init__(self, folder: Path, extensions: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._extensions = extensions
        self._open_path: Path | None = None
        self._states: dict[Path, str] = {}

        self._title = QLabel(f"<b>Files</b> — {folder.name}")
        self._title.setToolTip(str(folder))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemClicked.connect(self._on_item)
        self._list.itemActivated.connect(self._on_item)
        self._empty = QLabel()
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
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
        item.setText(f"{path.name}   — {state}" if state else path.name)

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


def _scan(folder: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Files in `folder` (not sub-folders) with one of `extensions`, by name."""
    try:
        return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions),
                      key=lambda p: p.name.lower())
    except Exception as exc:
        raise StageError("files", "could not list the working folder", file=str(folder), cause=exc) from exc
