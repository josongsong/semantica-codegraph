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

from .builder import SymbolGraphBuilder
from .models import (
    Relation,
    RelationIndex,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)
from .port import SymbolGraphPort
from .postgres_adapter import PostgreSQLSymbolGraphAdapter

__all__ = [
    # Models
    "Symbol",
    "SymbolKind",
    "Relation",
    "RelationKind",
    "SymbolGraph",
    "RelationIndex",
    # Builder
    "SymbolGraphBuilder",
    # Port & Adapters
    "SymbolGraphPort",
    "PostgreSQLSymbolGraphAdapter",
]
