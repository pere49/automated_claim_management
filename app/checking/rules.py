"""CheckingRules: the Stage C checking rules, from checking_rules.json, checked."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Formatter

from app.checking.model import PROBLEMS
from app.config_files import read_json_config
from app.errors import StageError

_LINE_FIELDS = {"ok": set(), "amount": {"receipt", "claimed"}, "date": {"receipt", "claimed"},
                "date_not_on_sheet": set(), "pin": set(),
                "other_buyer": set(), "repeated": {"page"}, "unreadable": set(), "no_receipt": set(),
                "no_claim": set(), "unknown": set()}

DEFAULT_CHECKING_RULES = Path(__file__).resolve().with_name("checking_rules.json")


@dataclass(frozen=True)
class CheckingRules:
    total_labels: tuple[tuple[str, ...], ...]      # each label as its words
    not_total_labels: tuple[tuple[str, ...], ...]
    label_letter_slips: int
    not_total_marks: tuple[str, ...]
    total_label_above: bool
    buyer_pin_labels: tuple[tuple[str, ...], ...]
    text_similarity_min: float
    word_min_length: int
    amount_min: int
    date_pattern: re.Pattern
    time_pattern: re.Pattern
    amount_pattern: re.Pattern
    red_problems: frozenset[str]                  # problem keys shown red (rule B, D34); the rest yellow
    badge_lines: dict[str, str]                   # what a badge says, per problem (D35)
    badge_date_format: str


def load_checking_rules(path: Path = DEFAULT_CHECKING_RULES) -> CheckingRules:
    """Read and check checking_rules.json. Raises StageError(stage="config")."""
    d = read_json_config(path, {
        "total_labels": list, "not_total_labels": list, "label_letter_slips": int, "not_total_marks": list,
        "total_label_above": bool, "buyer_pin_labels": list,
        "text_similarity_min": (int, float), "word_min_length": int, "amount_min": (int, float),
        "date_pattern": str, "time_pattern": str, "amount_pattern": str,
        "red_problems": list, "badge_lines": dict, "badge_date_format": str,
    })

    def fail(message: str) -> StageError:
        return StageError("config", message, file=path.name)

    def labels(key: str) -> tuple[tuple[str, ...], ...]:
        items = d[key]
        if not items or not all(isinstance(i, str) and i.strip() for i in items):
            raise fail(f"'{key}' must be a non-empty list of text")
        return tuple(tuple(i.lower().split()) for i in items)

    def pattern(key: str) -> re.Pattern:
        try:
            return re.compile(d[key])
        except re.error as exc:
            raise StageError("config", f"'{key}' is not a valid pattern", file=path.name, cause=exc) from exc

    if not 0 < d["text_similarity_min"] <= 1:
        raise fail("'text_similarity_min' must be above 0 and at most 1")
    if d["label_letter_slips"] < 0 or d["word_min_length"] < 1 or d["amount_min"] < 0:
        raise fail("'label_letter_slips', 'word_min_length' and 'amount_min' must not be negative")
    if not set(d["red_problems"]) <= set(PROBLEMS):
        raise fail(f"'red_problems' may only list {', '.join(PROBLEMS)}")
    lines = d["badge_lines"]
    if set(lines) != set(_LINE_FIELDS) or not all(isinstance(v, str) and v.strip() for v in lines.values()):
        raise fail(f"'badge_lines' must give text for exactly: {', '.join(sorted(_LINE_FIELDS))}")
    for key, text in lines.items():
        try:
            used = {name for _, name, _, _ in Formatter().parse(text) if name is not None}
        except ValueError as exc:
            raise StageError("config", f"'badge_lines' '{key}' is not valid text", file=path.name, cause=exc) from exc
        if used != _LINE_FIELDS[key]:
            wanted = ", ".join("{" + f + "}" for f in sorted(_LINE_FIELDS[key])) or "no {} fields"
            raise fail(f"'badge_lines' '{key}' must use {wanted}")
    try:
        date(2026, 1, 2).strftime(d["badge_date_format"])
    except ValueError as exc:
        raise StageError("config", "'badge_date_format' is not a valid date format", file=path.name, cause=exc) from exc
    return CheckingRules(
        total_labels=labels("total_labels"),
        not_total_labels=labels("not_total_labels"),
        label_letter_slips=d["label_letter_slips"],
        not_total_marks=tuple(str(m) for m in d["not_total_marks"] if str(m)),
        total_label_above=d["total_label_above"],
        buyer_pin_labels=labels("buyer_pin_labels"),
        text_similarity_min=float(d["text_similarity_min"]),
        word_min_length=d["word_min_length"],
        amount_min=d["amount_min"],
        date_pattern=pattern("date_pattern"),
        time_pattern=pattern("time_pattern"),
        amount_pattern=pattern("amount_pattern"),
        red_problems=frozenset(d["red_problems"]),
        badge_lines=dict(lines),
        badge_date_format=d["badge_date_format"],
    )
