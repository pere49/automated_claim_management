"""Process claim documents through OCR, layout, and matching.

This module deliberately has no UI or web-framework dependency.  A front end
can call :class:`ClaimProcessor` in a worker thread and persist the returned
plain-data result.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Literal

from app.config_files import read_json_config
from app.errors import StageError
from app.layout import group_rows, load_row_rules
from app.matching import (
    AMOUNT,
    CORRECTED,
    DATE,
    EXACT,
    PIN,
    POSSIBLE,
    Query,
    load_matching_rules,
    parse_typed_amount,
    prepare_page,
    search_document,
)
from app.ocr import OcrReader

ClaimStatus = Literal["queued", "processing", "done", "failed"]
DecisionCode = Literal["PASS", "CAUTION", "REVIEW"]
DEFAULT_FIELD_RULES = Path(__file__).with_name("claim_fields.json")


@dataclass
class ClaimPageResult:
    """Serializable OCR and layout output for one document page."""

    page: int
    text: list[str] = field(default_factory=list)
    words: list[dict[str, Any]] = field(default_factory=list)
    rows: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ClaimOcrResult:
    """Flet-agnostic result returned after processing one claim document."""

    status: ClaimStatus
    pages: list[ClaimPageResult] = field(default_factory=list)
    matches: dict[str, str] = field(default_factory=dict)
    extracted: dict[str, str] = field(default_factory=dict)
    table: dict[str, Any] = field(default_factory=dict)
    suggested_decision: DecisionCode = "REVIEW"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible data for claim metadata persistence."""
        return asdict(self)


class ClaimProcessor:
    """Run the reusable backend pipeline for one claim document."""

    def __init__(
        self,
        *,
        reader: Any | None = None,
        reader_factory: Callable[[], Any] = OcrReader,
        dpi: int = 300,
    ) -> None:
        if dpi <= 0:
            raise ValueError("dpi must be greater than zero")
        self._reader = reader
        self._reader_factory = reader_factory
        self._dpi = dpi
        self._row_rules: Any | None = None
        self._matching_rules: Any | None = None
        self._field_rules: dict[str, Any] | None = None

    def process_claim(
        self,
        source_path: str | Path,
        *,
        claim_date: date | str | None = None,
        claimed_amount: Decimal | str | None = None,
        pin: str | None = None,
    ) -> ClaimOcrResult:
        """OCR and search a claim document without exposing backend errors."""
        path = Path(source_path)
        result = ClaimOcrResult(status="processing")
        prepared_pages: dict[int, Any] = {}

        try:
            reader = self._reader or self._reader_factory()
            reader.start()
            pages = reader.load_pages(path, self._dpi)
            self._row_rules = self._row_rules or load_row_rules()
            self._matching_rules = self._matching_rules or load_matching_rules()
            self._field_rules = self._field_rules or _load_field_rules()
        except StageError as exc:
            result.status = "failed"
            result.errors.append(exc.summary)
            return result
        except Exception as exc:
            result.status = "failed"
            result.errors.append(_unexpected_error("processing", path, exc))
            return result

        query, query_error = _build_query(claim_date, claimed_amount, pin, self._matching_rules)
        if query_error is not None:
            result.status = "failed"
            result.errors.append(query_error)
            return result

        for page in pages:
            page_result = ClaimPageResult(page=page.number)
            try:
                ocr_result = reader.read_page(page)
                page_result.words = [_word_data(word) for word in ocr_result.words]
                page_result.text = [str(word.text) for word in ocr_result.words]
                if ocr_result.error is not None:
                    page_result.errors.append(ocr_result.error.summary)
                if ocr_result.warning is not None:
                    page_result.errors.append(ocr_result.warning.summary)
                if ocr_result.error is None:
                    rows = group_rows(ocr_result.words, self._row_rules)
                    page_result.rows = [row.text for row in rows]
                    prepared_pages[page.number] = prepare_page(rows, self._matching_rules)
            except StageError as exc:
                page_result.errors.append(exc.summary)
            except Exception as exc:
                page_result.errors.append(_unexpected_error("page processing", path, exc, page.number))
            result.pages.append(page_result)
            result.errors.extend(page_result.errors)

        result.extracted = _extract_fields(result.pages, self._matching_rules, self._field_rules)
        try:
            result.table = _extract_pdf_table(path)
            table_total = result.table.get("Total")
            if table_total:
                amount = _parse_table_amount(str(table_total), self._matching_rules)
                if amount is not None:
                    result.extracted["claimed_amount"] = str(amount)
        except Exception as exc:
            result.errors.append(_unexpected_error("table extraction", path, exc))
        try:
            matches = search_document(prepared_pages, query, self._matching_rules)
            result.matches = {
                DATE: _match_status(matches, DATE),
                AMOUNT: _match_status(matches, AMOUNT),
                PIN: _match_status(matches, PIN),
            }
            result.errors.extend(error.summary for error in matches.errors)
        except StageError as exc:
            result.errors.append(exc.summary)
        except Exception as exc:
            result.errors.append(_unexpected_error("matching", path, exc))

        result.suggested_decision = _decision(result.matches, result.errors, query.keys)
        result.status = "failed" if not prepared_pages else "done"
        return result


def _extract_pdf_table(path: Path) -> dict[str, Any]:
    """Extract the first claim table into JSON-compatible structures."""
    if path.suffix.lower() != ".pdf":
        return {}

    import pdfplumber

    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return {}
        table = pdf.pages[0].extract_table()
    if not table:
        return {}
    return _structure_table(table)


