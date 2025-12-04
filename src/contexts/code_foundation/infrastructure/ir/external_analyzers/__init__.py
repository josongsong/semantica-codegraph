"""
External Code Analyzers

Interfaces and adapters for external type checkers and LSP servers.

Supported analyzers:
- Pyright: Python type checker
- Mypy: Python type checker (future)
- LSP: Language Server Protocol integration (future)

RFC-023: Pyright Semantic Daemon (M0+M1+M2)
"""

from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import (
    ExternalAnalyzer,
    Location,
    NarrowingContext,
    NarrowingKind,
    TypeInfo,
)
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.change_detector import ChangeDetector
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_adapter import PyrightExternalAnalyzer
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_daemon import PyrightSemanticDaemon
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.snapshot import (
    PyrightSemanticSnapshot,
    SnapshotDelta,
    Span,
)
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.snapshot_store import SemanticSnapshotStore

__all__ = [
    "ExternalAnalyzer",
    "TypeInfo",
    "Location",
    # Union narrowing support
    "NarrowingKind",
    "NarrowingContext",
    # RFC-023: Semantic Daemon (M0+)
    "PyrightSemanticDaemon",
    "PyrightSemanticSnapshot",
    "Span",
    # RFC-023: Snapshot Storage (M1+)
    "SemanticSnapshotStore",
    # RFC-023: Incremental Updates (M2+)
    "SnapshotDelta",
    "ChangeDetector",
    # RFC-023: Integration Adapter (M2.3+)
    "PyrightExternalAnalyzer",
]
