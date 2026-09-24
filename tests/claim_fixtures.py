"""Synthetic claim forms for the tests: the owner's template layout, fabricated values only.

form_grid() lays out a claim form like the real one — a title, a ruled
"Name … Date …" line, a header row, two header-block rows holding ledger
codes, data rows, a Total row, Less Advance, Balance — as a list of rows of
cell values (columns A..O). It is then written as an Excel workbook
(write_workbook) or drawn as a PDF with ruled lines and a text layer
(write_pdf_form), so every reader can be tested on the same claim.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pymupdf

COLUMNS = ["", "Date", "Names of customers visited", "Project number", "Receipt No", "Motor", "Travel (Car",
           "Breakfast", "Lunch", "Dinner", "Daily", "Hotel", "Other", "Rate", "Total:"]
EXPENSE = {"Motor Vehicle Fuel": 5, "Travel": 6, "Breakfast": 7, "Lunch": 8, "Dinner": 9, "Daily Allowance": 10,
           "Hotel": 11, "Other": 12}
RATE, TOTAL = 13, 14
FIRST_DATA_ROW = 7          # the sheet's own row number of the first claim row


def form_grid(entries: list[tuple[object, str, dict[str, object]]], *, total: bool = True,
              rate: object = None, name_line: bool = True) -> list[list[object]]:
    """entries: (date cell, description, {expense column name: amount}). Row numbers match Excel's."""
    width = len(COLUMNS)
    grid: list[list[object]] = [[None] * width for _ in range(2)]
    grid[1][1] = "Cash  Expenses Claim Form"
    top = [None] * width
    if name_line:
        top[1], top[2], top[4], top[12], top[13] = " Name", "A. Tester", "Department", "Date", "24/09/2026"
    grid.append(top)
    grid.append(list(COLUMNS))
    block1 = [None, None, "expense description", "Number (CU INV)", None, "Vehicle Fuel", "Hire,Mileage,",
              4740150, 4740150, 4740150, "Allowance", 4740001, None, None, "Currency :"]
    block2 = [None, None, None, None, None, 4700040, "Taxi) 4740056", None, None, None, 4740080, None, None, None,
              "KES"]
    grid += [block1, block2]
    sums = [Decimal(0)] * width
    for number, (when, text, amounts) in enumerate(entries, start=1):
        row: list[object] = [None, when, text, None, number] + [0] * 8 + [rate, None]
        row_total = Decimal(0)
        for name, value in amounts.items():
            row[EXPENSE[name]] = value
            if isinstance(value, (int, float, Decimal)):
                row_total += Decimal(str(value))
                sums[EXPENSE[name]] += Decimal(str(value))
        row[TOTAL] = row_total
        grid.append(row)
    if total:
        row = [None] * width
        for c in EXPENSE.values():
            row[c] = sums[c]
        row[RATE], row[TOTAL] = "Total", sum(sums)
        grid.append(row)
    grid.append([None] * RATE + ["Less Advance", 10000])
    grid.append([None, None, "Signed :"] + [None] * 10 + ["Balance", 0])
    return grid


def write_workbook(path: Path, tabs: dict[str, list[list[object]]], active: str | None = None) -> Path:
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, grid in tabs.items():
        sheet = book.create_sheet(name)
        for row in grid:
            sheet.append([float(v) if isinstance(v, Decimal) else v for v in row])
    if active is not None:
        book.active = list(tabs).index(active)
    book.save(path)
    return path


def write_pdf_form(path: Path, grid: list[list[object]], ruled_from_row: int = 2) -> Path:
    """The form drawn like an Excel export: ruled cells from `ruled_from_row`, a text layer."""
    widths = [12, 52, 90, 60, 30] + [48] * 8 + [34, 52]
    xs = [20.0]
    for w in widths:
        xs.append(xs[-1] + w)
    row_h, top = 14.0, 40.0
    doc = pymupdf.open()
    page = doc.new_page(width=xs[-1] + 20, height=top + row_h * (len(grid) + 2))
    for r, row in enumerate(grid):
        y = top + r * row_h
        for c, value in enumerate(row):
            text = cell_text(value)
            if text:
                page.insert_text((xs[c] + 2, y + row_h - 4), text, fontsize=6)
    shape = page.new_shape()
    for r in range(ruled_from_row, len(grid) + 1):
        shape.draw_line((xs[0], top + r * row_h), (xs[-1], top + r * row_h))
    for x in xs:
        shape.draw_line((x, top + ruled_from_row * row_h), (x, top + len(grid) * row_h))
    shape.finish(width=0.5)
    shape.commit()
    doc.save(path)
    doc.close()
    return path


def cell_text(value: object) -> str:
    """How the exported PDF shows a cell."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return f"{value:%d/%m/%Y}"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if number == 0:
            return "-"
        if isinstance(value, int) and number >= 1_000_000:
            return str(value)              # a ledger code
        if isinstance(value, int) and number < 100 and number == number.to_integral_value():
            return str(value)              # a receipt number
        return f"{number:,.2f}"
    return str(value).strip()
