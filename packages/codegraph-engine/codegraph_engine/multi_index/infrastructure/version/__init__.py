"""Index Version Management.

Provides version tracking for indexed repositories to ensure consistency
between agent requests and underlying code index.
"""

from .checker import IndexVersionChecker, StalenessPolicy
from .middleware import VersionCheckMiddleware, VersionCheckResult
from .models import IndexVersion, IndexVersionStatus
from .store import IndexVersionStore

__all__ = [
    "IndexVersion",
    "IndexVersionStatus",
    "IndexVersionStore",
    "IndexVersionChecker",
    "StalenessPolicy",
    "VersionCheckMiddleware",
    "VersionCheckResult",
]
