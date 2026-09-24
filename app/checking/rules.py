"""CheckingRules: the Stage C checking rules, from checking_rules.json, checked."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config_files import read_json_config
from app.errors import StageError

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


def load_checking_rules(path: Path = DEFAULT_CHECKING_RULES) -> CheckingRules:
    """Read and check checking_rules.json. Raises StageError(stage="config")."""
    d = read_json_config(path, {
        "total_labels": list, "not_total_labels": list, "label_letter_slips": int, "not_total_marks": list,
        "total_label_above": bool, "buyer_pin_labels": list,
        "text_similarity_min": (int, float), "word_min_length": int, "amount_min": (int, float),
        "date_pattern": str, "time_pattern": str, "amount_pattern": str,
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
    )
