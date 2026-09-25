"""Framework-independent services used by application front ends."""

from app.services.claim_processor import ClaimOcrResult, ClaimProcessor

__all__ = ["ClaimOcrResult", "ClaimProcessor"]
