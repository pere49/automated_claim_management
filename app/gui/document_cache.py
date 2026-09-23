"""DocumentCache: every file's OCR reading, kept for as long as the app runs.

Opening a file that was read before shows its reading at once; a file that
was only partly read (the officer moved on mid-way) resumes with just the
missing pages. Nothing is written to disk: the cache is lost when the
application closes, which the window says before closing.

A file is recognised by its path, size and modification time together, so
a file that changes on disk is read again rather than shown with a stale
reading. Only OCR results are cached (text, positions, a few measurements —
a few kilobytes per page), never page images.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.errors import StageError
from app.layout import TextRow
from app.ocr import PageResult


@dataclass(frozen=True)
class FileKey:
    path: Path
    size: int
    modified_ns: int


def file_key(path: Path) -> FileKey:
    """Identify the file as it is on disk now. Raises StageError(stage="files")."""
    try:
        stat = path.stat()
    except Exception as exc:
        raise StageError("files", "could not read this file's details", file=path.name, cause=exc) from exc
    return FileKey(path, stat.st_size, stat.st_mtime_ns)


@dataclass
class PageReading:
    result: PageResult
    rows: list[TextRow]
    rows_grouped: bool  # False when rows are one-segment fallbacks (row rules unusable)


@dataclass
class CachedDocument:
    key: FileKey
    page_count: int | None = None           # None until the file has been opened or rendered
    pages: dict[int, PageReading] = field(default_factory=dict)   # 1-based page number -> reading
    failed: bool = False                    # the last attempt to read it could not open the file

    @property
    def path(self) -> Path:
        return self.key.path

    @property
    def pages_read(self) -> int:
        return len(self.pages)

    @property
    def complete(self) -> bool:
        return self.page_count is not None and self.pages_read >= self.page_count

    def missing_pages(self) -> list[int]:
        if self.page_count is None:
            return []
        return [n for n in range(1, self.page_count + 1) if n not in self.pages]


class DocumentCache:
    def __init__(self) -> None:
        self._docs: dict[Path, CachedDocument] = {}

    def get_or_create(self, key: FileKey) -> CachedDocument:
        """The cached document for this exact file version; a stale entry for
        the same path (the file changed on disk) is discarded."""
        doc = self._docs.get(key.path)
        if doc is None or doc.key != key:
            doc = CachedDocument(key)
            self._docs[key.path] = doc
        return doc

    def get(self, path: Path) -> CachedDocument | None:
        return self._docs.get(path)

    def is_current(self, doc: CachedDocument) -> bool:
        """False once `doc` has been replaced by a newer version of its file."""
        return self._docs.get(doc.path) is doc

    def files_with_readings(self) -> int:
        return sum(1 for d in self._docs.values() if d.pages)
