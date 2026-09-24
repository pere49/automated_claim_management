"""Reading an Excel workbook (.xlsx / .xlsm) into one grid of cells per tab.

openpyxl (already installed) in read-only mode, values as last saved by
Excel (a formula gives its saved result). Tens of milliseconds for a claim
form; the file may be open in Excel at the same time. Old .xls files are
refused by reader.py (reading them would need another library).
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from app.errors import StageError


def read_workbook(path: Path) -> tuple[list[tuple[str, list[list[object]]]], str | None]:
    """([(tab name, grid)], the tab the workbook was saved on). Grid row i is
    the sheet's row i + 1. Raises StageError(stage="claim sheet")."""
    try:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise StageError("claim sheet", "could not open this Excel file (it may be damaged, password-protected "
                         "or not an Excel file)", file=path.name, cause=exc) from exc
    try:
        tabs = []
        for sheet in book.worksheets:
            grid = [list(row) for row in sheet.iter_rows(min_row=1, values_only=True)]
            tabs.append((sheet.title, grid))
        active = book.active.title if book.active is not None else None
        return tabs, active
    except Exception as exc:
        raise StageError("claim sheet", "could not read the cells of this Excel file", file=path.name,
                         cause=exc) from exc
    finally:
        book.close()
