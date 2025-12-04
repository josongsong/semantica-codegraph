"""Apply Gateway - Safe patch application with conflict resolution.

Provides centralized patch application with:
- Conflict detection and resolution
- Automatic rollback on failure
- Format/lint integration
- All-or-nothing guarantees
"""

from .coordinator import FormatLintCoordinator, QualityCheckResult
from .gateway import ApplyGateway, ApplyResult
from .lsp_client import Diagnostic, LSPClient
from .pre_commit import PreCommitRunner
from .rollback import RollbackManager

__all__ = [
    "ApplyGateway",
    "ApplyResult",
    "RollbackManager",
    "FormatLintCoordinator",
    "QualityCheckResult",
    "LSPClient",
    "Diagnostic",
    "PreCommitRunner",
]
