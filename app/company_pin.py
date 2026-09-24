"""The company's PIN, from the git-ignored secrets file (decisions D23).

The file (".env" at the project root, named in gui_settings.json) holds
KEY=value lines; the key's value may list several PINs separated by commas —
the first is searched. The PIN is never shown, logged or put into an error.
"""

from __future__ import annotations

from pathlib import Path

from app.errors import StageError


def load_company_pin(path: Path, key: str) -> str | None:
    """The first PIN listed under `key`; None when the file or the key is
    absent (the PIN checks then stay off). Raises StageError(stage="config")
    when the file exists but cannot be read."""
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        raise StageError("config", "the company PIN file could not be read", file=path.name, cause=exc) from exc
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == key:
            first = next((v.strip() for v in value.split(",") if v.strip()), "")
            return "".join(first.split()).upper() or None
    return None
