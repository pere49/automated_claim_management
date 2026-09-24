"""PDF claim sheets with a text layer (exported from Excel): words and drawn lines.

A sheet exported from Excel carries its text and its cell borders; both are
read exactly with pymupdf — no OCR, a few milliseconds. A page with fewer
than pdf_min_text_words words is a picture and is read by OCR instead
(image_grid.py). Positions are in PDF points; the page size comes along so
they can be turned into fractions of the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.claims.rules import ClaimRules
from app.claims.table_grid import Table, Word, build_table, cluster, printed_area
from app.errors import StageError


@dataclass
class TextPage:
    number: int
    words: list[Word]
    table: Table
    size: tuple[float, float]                                  # page width, height (points)
    printed: tuple[float, float, float, float] | None          # left, top, right, bottom (points)


def text_pages(path: Path, rules: ClaimRules) -> list[TextPage]:
    """Every page's words and its table rebuilt from the drawn lines.
    Raises StageError(stage="claim sheet")."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise StageError("claim sheet", "could not open this PDF", file=path.name, cause=exc) from exc
    try:
        pages = []
        for page in doc:
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
            rows, cols = _lines(page, rules)
            table = build_table(words, rows, cols, rules.pdf_min_band_pt)
            pages.append(TextPage(page.number + 1, words, table, (page.rect.width, page.rect.height),
                                  printed_area(words, table)))
        return pages
    except Exception as exc:
        raise StageError("claim sheet", "could not read the text of this PDF", file=path.name, cause=exc) from exc
    finally:
        doc.close()


def has_text_layer(path: Path, rules: ClaimRules) -> bool:
    """True when the first page carries real text (not a scanned picture)."""
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count > 0 and len(doc[0].get_text("words")) >= rules.pdf_min_text_words
    except Exception as exc:
        raise StageError("claim sheet", "could not open this PDF", file=path.name, cause=exc) from exc


def _lines(page, rules: ClaimRules) -> tuple[list[float], list[float]]:
    horizontal, vertical = [], []
    shortest = rules.pdf_line_min_length_pt
    for path in page.get_drawings():
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.y - b.y) < 0.5 and abs(a.x - b.x) >= shortest:
                    horizontal.append((a.y + b.y) / 2)
                elif abs(a.x - b.x) < 0.5 and abs(a.y - b.y) >= shortest:
                    vertical.append((a.x + b.x) / 2)
            elif item[0] == "re":
                r = item[1]
                if r.height < 2 and r.width >= shortest:
                    horizontal.append((r.y0 + r.y1) / 2)
                elif r.width < 2 and r.height >= shortest:
                    vertical.append((r.x0 + r.x1) / 2)
    return cluster(horizontal, rules.pdf_line_cluster_pt), cluster(vertical, rules.pdf_line_cluster_pt)
