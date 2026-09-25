"""Optional JSON export of the in-memory OCR cache.

The application continues to use DocumentCache for live work. This module
only writes a snapshot when an export path is configured, so a disk failure
cannot interrupt OCR or change the review flow.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.gui.document_cache import CachedDocument, PageReading
from app.ocr.pipeline import OcrStageError


def export_document(document: CachedDocument, destination: Path) -> None:
    """Write one document's current OCR readings as a replaceable JSON snapshot."""
    payload = {
        "schema_version": "1.0",
        "storage": "json_snapshot",
        "source": str(document.path),
        "page_count": document.page_count,
        "pages": [_page_payload(number, document.pages[number]) for number in sorted(document.pages)],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent,
                prefix=f".{destination.stem}-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, destination)
    except Exception as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise OcrStageError(
            "ocr-export", "OCR readings could not be written to the JSON export",
            file=destination.name, cause=exc,
        ) from exc


def _page_payload(number: int, reading: PageReading) -> dict[str, Any]:
    result = reading.result
    return {
        "page": number,
        "status": "error" if result.error else "warning" if result.warning else "complete",
        "seconds": result.seconds,
        "words": [
            {
                "text": word.text,
                "confidence": word.confidence,
                "box": word.box,
                "page_box": word.page_box,
            }
            for word in result.words
        ],
        "rows": [
            {
                "text": row.text,
                "segments": [
                    {
                        "text": segment.text,
                        "left": segment.left,
                        "right": segment.right,
                        "top": segment.top,
                        "bottom": segment.bottom,
                    }
                    for segment in row.segments
                ],
            }
            for row in reading.rows
        ],
        "warning": result.warning.summary if result.warning else None,
        "error": result.error.summary if result.error else None,
    }
