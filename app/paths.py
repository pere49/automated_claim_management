"""Where the project lives on disk, worked out from this file's own location.

Nothing else here: every folder name the application uses (the working
folder, and so on) is read from config and resolved against PROJECT_ROOT.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve(folder: str) -> Path:
    """A config-supplied folder: absolute paths are kept as they are,
    relative ones are taken from the project root."""
    path = Path(folder)
    return path if path.is_absolute() else PROJECT_ROOT / path
