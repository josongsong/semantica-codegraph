"""
RFC Replay Domain (RFC-027 Section 9)

Replay & Audit infrastructure for determinism.

Architecture:
- Domain Layer (Pure models)
- Infrastructure Layer (SQLiteAuditStore)
- No business logic (just data)

RFC-027 Section 9: Replay & Determinism
RFC-027 Section 14: Stored Per Request
"""

from .models import RequestAuditLog

__all__ = [
    "RequestAuditLog",
]
