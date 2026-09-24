"""ClaimRules: how a claim sheet is read, from claim_rules.json, checked."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config_files import read_json_config
from app.errors import StageError

DEFAULT_CLAIM_RULES = Path(__file__).resolve().with_name("claim_rules.json")


@dataclass(frozen=True)
class ExpenseColumn:
    name: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class ClaimRules:
    date_headers: frozenset[str]
    expense_columns: tuple[ExpenseColumn, ...]
    expense_range: tuple[str, str]           # names of the first and last expense columns
    min_expense_columns: int
    rate_headers: frozenset[str]
    total_headers: frozenset[str]
    total_row_labels: frozenset[str]
    stop_row_labels: frozenset[str]
    header_search_rows: int
    header_block_max_rows: int
    ledger_code_min_digits: int
    empty_marks: frozenset[str]
    currency_codes: frozenset[str]
    month_names: dict[str, int]              # lower-case name -> month number
    ocr_digit_repairs: dict[str, str]
    date_years: tuple[int, int]
    max_claim_span_days: int
    pdf_min_text_words: int
    pdf_line_min_length_pt: float
    pdf_line_cluster_pt: float
    pdf_min_band_pt: float
    image_line_min_length_frac: float
    image_vertical_min_length_frac: float
    image_line_max_thickness_px: int
    image_line_cluster_px: int
    image_min_band_px: int
    image_threshold_block_px: int
    image_threshold_offset: int


def load_claim_rules(path: Path = DEFAULT_CLAIM_RULES) -> ClaimRules:
    """Read and check claim_rules.json. Raises StageError(stage="config")."""
    number = (int, float)
    d = read_json_config(path, {
        "date_headers": list, "expense_columns": list, "expense_range": list, "min_expense_columns": int,
        "rate_headers": list,
        "total_headers": list, "total_row_labels": list, "stop_row_labels": list, "header_search_rows": int,
        "header_block_max_rows": int, "ledger_code_min_digits": int, "empty_marks": list, "currency_codes": list,
        "month_names": dict, "ocr_digit_repairs": dict, "date_years": list, "max_claim_span_days": int,
        "pdf_min_text_words": int, "pdf_line_min_length_pt": number, "pdf_line_cluster_pt": number,
        "pdf_min_band_pt": number, "image_line_min_length_frac": number, "image_vertical_min_length_frac": number,
        "image_line_max_thickness_px": int, "image_line_cluster_px": int, "image_min_band_px": int,
        "image_threshold_block_px": int, "image_threshold_offset": int,
    })

    def fail(message: str) -> StageError:
        return StageError("config", message, file=path.name)

    def words(key: str) -> frozenset[str]:
        items = d[key]
        if not items or not all(isinstance(i, str) and i.strip() for i in items):
            raise fail(f"'{key}' must be a non-empty list of text")
        return frozenset(" ".join(i.lower().split()) for i in items)

    columns = []
    for entry in d["expense_columns"]:
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"].strip()
                and isinstance(entry.get("words"), list) and entry["words"]
                and all(isinstance(w, str) and w.strip() for w in entry["words"])):
            raise fail("'expense_columns' entries need a 'name' and a non-empty list of 'words'")
        columns.append(ExpenseColumn(entry["name"].strip(), tuple(w.lower().strip() for w in entry["words"])))
    if not columns:
        raise fail("'expense_columns' must list at least one column")
    names = [c.name for c in columns]
    ends = d["expense_range"]
    if len(ends) != 2 or not all(isinstance(e, str) and e.strip() in names for e in ends) or ends[0] == ends[1]:
        raise fail("'expense_range' must name two different columns of 'expense_columns': [first, last]")
    if not 1 <= d["min_expense_columns"] <= len(columns):
        raise fail("'min_expense_columns' must be between 1 and the number of expense columns")

    months: dict[str, int] = {}
    for k, names in d["month_names"].items():
        if not (k.isdigit() and 1 <= int(k) <= 12) or not isinstance(names, list) or not names:
            raise fail("'month_names' must map month numbers 1..12 to lists of names")
        for name in names:
            if not isinstance(name, str) or not name.isalpha():
                raise fail("'month_names' names must be words")
            months[name.lower()] = int(k)
    if set(months.values()) != set(range(1, 13)):
        raise fail("'month_names' must cover all twelve months")
    repairs = d["ocr_digit_repairs"]
    if not all(isinstance(a, str) and len(a) == 1 and isinstance(b, str) and b.isdigit() and len(b) == 1
               for a, b in repairs.items()):
        raise fail("'ocr_digit_repairs' must map single characters to single digits")
    years = d["date_years"]
    if len(years) != 2 or not all(isinstance(y, int) for y in years) or years[0] >= years[1]:
        raise fail("'date_years' must be [first year, last year]")
    positive = ("min_expense_columns", "header_search_rows", "max_claim_span_days", "pdf_min_text_words",
                "image_line_max_thickness_px", "image_line_cluster_px", "image_min_band_px",
                "image_threshold_block_px", "ledger_code_min_digits")
    for key in positive:
        if d[key] <= 0:
            raise fail(f"'{key}' must be greater than zero")
    if d["header_block_max_rows"] < 0:
        raise fail("'header_block_max_rows' must not be negative")
    if d["image_threshold_block_px"] % 2 == 0:
        raise fail("'image_threshold_block_px' must be an odd number")
    for key in ("pdf_line_min_length_pt", "pdf_line_cluster_pt", "pdf_min_band_pt",
                "image_line_min_length_frac", "image_vertical_min_length_frac"):
        if d[key] <= 0:
            raise fail(f"'{key}' must be greater than zero")

    return ClaimRules(
        date_headers=words("date_headers"),
        expense_columns=tuple(columns),
        expense_range=(ends[0].strip(), ends[1].strip()),
        min_expense_columns=d["min_expense_columns"],
        rate_headers=words("rate_headers"),
        total_headers=words("total_headers"),
        total_row_labels=words("total_row_labels"),
        stop_row_labels=words("stop_row_labels"),
        header_search_rows=d["header_search_rows"],
        header_block_max_rows=d["header_block_max_rows"],
        ledger_code_min_digits=d["ledger_code_min_digits"],
        empty_marks=frozenset(d["empty_marks"]),
        currency_codes=frozenset(c.upper() for c in d["currency_codes"]),
        month_names=months,
        ocr_digit_repairs=dict(repairs),
        date_years=(years[0], years[1]),
        max_claim_span_days=d["max_claim_span_days"],
        pdf_min_text_words=d["pdf_min_text_words"],
        pdf_line_min_length_pt=float(d["pdf_line_min_length_pt"]),
        pdf_line_cluster_pt=float(d["pdf_line_cluster_pt"]),
        pdf_min_band_pt=float(d["pdf_min_band_pt"]),
        image_line_min_length_frac=float(d["image_line_min_length_frac"]),
        image_vertical_min_length_frac=float(d["image_vertical_min_length_frac"]),
        image_line_max_thickness_px=d["image_line_max_thickness_px"],
        image_line_cluster_px=d["image_line_cluster_px"],
        image_min_band_px=d["image_min_band_px"],
        image_threshold_block_px=d["image_threshold_block_px"],
        image_threshold_offset=d["image_threshold_offset"],
    )
