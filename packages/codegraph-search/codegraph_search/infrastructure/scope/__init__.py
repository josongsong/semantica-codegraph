"""
Scope Selection Module

Determines search scope based on RepoMap and intent.
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.scope.models import ScopeResult
from codegraph_search.infrastructure.scope.validator import RepoMapStatus

if TYPE_CHECKING:
    from codegraph_search.infrastructure.scope.selector import ScopeSelector
    from codegraph_search.infrastructure.scope.validator import RepoMapValidator, SnapshotValidator


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "ScopeSelector":
        from codegraph_search.infrastructure.scope.selector import ScopeSelector

        return ScopeSelector
    if name == "RepoMapValidator":
        from codegraph_search.infrastructure.scope.validator import RepoMapValidator

        return RepoMapValidator
    if name == "SnapshotValidator":
        from codegraph_search.infrastructure.scope.validator import SnapshotValidator

        return SnapshotValidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "ScopeResult",
    # Selector (heavy - lazy import via TYPE_CHECKING)
    "ScopeSelector",
    # Validator (heavy - lazy import via TYPE_CHECKING)
    "RepoMapValidator",
    "SnapshotValidator",
    "RepoMapStatus",
]
