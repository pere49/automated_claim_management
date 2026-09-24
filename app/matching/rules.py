"""MatchingRules: the search rules, read from matching_rules.json and checked."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config_files import read_json_config
from app.errors import StageError

DEFAULT_MATCHING_RULES = Path(__file__).resolve().with_name("matching_rules.json")


@dataclass(frozen=True)
class MatchingRules:
    currency_words: tuple[str, ...]
    no_cents_endings: tuple[str, ...]
    tax_code_letters: frozenset[str]
    amount_prefix_marks: frozenset[str]
    total_labels: frozenset[str]
    thousands_separators: tuple[str, ...]
    one_decimal_forms: bool
    tail_join_gap_per_height: float
    month_names: dict[int, tuple[str, ...]]
    date_separators: tuple[str, ...]
    pin_formats: frozenset[str]
    letter_to_digit: dict[str, str]
    digit_to_letter: dict[str, str]
    lookalike_pairs: frozenset[frozenset[str]]
    pin_labels: frozenset[str]
    neighbours_each_side: int
    currency_lower: frozenset[str] = frozenset()          # derived: currency words (lower case) and endings
    currency_longest_first: tuple[str, ...] = ()          # derived: lower case, longest first, for trimming


def load_matching_rules(path: Path = DEFAULT_MATCHING_RULES) -> MatchingRules:
    """Read and check matching_rules.json. Raises StageError(stage="config")."""
    d = read_json_config(path, {
        "currency_words": list, "no_cents_endings": list, "tax_code_letters": list, "amount_prefix_marks": list,
        "total_labels": list, "thousands_separators": list, "one_decimal_forms": bool,
        "tail_join_gap_per_height": (int, float), "month_names": dict, "date_separators": list,
        "pin_formats": list, "letter_to_digit": dict, "digit_to_letter": dict, "lookalike_pairs": list,
        "pin_labels": list, "neighbours_each_side": int,
    })

    def fail(message: str) -> StageError:
        return StageError("config", message, file=path.name)

    def texts(key: str, allow_empty_items: bool = False) -> tuple[str, ...]:
        items = d[key]
        if not items or not all(isinstance(i, str) and (i or allow_empty_items) for i in items):
            raise fail(f"'{key}' must be a non-empty list of text")
        return tuple(items)

    def single_chars(key: str) -> frozenset[str]:
        items = texts(key)
        if not all(len(i) == 1 for i in items):
            raise fail(f"'{key}' must list single characters")
        return frozenset(items)

    months: dict[int, tuple[str, ...]] = {}
    for k, names in d["month_names"].items():
        if not (k.isdigit() and 1 <= int(k) <= 12) or not names or not all(isinstance(n, str) and n for n in names):
            raise fail("'month_names' must map month numbers 1..12 to lists of names")
        months[int(k)] = tuple(names)
    if set(months) != set(range(1, 13)):
        raise fail("'month_names' must cover all twelve months")

    formats = texts("pin_formats")
    if not all(set(f) <= {"L", "D"} for f in formats):
        raise fail("'pin_formats' may use only L (letter) and D (digit)")
    for key in ("letter_to_digit", "digit_to_letter"):
        if not all(isinstance(a, str) and isinstance(b, str) and len(a) == 1 and len(b) == 1 for a, b in d[key].items()):
            raise fail(f"'{key}' must map single characters to single characters")
    pairs = d["lookalike_pairs"]
    if not all(isinstance(p, list) and len(p) == 2 and all(isinstance(c, str) and len(c) == 1 for c in p) for p in pairs):
        raise fail("'lookalike_pairs' must be a list of two-character pairs")
    if d["tail_join_gap_per_height"] <= 0:
        raise fail("'tail_join_gap_per_height' must be greater than zero")
    if d["neighbours_each_side"] < 0:
        raise fail("'neighbours_each_side' must not be negative")

    return MatchingRules(
        currency_words=texts("currency_words"),
        no_cents_endings=texts("no_cents_endings"),
        tax_code_letters=single_chars("tax_code_letters"),
        amount_prefix_marks=single_chars("amount_prefix_marks"),
        total_labels=frozenset(t.lower() for t in texts("total_labels")),
        thousands_separators=texts("thousands_separators", allow_empty_items=True),
        one_decimal_forms=d["one_decimal_forms"],
        tail_join_gap_per_height=float(d["tail_join_gap_per_height"]),
        month_names=months,
        date_separators=texts("date_separators"),
        pin_formats=frozenset(formats),
        letter_to_digit=dict(d["letter_to_digit"]),
        digit_to_letter=dict(d["digit_to_letter"]),
        lookalike_pairs=frozenset(frozenset(p) for p in pairs),
        pin_labels=frozenset(t.lower() for t in texts("pin_labels")),
        neighbours_each_side=d["neighbours_each_side"],
        currency_lower=frozenset(c.lower() for c in d["currency_words"]) | frozenset(d["no_cents_endings"]),
        currency_longest_first=tuple(sorted((c.lower() for c in d["currency_words"]), key=len, reverse=True)),
    )
