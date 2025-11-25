"""
Scope Selection Module

Determines search scope based on RepoMap and intent.
"""

from .models import ScopeResult
from .selector import ScopeSelector
from .validator import RepoMapStatus, RepoMapValidator, SnapshotValidator

__all__ = [
    # Models
    "ScopeResult",
    # Selector
    "ScopeSelector",
    # Validator
    "RepoMapValidator",
    "SnapshotValidator",
    "RepoMapStatus",
]
