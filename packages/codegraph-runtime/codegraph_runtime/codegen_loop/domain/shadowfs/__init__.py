"""
ShadowFS Domain Models

Pure domain models for ShadowFS (RFC-016).
No infrastructure dependencies.
"""

from .models import ChangeType, FilePatch, Hunk
from .transaction import FileSnapshot, TransactionState

__all__ = [
    "FilePatch",
    "Hunk",
    "ChangeType",
    "TransactionState",
    "FileSnapshot",
]
