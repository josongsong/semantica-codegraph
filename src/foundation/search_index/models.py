"""
Search Index Models

Heavy, search-optimized representations for code symbols and relationships.
Target: ~500-800 bytes per symbol (includes ranking signals and search metadata).
"""

from dataclasses import dataclass, field

from ..symbol_graph.models import RelationKind, SymbolKind

# ============================================================
# SearchableSymbol (Heavy Node)
# ============================================================


@dataclass
class SearchableSymbol:
    """
    Search-optimized code symbol (~500-800 bytes).

    Attributes:
        id: Unique identifier (FQN-based)
        kind: Symbol type
        fqn: Fully qualified name
        name: Simple name
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier

        # Ranking signals
        call_count: Number of times called
        import_count: Number of times imported
        reference_count: Number of references
        is_public: Is symbol public?
        is_exported: Is symbol exported?
        complexity: Cyclomatic complexity
        loc: Lines of code

        # Search metadata
        docstring: Documentation string
        signature: Function signature string
        full_text: Full source code text (for fuzzy search)

        # Parent relationship
        parent_id: Parent symbol ID
    """

    # Core identity (same as Symbol)
    id: str
    kind: SymbolKind
    fqn: str
    name: str
    repo_id: str
    snapshot_id: str

    # Ranking signals (for relevance scoring)
    call_count: int = 0
    import_count: int = 0
    reference_count: int = 0
    is_public: bool = True
    is_exported: bool = False
    complexity: int = 1
    loc: int = 0

    # Search metadata (for fuzzy/semantic search)
    docstring: str | None = None
    signature: str | None = None
    full_text: str | None = None

    # Parent relationship
    parent_id: str | None = None

    def relevance_score(self) -> float:
        """
        Calculate relevance score for ranking.

        Higher score = more important/relevant symbol.
        """
        score = 0.0

        # Call/import/reference frequency (log scale)
        import math

        score += math.log1p(self.call_count) * 2.0
        score += math.log1p(self.import_count) * 1.5
        score += math.log1p(self.reference_count) * 1.0

        # Visibility boost
        if self.is_public:
            score += 5.0
        if self.is_exported:
            score += 3.0

        # Documentation boost
        if self.docstring:
            score += 2.0

        # Penalize complexity
        if self.complexity > 10:
            score -= math.log1p(self.complexity - 10) * 0.5

        return score


# ============================================================
# SearchableRelation (Heavy Edge)
# ============================================================


@dataclass
class SearchableRelation:
    """
    Search-optimized relationship between symbols.

    Attributes:
        id: Unique edge identifier
        kind: Relationship type
        source_id: Source symbol ID
        target_id: Target symbol ID
        frequency: How often this edge is traversed (for weighting)
    """

    id: str
    kind: RelationKind
    source_id: str
    target_id: str
    frequency: int = 1


# ============================================================
# QueryIndexes (Pre-built Search Indexes)
# ============================================================


@dataclass
class QueryIndexes:
    """
    Pre-built indexes for efficient search operations.

    These indexes are built at indexing time and stored in
    Zoekt (lexical), Qdrant (vector), PostgreSQL (fuzzy/domain).

    Attributes:
        fuzzy_index: Symbol names for fuzzy matching (trigram)
        prefix_index: Symbol names for prefix search
        signature_index: Function signatures for signature search
        domain_index: Domain-specific terms (e.g., class names)
    """

    # Lexical indexes (Zoekt)
    fuzzy_index: dict[str, list[str]] = field(default_factory=dict)
    prefix_index: dict[str, list[str]] = field(default_factory=dict)

    # Semantic indexes (Qdrant)
    # Note: Actual embeddings stored in Qdrant, not here
    embedded_symbol_ids: list[str] = field(default_factory=list)

    # Domain indexes (PostgreSQL)
    signature_index: dict[str, list[str]] = field(default_factory=dict)
    domain_index: dict[str, list[str]] = field(default_factory=dict)


# ============================================================
# SearchIndex (Complete Search Graph)
# ============================================================


@dataclass
class SearchIndex:
    """
    Complete search-optimized graph for code symbols.

    This is the heavy layer used for search operations.
    Built from SymbolGraph and enriched with ranking signals.

    Attributes:
        repo_id: Repository identifier
        snapshot_id: Snapshot identifier
        symbols: All searchable symbols indexed by ID
        relations: All searchable relationships
        indexes: Pre-built query indexes
    """

    repo_id: str
    snapshot_id: str
    symbols: dict[str, SearchableSymbol] = field(default_factory=dict)
    relations: list[SearchableRelation] = field(default_factory=list)
    indexes: QueryIndexes = field(default_factory=QueryIndexes)

    def get_symbol(self, symbol_id: str) -> SearchableSymbol | None:
        """Get symbol by ID"""
        return self.symbols.get(symbol_id)

    def get_symbols_by_kind(self, kind: SymbolKind) -> list[SearchableSymbol]:
        """Get all symbols of a specific kind"""
        return [s for s in self.symbols.values() if s.kind == kind]

    def search_by_name(self, query: str, limit: int = 10) -> list[SearchableSymbol]:
        """
        Search symbols by name (exact prefix match).

        For fuzzy search, use adapters (Zoekt/PostgreSQL).
        """
        results = []
        query_lower = query.lower()

        for symbol in self.symbols.values():
            if symbol.name.lower().startswith(query_lower):
                results.append(symbol)

        # Sort by relevance score
        results.sort(key=lambda s: s.relevance_score(), reverse=True)

        return results[:limit]

    def get_top_symbols(self, limit: int = 100) -> list[SearchableSymbol]:
        """Get top symbols by relevance score"""
        symbols = list(self.symbols.values())
        symbols.sort(key=lambda s: s.relevance_score(), reverse=True)
        return symbols[:limit]

    @property
    def symbol_count(self) -> int:
        """Total number of symbols"""
        return len(self.symbols)

    @property
    def relation_count(self) -> int:
        """Total number of relations"""
        return len(self.relations)
