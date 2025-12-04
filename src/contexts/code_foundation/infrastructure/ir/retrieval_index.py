"""
Retrieval-Optimized Index

Fast indexes for retrieval queries optimized for SOTA IR.

Key features:
1. Symbol name index (exact + fuzzy)
2. FQN index (O(1) lookup)
3. Type-based index
4. Importance-ranked results
5. File-level indexes

Performance targets:
- Symbol lookup (exact): <1ms
- Symbol lookup (fuzzy): <10ms
- Find-references: <5ms (via OccurrenceIndex)
- Type-based queries: <10ms

Example usage:
    index = RetrievalOptimizedIndex()

    # Index IR documents
    for ir_doc in ir_docs.values():
        index.index_ir_document(ir_doc)

    # Query
    results = index.search_symbol("Calculator", fuzzy=True, limit=10)
    for node, score in results:
        print(f"{node.name}: {score:.2f}")
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.common.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.core import Node
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
    from src.contexts.code_foundation.infrastructure.ir.models.occurrence import OccurrenceIndex

logger = get_logger(__name__)


@dataclass
class FileIndex:
    """Per-file index"""

    file_path: str
    nodes: list["Node"] = field(default_factory=list)
    node_ids: set[str] = field(default_factory=set)

    @classmethod
    def from_ir_doc(cls, ir_doc: "IRDocument") -> "FileIndex":
        """Create file index from IR document"""
        return cls(
            file_path=ir_doc.nodes[0].file_path if ir_doc.nodes else "",
            nodes=ir_doc.nodes,
            node_ids={n.id for n in ir_doc.nodes},
        )


class FuzzyMatcher:
    """
    Simple fuzzy string matcher.

    Uses edit distance for fuzzy matching.
    """

    def __init__(self):
        self._items: dict[str, list[str]] = {}  # name → [ids]

    def add(self, name: str, item_id: str):
        """Add item to fuzzy index"""
        if not name:
            return

        # Normalize
        name_lower = name.lower()
        self._items.setdefault(name_lower, []).append(item_id)

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        """
        Fuzzy search.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of (item_id, score) tuples, sorted by score
        """
        if not query:
            return []

        query_lower = query.lower()
        results = []

        for name, item_ids in self._items.items():
            # Calculate similarity
            score = self._similarity(query_lower, name)

            if score > 0.3:  # Threshold
                for item_id in item_ids:
                    results.append((item_id, score))

        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:limit]

    def _similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity score (0.0-1.0).

        Uses simple substring + length-based heuristic.
        For production, consider Levenshtein distance.
        """
        # Exact match
        if s1 == s2:
            return 1.0

        # Substring match
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return shorter / longer

        # Common prefix
        common_prefix = 0
        for c1, c2 in zip(s1, s2):
            if c1 == c2:
                common_prefix += 1
            else:
                break

        if common_prefix > 0:
            return common_prefix / max(len(s1), len(s2))

        return 0.0


class RetrievalOptimizedIndex:
    """
    Retrieval-optimized index for SOTA IR.

    Indexes:
    - by_symbol_name: name → [Node]
    - by_fqn: FQN → Node (O(1))
    - by_type: type_name → [Node]
    - by_file: file_path → FileIndex
    - fuzzy_matcher: Fuzzy name search

    Also includes OccurrenceIndex for find-references.
    """

    def __init__(self):
        self.logger = logger

        # Symbol indexes
        self.by_symbol_name: dict[str, list["Node"]] = {}
        self.by_fqn: dict[str, "Node"] = {}
        self.by_type: dict[str, list["Node"]] = {}

        # File indexes
        self.by_file: dict[str, FileIndex] = {}

        # Fuzzy search
        self.fuzzy_matcher = FuzzyMatcher()

        # Occurrence index (from IR document)
        self.occurrence_index: "OccurrenceIndex | None" = None

        # Stats
        self.total_nodes = 0
        self.total_files = 0

    def index_ir_document(self, ir_doc: "IRDocument"):
        """
        Index entire IR document.

        Args:
            ir_doc: IR document to index
        """
        # Index nodes
        for node in ir_doc.nodes:
            self.total_nodes += 1

            # By name
            if node.name:
                self.by_symbol_name.setdefault(node.name, []).append(node)
                self.fuzzy_matcher.add(node.name, node.id)

            # By FQN
            if node.fqn:
                self.by_fqn[node.fqn] = node

            # By type
            if type_name := node.attrs.get("lsp_type"):
                self.by_type.setdefault(type_name, []).append(node)

        # Index file
        if ir_doc.nodes:
            file_path = ir_doc.nodes[0].file_path
            self.by_file[file_path] = FileIndex.from_ir_doc(ir_doc)
            self.total_files += 1

        # Store occurrence index
        if ir_doc._occurrence_index:
            self.occurrence_index = ir_doc._occurrence_index

    def search_symbol(
        self,
        query: str,
        fuzzy: bool = True,
        limit: int = 20,
    ) -> list[tuple["Node", float]]:
        """
        Search symbols with ranking.

        Args:
            query: Search query
            fuzzy: Use fuzzy matching
            limit: Max results

        Returns:
            List of (Node, relevance_score), sorted by relevance
        """
        if fuzzy:
            # Fuzzy matching
            matches = self.fuzzy_matcher.search(query, limit=limit * 2)
            node_ids = [m[0] for m in matches]
            nodes = [self.by_fqn.get(nid) for nid in node_ids]
            nodes = [n for n in nodes if n is not None]
        else:
            # Exact matching
            nodes = self.by_symbol_name.get(query, [])

        # Calculate relevance scores
        scored = []
        for node in nodes:
            score = self._calculate_relevance(node, query)
            scored.append((node, score))

        # Sort by relevance
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:limit]

    def _calculate_relevance(self, node: "Node", query: str) -> float:
        """
        Calculate relevance score for ranking.

        Factors:
        - Name match quality
        - Importance score (from occurrence)
        - Documentation presence
        - Public API status
        - Type (class > function > variable)

        Args:
            node: Node to score
            query: Search query

        Returns:
            Relevance score (0.0-1.0)
        """
        score = 0.0

        # Name match (fuzzy similarity)
        if node.name:
            name_match = self._fuzzy_similarity(node.name.lower(), query.lower())
            score += name_match * 0.4

        # Importance (from occurrence layer)
        importance = node.attrs.get("importance_score", 0.5)
        score += importance * 0.3

        # Documentation
        if node.docstring:
            score += 0.2

        # Public API
        if node.name and not node.name.startswith("_"):
            score += 0.1

        return min(score, 1.0)

    def _fuzzy_similarity(self, s1: str, s2: str) -> float:
        """Calculate fuzzy similarity (same as FuzzyMatcher)"""
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            return min(len(s1), len(s2)) / max(len(s1), len(s2))
        return 0.3  # Base score

    def get_by_fqn(self, fqn: str) -> "Node | None":
        """Get node by FQN (O(1))"""
        return self.by_fqn.get(fqn)

    def get_by_type(self, type_name: str) -> list["Node"]:
        """Get nodes by type"""
        return self.by_type.get(type_name, [])

    def get_file_nodes(self, file_path: str) -> list["Node"]:
        """Get all nodes in file"""
        file_index = self.by_file.get(file_path)
        return file_index.nodes if file_index else []

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics"""
        return {
            "total_nodes": self.total_nodes,
            "total_files": self.total_files,
            "unique_names": len(self.by_symbol_name),
            "unique_fqns": len(self.by_fqn),
            "types": len(self.by_type),
        }
