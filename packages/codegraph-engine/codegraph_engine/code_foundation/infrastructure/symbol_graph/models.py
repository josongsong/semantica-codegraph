"""
Symbol Graph Models

Lightweight graph representation for code symbols.
Target: ~200 bytes per symbol (vs 500 bytes in GraphDocument).
"""

from dataclasses import dataclass, field
from enum import Enum

from codegraph_engine.code_foundation.infrastructure.ir.models import Span

# ============================================================
# Symbol (Lightweight Node)
# ============================================================


class SymbolKind(str, Enum):
    """Code symbol types"""

    # Structural symbols
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    FIELD = "field"

    # Semantic symbols
    TYPE = "type"
    SIGNATURE = "signature"
    CFG_BLOCK = "cfg_block"

    # External symbols
    EXTERNAL_MODULE = "external_module"
    EXTERNAL_FUNCTION = "external_function"
    EXTERNAL_TYPE = "external_type"


@dataclass
class Symbol:
    """
    Lightweight code symbol (target: ~200 bytes).

    Attributes:
        id: Unique identifier (FQN-based)
        kind: Symbol type
        fqn: Fully qualified name
        name: Simple name
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        span: Source location (optional)
        parent_id: Parent symbol ID (optional)
        signature_id: Signature ID (functions only)
        type_id: Type ID (variables only)
    """

    id: str
    kind: SymbolKind
    fqn: str
    name: str
    repo_id: str
    snapshot_id: str | None
    span: Span | None = None

    # Essential relationships (ID references only)
    parent_id: str | None = None
    signature_id: str | None = None
    type_id: str | None = None

    def is_external(self) -> bool:
        """Check if this is an external symbol"""
        return self.kind in (
            SymbolKind.EXTERNAL_MODULE,
            SymbolKind.EXTERNAL_FUNCTION,
            SymbolKind.EXTERNAL_TYPE,
        )

    def is_callable(self) -> bool:
        """Check if this symbol is callable"""
        return self.kind in (
            SymbolKind.FUNCTION,
            SymbolKind.METHOD,
            SymbolKind.EXTERNAL_FUNCTION,
        )


# ============================================================
# Relation (Lightweight Edge)
# ============================================================


class RelationKind(str, Enum):
    """Semantic relationship types"""

    # Structural relations
    CONTAINS = "contains"  # Parent-child containment
    IMPORTS = "imports"  # Import relationship
    INHERITS = "inherits"  # Class inheritance
    IMPLEMENTS = "implements"  # Interface implementation

    # Call/Reference relations
    CALLS = "calls"  # Function call
    REFERENCES_TYPE = "references_type"  # Type usage
    REFERENCES_SYMBOL = "references_symbol"  # Symbol reference

    # Data flow relations
    READS = "reads"  # Variable read
    WRITES = "writes"  # Variable write

    # Control flow relations
    CFG_NEXT = "cfg_next"  # Sequential execution
    CFG_BRANCH = "cfg_branch"  # Conditional branch
    CFG_LOOP = "cfg_loop"  # Loop back edge
    CFG_HANDLER = "cfg_handler"  # Exception handler


@dataclass
class Relation:
    """
    Semantic relationship between symbols.

    Attributes:
        id: Unique edge identifier
        kind: Relationship type
        source_id: Source symbol ID
        target_id: Target symbol ID
        span: Source location (optional)
    """

    id: str
    kind: RelationKind
    source_id: str
    target_id: str
    span: Span | None = None


# ============================================================
# Relation Index (Fast Traversal)
# ============================================================


@dataclass
class RelationIndex:
    """
    Indexes for efficient graph traversal.

    Provides reverse indexes for common queries:
    - Who calls this function?
    - What does this class contain?
    - What imports this module?
    """

    # Core reverse indexes (target → sources)
    called_by: dict[str, list[str]] = field(default_factory=dict)
    imported_by: dict[str, list[str]] = field(default_factory=dict)
    parent_to_children: dict[str, list[str]] = field(default_factory=dict)
    type_users: dict[str, list[str]] = field(default_factory=dict)
    reads_by: dict[str, list[str]] = field(default_factory=dict)
    writes_by: dict[str, list[str]] = field(default_factory=dict)

    # Adjacency indexes (for general graph queries)
    outgoing: dict[str, list[str]] = field(default_factory=dict)
    incoming: dict[str, list[str]] = field(default_factory=dict)

    def get_callers(self, symbol_id: str) -> list[str]:
        """Get all callers of a symbol"""
        return self.called_by.get(symbol_id, [])

    def get_importers(self, symbol_id: str) -> list[str]:
        """Get all importers of a symbol"""
        return self.imported_by.get(symbol_id, [])

    def get_children(self, symbol_id: str) -> list[str]:
        """Get all children of a symbol"""
        return self.parent_to_children.get(symbol_id, [])

    def get_type_users(self, type_id: str) -> list[str]:
        """Get all symbols using this type"""
        return self.type_users.get(type_id, [])

    def get_outgoing_edges(self, symbol_id: str) -> list[str]:
        """Get all outgoing edge IDs from a symbol"""
        return self.outgoing.get(symbol_id, [])

    def get_incoming_edges(self, symbol_id: str) -> list[str]:
        """Get all incoming edge IDs to a symbol"""
        return self.incoming.get(symbol_id, [])


# ============================================================
# Symbol Graph (Complete Graph)
# ============================================================


@dataclass
class SymbolGraph:
    """
    Lightweight semantic graph for code symbols.

    Combines symbols and relationships into a unified graph
    optimized for Chunk/RepoMap construction.

    Attributes:
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        symbols: All symbols indexed by ID
        relations: All relationships
        indexes: Traversal indexes
    """

    repo_id: str
    snapshot_id: str
    symbols: dict[str, Symbol] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    indexes: RelationIndex = field(default_factory=RelationIndex)

    def get_symbol(self, symbol_id: str) -> Symbol | None:
        """Get symbol by ID"""
        return self.symbols.get(symbol_id)

    def get_symbols_by_kind(self, kind: SymbolKind) -> list[Symbol]:
        """Get all symbols of a specific kind"""
        return [s for s in self.symbols.values() if s.kind == kind]

    def get_relations_by_kind(self, kind: RelationKind) -> list[Relation]:
        """Get all relations of a specific kind"""
        return [r for r in self.relations if r.kind == kind]

    def get_relations_from(self, source_id: str) -> list[Relation]:
        """Get all relations originating from a symbol"""
        edge_ids = self.indexes.outgoing.get(source_id, [])
        return [r for r in self.relations if r.id in edge_ids]

    def get_relations_to(self, target_id: str) -> list[Relation]:
        """Get all relations pointing to a symbol"""
        edge_ids = self.indexes.incoming.get(target_id, [])
        return [r for r in self.relations if r.id in edge_ids]

    @property
    def symbol_count(self) -> int:
        """Total number of symbols"""
        return len(self.symbols)

    @property
    def relation_count(self) -> int:
        """Total number of relations"""
        return len(self.relations)

    def stats(self) -> dict[str, int]:
        """Get graph statistics"""
        symbol_counts: dict[str, int] = {}
        for symbol in self.symbols.values():
            kind = symbol.kind.value
            symbol_counts[kind] = symbol_counts.get(kind, 0) + 1

        relation_counts: dict[str, int] = {}
        for relation in self.relations:
            kind = relation.kind.value
            relation_counts[kind] = relation_counts.get(kind, 0) + 1

        return {
            "total_symbols": self.symbol_count,
            "total_relations": self.relation_count,
            "symbols_by_kind": symbol_counts,
            "relations_by_kind": relation_counts,
        }
