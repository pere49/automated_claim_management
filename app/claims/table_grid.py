"""Rebuilding a table's cells from positioned words and its drawn lines.

Shared by PDF sheets (lines drawn in the PDF) and scanned sheets (lines
found in the picture). Each word goes into the cell whose row band and
column band hold its centre — so a value printed a little high or low in
its cell, or a row whose description wraps onto two text lines, still lands
in the right row. Words outside the ruled table (the title, the name, the
signatures) are left out. Rows with no text at all are dropped.
"""

from __future__ import annotations

from bisect import bisect_right

Word = tuple[float, float, float, float, str]      # x0, y0, x1, y1, text


def build_grid(words: list[Word], row_lines: list[float], col_lines: list[float],
               min_band: float) -> list[list[str | None]]:
    rows, cols = _bands(row_lines, min_band), _bands(col_lines, min_band)
    if len(rows) < 2 or len(cols) < 2:
        return []
    cells: dict[tuple[int, int], list[Word]] = {}
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if not (rows[0] <= cy < rows[-1] and cols[0] <= cx < cols[-1]):
            continue
        cell = (bisect_right(rows, cy) - 1, bisect_right(cols, cx) - 1)
        cells.setdefault(cell, []).append(w)
    grid = []
    for r in range(len(rows) - 1):
        row = [_text(cells.get((r, c), [])) for c in range(len(cols) - 1)]
        if any(row):
            grid.append(row)
    return grid


def cluster(positions: list[float], tolerance: float) -> list[float]:
    """Positions within `tolerance` of each other become one (their mean)."""
    groups: list[list[float]] = []
    for p in sorted(positions):
        if groups and p - groups[-1][-1] <= tolerance:
            groups[-1].append(p)
        else:
            groups.append([p])
    return [sum(g) / len(g) for g in groups]


def _bands(lines: list[float], min_band: float) -> list[float]:
    out: list[float] = []
    for p in sorted(lines):
        if not out or p - out[-1] >= min_band:
            out.append(p)
    return out


def _text(words: list[Word]) -> str | None:
    if not words:
        return None
    height = max(1.0, min(w[3] - w[1] for w in words))
    ordered = sorted(words, key=lambda w: (round(w[1] / height), w[0]))
    return " ".join(w[4] for w in ordered)
