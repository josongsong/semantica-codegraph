"""
External Code Analyzers

Interfaces and adapters for external type checkers and LSP servers.

Supported analyzers:
- Pyright: Python type checker
- Mypy: Python type checker (future)
- LSP: Language Server Protocol integration
  - TypeScript (tsserver)
  - Rust (rust-analyzer)
  - Go (gopls)

RFC-023: Pyright Semantic Daemon (M0+M1+M2)
"""

from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import (
    ExternalAnalyzer,
    Location,
    NarrowingContext,
    NarrowingKind,
    TypeInfo,
)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.change_detector import ChangeDetector
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.diagnostics import (
    Diagnostic,
    DiagnosticRange,
    DiagnosticRelatedInfo,
    DiagnosticsAggregator,
    DiagnosticSeverity,
    DiagnosticsStore,
    DiagnosticsSubscriber,
)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.pyright_adapter import (
    PyrightExternalAnalyzer,
)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.pyright_cache import (
    PyrightResultCache,
    clear_shared_cache,
    get_shared_cache,
)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.pyright_daemon import PyrightSemanticDaemon
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot import (
    PyrightSemanticSnapshot,
    SnapshotDelta,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot_store import SemanticSnapshotStore

# SOTA: Batch LSP Fetcher (parallel hover/definition calls)
from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.batch_lsp_fetcher import (
    BatchLSPFetcher,
    BatchLSPStats,
)

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
    # RFC-029: Pyright Result Caching
    "PyrightResultCache",
    "get_shared_cache",
    "clear_shared_cache",
    # LSP Diagnostics (SOTA-grade)
    "Diagnostic",
    "DiagnosticRange",
    "DiagnosticRelatedInfo",
    "DiagnosticSeverity",
    "DiagnosticsStore",
    "DiagnosticsSubscriber",
    "DiagnosticsAggregator",
    # SOTA: Batch LSP Fetcher (20-30x speedup)
    "BatchLSPFetcher",
    "BatchLSPStats",
]
