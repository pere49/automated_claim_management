"""A grid of cells -> a ClaimSheet: rows, claim items, dates, grand Total.

Every non-zero amount in an expense column is one claim item paired with
its row's date (owner, decisions D24). Rows with nothing claimed are
skipped. A cell that cannot be read becomes an item with a problem (shown
yellow), never a stop. Dates of the whole sheet are read together
(sheet_dates.py).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.claims.amounts import read_amount, read_rate
from app.claims.layout import find_layout
from app.claims.model import ClaimItem, ClaimRow, ClaimSheet
from app.claims.rules import ClaimRules
from app.claims.sheet_dates import read_dates


def build_sheet(name: str, grid: list[list[object]], row_numbers: list[int], rules: ClaimRules,
                today: date) -> ClaimSheet | None:
    """None when the grid holds no claim table."""
    width = max((len(r) for r in grid), default=0)
    grid = [list(r) + [None] * (width - len(r)) for r in grid]
    layout = find_layout(grid, rules)
    if layout is None:
        return None
    cols = layout.columns
    raw_rows = []
    for r in range(layout.first_data_row, layout.end_row):
        cells = [(c, *read_amount(grid[r][c], rules)) for c in sorted(cols.expenses)]
        claimed = [(c, amount, problem) for c, amount, problem in cells if amount is not None or problem]
        if claimed:
            raw_rows.append((r, claimed))

    dates = read_dates([grid[r][cols.date] for r, _ in raw_rows], today, rules)
    rows, index = [], 0
    for (r, claimed), when in zip(raw_rows, dates):
        rate, rate_problem = read_rate(grid[r][cols.rate], rules) if cols.rate is not None else (Decimal(1), None)
        total, total_problem = (read_amount(grid[r][cols.total], rules, calculated=True)
                                if cols.total is not None else (None, None))
        items = []
        for c, amount, problem in claimed:
            items.append(ClaimItem(index, row_numbers[r], r, c, cols.expenses[c], amount, when, rate, problem))
            index += 1
        problems = [p for p in (rate_problem, total_problem and "the row's Total could not be read") if p]
        rows.append(ClaimRow(row_numbers[r], r, when, items, rate, total, problems))

    grand, grand_cell, problems = _grand_total(grid, layout, rules)
    return ClaimSheet(name, grid, layout.header_row, layout.first_data_row, layout.end_row, cols, rows, grand,
                      grand_cell, layout.currency, row_numbers, problems)


def _grand_total(grid, layout, rules) -> tuple[Decimal | None, tuple[int, int] | None, list[str]]:
    if layout.total_row is None:
        return None, None, ["no Total row was found under the claimed amounts"]
    r = layout.total_row
    order = ([layout.columns.total] if layout.columns.total is not None else []) + list(range(len(grid[r]) - 1, -1, -1))
    for c in order:
        value, problem = read_amount(grid[r][c], rules, calculated=True)
        if value is not None:
            return value, (r, c), []
    return None, None, ["the grand Total has no value saved in the file (open it in Excel and save it again)"]
