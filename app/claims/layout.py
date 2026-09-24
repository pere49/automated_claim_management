"""Finding the claim table on a grid of cells — the same for Excel and PDF.

The header row is the first row (within header_search_rows) that itself
holds the date header and at least min_expense_columns expense column names
(the form's top line "Name … Date …" is ruled too, but holds no expense
names). Under it, a small header block — rows whose filled cells are all
words or ledger codes (the form puts "Vehicle Fuel" and codes like 4740150
there) — is skipped, so codes are never read as amounts. The data rows run
from the first row after the block to the Total row (a row labelled
"Total", where the grand Total is read) or a stop row ("Less Advance").
With no Total label, the last row before the stop is the totals row only
when it holds no date and no words and every amount in it equals the sum
of its column above (the July-EA form).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.claims.amounts import read_amount
from app.claims.model import SheetColumns
from app.claims.rules import ClaimRules

_DATE_LIKE = re.compile(r"\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-,]*\d{2,4}")


@dataclass
class TableLayout:
    header_row: int
    first_data_row: int
    end_row: int                 # the Total row, the stop row, or len(grid)
    total_row: int | None
    columns: SheetColumns
    currency: str | None


def find_layout(grid: list[list[object]], rules: ClaimRules) -> TableLayout | None:
    for r in range(min(len(grid), rules.header_search_rows)):
        date_col = next((c for c, v in enumerate(grid[r]) if norm(v) in rules.date_headers), None)
        if date_col is None:
            continue
        expenses = _expense_columns(grid[r], date_col, rules)
        if len(expenses) < rules.min_expense_columns:
            continue
        header = [norm(v) for v in grid[r]]
        rate = next((c for c, h in enumerate(header) if h in rules.rate_headers), None)
        total = next((c for c, h in enumerate(header)
                      if c not in expenses and (h in rules.total_headers or h.startswith("total:"))), None)
        columns = SheetColumns(date_col, expenses, rate, total)
        first = r + 1 + len(_header_block(grid, r, rules))
        end, total_row = _end(grid, first, columns, rules)
        return TableLayout(r, first, end, total_row, columns, _currency(grid, r, first, rules))
    return None


def norm(value: object) -> str:
    """Lower case, spaces collapsed; dates are not header words."""
    if value is None or isinstance(value, date):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).lower().split())


def _header_block(grid: list[list[object]], header_row: int, rules: ClaimRules) -> list[int]:
    block = []
    for r in range(header_row + 1, min(len(grid), header_row + 1 + rules.header_block_max_rows)):
        if not _header_like(grid[r], rules):
            break
        block.append(r)
    return block


def _header_like(row: list[object], rules: ClaimRules) -> bool:
    filled = [v for v in row if norm(v) and norm(v) not in rules.empty_marks]
    if not filled:
        return False
    for v in filled:
        if isinstance(v, date):
            return False
        text = norm(v)
        if text.isdigit():
            if len(text) < rules.ledger_code_min_digits:
                return False
            continue
        if isinstance(v, (int, float)) or _DATE_LIKE.search(text) or read_amount(text, rules)[0] is not None:
            return False
    return True


def _expense_columns(header: list[object], date_col: int, rules: ClaimRules) -> dict[int, str]:
    words = {c: set(re.findall(r"[a-z]+", norm(v))) for c, v in enumerate(header)}
    found: dict[int, str] = {}
    for column in rules.expense_columns:
        for c in range(len(header)):
            if c != date_col and c not in found and set(column.words) <= words[c]:
                found[c] = column.name
                break
    return found


def _end(grid: list[list[object]], first: int, columns: SheetColumns, rules: ClaimRules) -> tuple[int, int | None]:
    stop = len(grid)
    for r in range(first, len(grid)):
        cells = {norm(v) for v in grid[r]}
        if cells & rules.total_row_labels:
            return r, r
        if any(cell.startswith(label) for cell in cells for label in rules.stop_row_labels):
            stop = r
            break
    last = next((r for r in range(stop - 1, first, -1) if any(norm(v) for v in grid[r])), None)
    if last is not None and _is_sum_row(grid, first, last, columns, rules):
        return last, last
    return stop, None


def _is_sum_row(grid: list[list[object]], first: int, r: int, columns: SheetColumns, rules: ClaimRules) -> bool:
    """No date, no words, and every amount equal to the sum of its column above it."""
    row = grid[r]
    amount_cols = set(columns.expenses) | {c for c in (columns.total,) if c is not None}
    for c, v in enumerate(row):
        text = norm(v)
        if not text or text in rules.empty_marks:
            continue
        if c == columns.date or c not in amount_cols | {columns.rate}:
            return False
    sums = 0
    for c in columns.expenses:
        value, problem = read_amount(row[c], rules, calculated=True)
        if problem:
            return False
        if value is None:
            continue
        above = sum((read_amount(grid[i][c], rules)[0] or 0) for i in range(first, r))
        if value != above:
            return False
        sums += 1
    return sums > 0


def _currency(grid: list[list[object]], header_row: int, first: int, rules: ClaimRules) -> str | None:
    for r in range(header_row, first):
        for v in grid[r]:
            for token in re.findall(r"[A-Za-z]+", norm(v)):
                if token.upper() in rules.currency_codes:
                    return token.upper()
    return None