def _structure_table(table: list[list[str | None]]) -> dict[str, Any]:
    """Normalize the claim-table layout used by the card-expense forms."""
    rows = [[cell.strip() if isinstance(cell, str) else cell for cell in row] for row in table]
    header = [cell for cell in rows[0] if cell is not None] if rows else []
    details = rows[1] if len(rows) > 1 else []
    data_columns = rows[2] if len(rows) > 2 else (rows[0] if rows else [])
    data_rows: list[dict[str, Any]] = []
    total: str | None = None

    for row in rows[3:] if len(rows) > 3 else []:
        first_value = str(row[0] or "").strip()
        if not first_value:
            continue
        if first_value.lower() == "total":
            total = next((str(value).strip() for value in reversed(row) if value not in (None, "")), None)
            break
        data_rows.append(dict(zip(data_columns, row)))

    return {
        "header": header,
        "Document Details": _description_from_row(details),
        "data_columns": data_columns,
        "data_rows": data_rows,
        "Total": total,
    }


def _description_from_row(row: list[str | None]) -> dict[str, str]:
    values = [str(value).strip() for value in row if value not in (None, "")]
    return dict(zip(values[::2], values[1::2]))


def _parse_table_amount(value: str, matching_rules: Any) -> Decimal | None:
    for token in value.replace(":", " ").split():
        try:
            return parse_typed_amount(token.strip("$€£,"), matching_rules)
        except ValueError:
            continue
    return None


def _build_query(
    claim_date: date | str | None,
    claimed_amount: Decimal | str | None,
    pin: str | None,
    rules: Any,
) -> tuple[Query, str | None]:
    try:
        parsed_date = date.fromisoformat(claim_date) if isinstance(claim_date, str) else claim_date
        parsed_amount = Decimal(claimed_amount) if isinstance(claimed_amount, str) else claimed_amount
        if parsed_amount is not None:
            parsed_amount = parsed_amount.quantize(Decimal("0.01"))
        return Query(date=parsed_date, amount=parsed_amount, pin=pin), None
    except (TypeError, ValueError, ArithmeticError) as exc:
        return Query(), _unexpected_error("query", None, exc)


def _load_field_rules() -> dict[str, Any]:
    return dict(read_json_config(DEFAULT_FIELD_RULES, {
        "claimant_labels": list,
        "project_labels": list,
        "date_labels": list,
        "amount_labels": list,
        "date_formats": list,
    }))


def _extract_fields(
    pages: list[ClaimPageResult],
    matching_rules: Any,
    field_rules: dict[str, Any],
) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for page in pages:
        for row in page.rows:
            _extract_label_value(row, field_rules["claimant_labels"], "individual_name", extracted)
            _extract_label_value(row, field_rules["project_labels"], "project_name", extracted)
            _extract_date(row, field_rules, extracted)
            _extract_amount(row, field_rules, matching_rules, extracted)
    return extracted


def _extract_label_value(
    row: str,
    labels: list[str],
    key: str,
    extracted: dict[str, str],
) -> None:
    if key in extracted:
        return
    lowered = row.lower()
    for label in sorted(labels, key=len, reverse=True):
        prefix = f"{label.lower()}:"
        if lowered.startswith(prefix):
            value = row[len(prefix):].strip()
            if value:
                extracted[key] = value
                return


def _extract_date(row: str, field_rules: dict[str, Any], extracted: dict[str, str]) -> None:
    if "claim_date" in extracted:
        return
    lowered = row.lower()
    for label in sorted(field_rules["date_labels"], key=len, reverse=True):
        prefix = f"{label.lower()}:"
        if lowered.startswith(prefix):
            candidate = row[len(prefix):].strip().split("|", 1)[0].strip()
            for fmt in field_rules["date_formats"]:
                try:
                    extracted["claim_date"] = datetime.strptime(candidate, fmt).date().isoformat()
                    return
                except ValueError:
                    continue


def _extract_amount(
    row: str,
    field_rules: dict[str, Any],
    matching_rules: Any,
    extracted: dict[str, str],
) -> None:
    if "claimed_amount" in extracted:
        return
    lowered = row.lower()
    if not any(label.lower() in lowered for label in field_rules["amount_labels"]):
        return
    for token in row.replace(":", " ").split():
        candidate = token.strip("$€£,")
        try:
            value = parse_typed_amount(candidate, matching_rules)
        except ValueError:
            continue
        extracted["claimed_amount"] = str(value)
        return


def _word_data(word: Any) -> dict[str, Any]:
    return {
        "text": str(word.text),
        "confidence": word.confidence,
        "box": word.box,
        "page_box": word.page_box,
    }


def _match_status(matches: Any, key: str) -> str:
    if matches.pages_with(key):
        return CORRECTED if matches.corrected(key) else EXACT
    if matches.pages_possible(key):
        return POSSIBLE
    return "MISSING"


def _decision(matches: dict[str, str], errors: list[str], keys: tuple[str, ...]) -> DecisionCode:
    if errors or not keys:
        return "REVIEW"
    statuses = [matches[key] for key in keys]
    if any(status == "MISSING" for status in statuses):
        return "REVIEW"
    if any(status in (CORRECTED, POSSIBLE) for status in statuses):
        return "CAUTION"
    return "PASS"


def _unexpected_error(stage: str, path: Path | None, exc: Exception, page: int | None = None) -> str:
    error = StageError(stage, "an unexpected processing error occurred", file=path.name if path else None,
                       page=page, cause=exc)
    return error.summary
