"""Plain-language description of a search result, for the search panel.

Stage B shows what was found, never a verdict (blueprint section 7): per key,
the pages and number of places, possible matches, OCR corrections; which page
is shown and why; how much of the document has been searched.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.gui.search_controller import SearchOutcome
from app.matching import AMOUNT, DATE, PIN, POSSIBLE

KEY_NAMES = {DATE: "Date", AMOUNT: "Amount", PIN: "PIN"}


@dataclass(frozen=True)
class Summary:
    keys: list[tuple[str, str, str]]   # (key, label with value, finding)
    shown: str                         # which page is shown, and why
    progress: str                      # how much was searched


def summarise(outcome: SearchOutcome) -> Summary:
    m = outcome.matches
    q = m.query
    values = {DATE: q.date.strftime("%d/%m/%Y") if q.date else "", AMOUNT: f"{q.amount:,.2f}" if q.amount else "",
              PIN: q.pin or ""}
    keys = []
    for key in q.keys:
        found, possible = m.pages_with(key), m.pages_possible(key)
        places = sum(1 for _, h in m.places(key) if h.strength != POSSIBLE)
        if found:
            text = f"found on {_pages(found)} ({places} place{'s' if places != 1 else ''})"
            if m.corrected(key):
                text += "; read with an OCR character correction"
        else:
            text = "not found" + (" yet" if outcome.still_reading else "")
        if possible:
            text += f"; possible on {_pages(possible)} (decimal point too faint to read)"
        keys.append((key, f"{KEY_NAMES[key]} {values[key]}", text))

    best, complete = m.best_page, m.complete_pages()
    if best is None:
        shown = "Nothing found" + (" yet." if outcome.still_reading else ".")
    elif complete and len(q.keys) > 1:
        others = [n for n in complete if n != best]
        shown = f"Every searched key is on page {best}" + (f" (also on {_pages(others)})" if others else "") + \
                f"; showing page {best}."
    elif len(q.keys) == 1:
        shown = f"Showing page {best}."
    else:
        page = m.pages[best]
        count = sum(page.found(k) for k in q.keys)
        shown = f"No page has every searched key; showing page {best} ({count} of {len(q.keys)} keys)."

    progress = (f"Searched {outcome.searched} of {outcome.total} pages — still reading."
                if outcome.still_reading or outcome.searched < outcome.total
                else f"Searched all {outcome.total} page{'s' if outcome.total != 1 else ''}.")
    if outcome.unreadable:
        progress += f" {outcome.unreadable} page{'s' if outcome.unreadable != 1 else ''} could not be read."
    return Summary(keys, shown, progress)


def _pages(numbers: list[int]) -> str:
    if len(numbers) == 1:
        return f"page {numbers[0]}"
    return "pages " + ", ".join(map(str, numbers[:-1])) + f" and {numbers[-1]}"
