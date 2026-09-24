"""Reading a JSON config file into a plain dict, with structured errors.

Every config file in the application lives next to the code that reads it
and is loaded through read_json_config(), so a missing file, broken JSON or
a missing/wrongly-typed key always becomes the same kind of StageError
("config" stage) instead of a bare traceback. Keys starting with "_" are
comments and are ignored. Each caller states the keys it needs and their
types; checking what a value *means* stays with the caller.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.errors import StageError

# type names used in error messages, so they read plainly
_TYPE_NAMES = {int: "a whole number", float: "a number", str: "text", list: "a list",
               dict: "a section", bool: "true or false"}


def read_json_config(path: Path, required: dict[str, type | tuple[type, ...]]) -> dict[str, Any]:
    """Load `path` and check that every key in `required` is present with the
    stated type. Raises StageError(stage="config") on any problem."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StageError("config", "config file not found", file=path.name, cause=exc) from exc
    except json.JSONDecodeError as exc:
        raise StageError("config", "config file is not valid JSON", file=path.name, cause=exc) from exc
    except Exception as exc:
        raise StageError("config", "config file could not be read", file=path.name, cause=exc) from exc

    if not isinstance(data, dict):
        raise StageError("config", "config file must hold one JSON object at the top level", file=path.name)

    problems = []
    for key, expected in required.items():
        if key not in data:
            problems.append(f"'{key}' is missing")
        elif not _is_type(data[key], expected):
            problems.append(f"'{key}' must be {_describe(expected)}")
    if problems:
        raise StageError("config", "; ".join(problems), file=path.name)
    return data


def _is_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    kinds = expected if isinstance(expected, tuple) else (expected,)
    if isinstance(value, bool) and bool not in kinds:
        return False  # JSON true/false must not pass as a number
    return isinstance(value, kinds)


def _describe(expected: type | tuple[type, ...]) -> str:
    kinds = expected if isinstance(expected, tuple) else (expected,)
    return " or ".join(_TYPE_NAMES.get(k, k.__name__) for k in kinds)
