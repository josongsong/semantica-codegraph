"""
Application DTOs

Data Transfer Objects for MCP Service Layer.
"""

from .error import AnalysisError, ErrorCode, RecoveryHint
from .verification_snapshot import VerificationSnapshot

__all__ = [
    "VerificationSnapshot",
    "AnalysisError",
    "ErrorCode",
    "RecoveryHint",
]
