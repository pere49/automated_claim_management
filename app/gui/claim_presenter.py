"""From a checked claim to what the window shows on the receipts (D35, D39).

    badges(result, ...)      one badge per receipt page, in its status colour
    claim_places(result)     every claimed amount's highlights on its linked page —
                             all shown at once, so scrolling never loses them
    row_of_page(result, n)   the claim row whose amount is linked to page n (None: none)
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from app.checking import ClaimCheck
from app.gui.page_badges import Badge


def badges(result: ClaimCheck | None, colours: dict[str, str], text_colour: str) -> list[Badge]:
    if result is None:
        return []
    text = QColor(text_colour)
    return [Badge(n, page.lines, QColor(colours[page.colour]), text) for n, page in sorted(result.pages.items())]


def claim_places(result: ClaimCheck | None) -> list[tuple[int, object]]:
    if result is None:
        return []
    return [(r.page, hit) for r in result.items if r.page is not None for hit in r.hits]


def row_of_page(result: ClaimCheck | None, page: int) -> int | None:
    if result is None or page not in result.pages or result.pages[page].item is None:
        return None
    return result.items[result.pages[page].item].item.grid_row
