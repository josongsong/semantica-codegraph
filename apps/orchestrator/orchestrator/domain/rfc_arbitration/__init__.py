"""
RFC Arbitration Domain (RFC-027 Section 7)

Result Arbitration Engine - Priority-based claim resolution.

Architecture:
- Domain Layer (Pure logic)
- Depends on: rfc_specs (Claim, ConfidenceBasis)
- No infrastructure dependencies

RFC-027 Section 7.1: Priority Rules
RFC-027 Section 7.2: Conflict Resolution
"""

from .arbitration_engine import ArbitrationEngine, ArbitrationPriority, ArbitrationResult

__all__ = [
    "ArbitrationEngine",
    "ArbitrationPriority",
    "ArbitrationResult",
]
