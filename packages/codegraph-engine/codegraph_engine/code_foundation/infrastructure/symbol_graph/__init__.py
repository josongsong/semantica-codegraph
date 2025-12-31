"""
Symbol Graph Layer

Lightweight semantic graph for code symbols and relationships.
Optimized for Chunk/RepoMap construction (200 bytes/symbol).

SymbolGraph:
  - Symbol: Code entities (Class, Function, Variable, etc.)
  - Relation: Semantic relationships (CALLS, IMPORTS, CONTAINS)
  - RelationIndex: Fast graph traversal indexes

Storage (Port-Adapter Pattern):
  - In-Memory: Primary graph storage (<10ms)
  - SymbolGraphPort: Persistence interface
  - PostgreSQLAdapter: PostgreSQL implementation (100ms+)
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.symbol_graph.models import (
    Relation,
    RelationIndex,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)
from codegraph_engine.code_foundation.infrastructure.symbol_graph.port import SymbolGraphPort

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.symbol_graph.builder import SymbolGraphBuilder
    from codegraph_engine.code_foundation.infrastructure.symbol_graph.postgres_adapter import (
        PostgreSQLSymbolGraphAdapter,
    )


def __getattr__(name: str):
    """Lazy import for heavy components."""
    if name == "SymbolGraphBuilder":
        from codegraph_engine.code_foundation.infrastructure.symbol_graph.builder import SymbolGraphBuilder

        return SymbolGraphBuilder
    if name == "PostgreSQLSymbolGraphAdapter":
        from codegraph_engine.code_foundation.infrastructure.symbol_graph.postgres_adapter import (
            PostgreSQLSymbolGraphAdapter,
        )

        return PostgreSQLSymbolGraphAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "Symbol",
    "SymbolKind",
    "Relation",
    "RelationKind",
    "SymbolGraph",
    "RelationIndex",
    # Builder (heavy - lazy import via TYPE_CHECKING)
    "SymbolGraphBuilder",
    # Port (lightweight)
    "SymbolGraphPort",
    # Adapter (PostgreSQL heavy - lazy import via TYPE_CHECKING)
    "PostgreSQLSymbolGraphAdapter",
]
