"""Found: one place on a page where a searched value was found.

Strength says how sure the find is:
  EXACT      the value exactly, in one of its printed forms
  CORRECTED  the value after a configured OCR character correction (a PIN
             with a letter/digit read in the wrong position, or one
             look-alike character) — counts as found (user decision)
  POSSIBLE   only through a repair that can also match something else (an
             amount whose decimal point OCR could not see) — never a PASS
"""

from __future__ import annotations

from dataclasses import dataclass

EXACT, CORRECTED, POSSIBLE = "exact", "corrected", "possible"


@dataclass(frozen=True)
class Found:
    row: int                    # index of the printed row on the page
    segments: tuple[int, ...]   # indexes of that row's segments holding the value
    strength: str               # EXACT | CORRECTED | POSSIBLE
