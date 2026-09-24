"""Layout: grouping OCR text segments into the printed rows they came from.

Public entry points: load_row_rules(), group_rows(), TextRow (rows.py).
Imports nothing from OCR or GUI code — it works on any object with a
`.text` string and a `.box` of four corner points, so the matcher can reuse
it later without depending on the OCR module.
"""

from app.layout.rows import RowRules, Segment, TextRow, group_rows, load_row_rules, ungrouped_rows

__all__ = ["RowRules", "Segment", "TextRow", "group_rows", "load_row_rules", "ungrouped_rows"]
