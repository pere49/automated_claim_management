"""UI boundary for the framework-independent backend service."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_ROOT) in sys.path:
    sys.path.remove(str(_BACKEND_ROOT))
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.claim_processor import ClaimOcrResult, ClaimProcessor

__all__ = ["ClaimOcrResult", "ClaimProcessor"]
