"""Scanned claim sheets: the table's lines found in the picture, OCR words placed in them.

The picture is thresholded (adaptive, so uneven lighting does not matter)
and opened with long thin kernels: what survives is the ruled lines, not
the text. Vertical lines must be longer than any digit is tall. The OCR
words (in the same pixel frame as the picture) are then placed in the cells
(table_grid.py); an OCR segment holding several words is split so each word
lands in its own column. Positions stay in the picture's pixels.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.claims.rules import ClaimRules
from app.claims.table_grid import Table, Word, build_table, cluster


def table_from_picture(gray: np.ndarray, segments: list[Word], rules: ClaimRules) -> Table:
    rows, cols = find_lines(gray, rules)
    return build_table(split_words(segments), rows, cols, rules.image_min_band_px)


def find_lines(gray: np.ndarray, rules: ClaimRules) -> tuple[list[float], list[float]]:
    height, width = gray.shape[:2]
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV,
                                rules.image_threshold_block_px, rules.image_threshold_offset)
    h_len = max(2, int(width * rules.image_line_min_length_frac))
    v_len = max(2, int(height * rules.image_vertical_min_length_frac))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len)))
    thick = rules.image_line_max_thickness_px
    ys = [y + h / 2 for x, y, w, h in _boxes(horizontal) if w >= h_len and h <= thick]
    xs = [x + w / 2 for x, y, w, h in _boxes(vertical) if h >= v_len and w <= thick]
    return cluster(ys, rules.image_line_cluster_px), cluster(xs, rules.image_line_cluster_px)


def split_words(segments: list[Word]) -> list[Word]:
    """An OCR segment of several words -> one entry per word, x spread by character count."""
    out = []
    for x0, y0, x1, y1, text in segments:
        parts = text.split()
        if len(parts) <= 1:
            out.append((x0, y0, x1, y1, text))
            continue
        per_char = (x1 - x0) / max(1, len(text))
        start = 0
        for part in parts:
            at = text.index(part, start)
            out.append((x0 + at * per_char, y0, x0 + (at + len(part)) * per_char, y1, part))
            start = at + len(part)
    return out


def _boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    return [tuple(int(v) for v in stats[i][:4]) for i in range(1, count)]
