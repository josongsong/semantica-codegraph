"""
IR Document - Top-level container (v2.0)

IRDocument aggregates all IR layers:
- Structural IR (nodes, edges)
- Semantic IR (types, signatures, cfgs)
- Occurrence IR (SCIP-compatible) ⭐ NEW in v2.0

v2.0 adds SCIP-level occurrence tracking for retrieval optimization.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.contexts.code_foundation.infrastructure.ir.models.core import Edge, Node

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.diagnostic import Diagnostic, DiagnosticIndex
    from src.contexts.code_foundation.infrastructure.ir.models.occurrence import Occurrence, OccurrenceIndex, SymbolRole
    from src.contexts.code_foundation.infrastructure.ir.models.package import PackageMetadata, PackageIndex
    from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.models import ControlFlowGraph
    from src.contexts.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
    from src.contexts.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity


@dataclass
class IRDocument:
    """
    Complete IR snapshot for a repository (v2.0).

    v2.0 Changes:
    - Added occurrences field (SCIP-compatible)
    - Added retrieval-optimized query methods
    - Added lazy index building
    - Schema version: 2.0

    This is the top-level container that gets serialized to JSON/DB.

    Example usage:
        # Build IR
        ir_doc = IRDocument(
            repo_id="myproject",
            snapshot_id="2024-12-04",
            schema_version="2.0",
        )

        # Add nodes, edges
        ir_doc.nodes.append(node)
        ir_doc.edges.append(edge)

        # Generate occurrences
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(ir_doc)
        ir_doc.occurrences = occurrences
        ir_doc._occurrence_index = index

        # Query
        refs = ir_doc.find_references("class:Calculator")
        defs = ir_doc.get_definitions_in_file("src/calc.py")
    """

    # [Required] Identity
    repo_id: str
    snapshot_id: str  # Timestamp or version tag
    schema_version: str = "2.0"  # ⭐ IR schema version (v2.0 adds occurrences)

    # [Required] Structural IR
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    # [Optional] Semantic IR
    types: list["TypeEntity"] = field(default_factory=list)
    signatures: list["SignatureEntity"] = field(default_factory=list)
    cfgs: list["ControlFlowGraph"] = field(default_factory=list)

    # ⭐ NEW in v2.0: Occurrence IR (SCIP-compatible)
    occurrences: list["Occurrence"] = field(default_factory=list)

    # ⭐ NEW in v2.0: Diagnostics (SCIP-compatible)
    diagnostics: list["Diagnostic"] = field(default_factory=list)

    # ⭐ NEW in v2.0: Package Metadata (SCIP-compatible)
    packages: list["PackageMetadata"] = field(default_factory=list)

    # [Optional] Metadata
    meta: dict[str, Any] = field(default_factory=dict)

    # ============================================================
    # Private indexes (lazy-built, not serialized)
    # ============================================================
    _occurrence_index: "OccurrenceIndex | None" = field(default=None, repr=False, compare=False)
    _diagnostic_index: "DiagnosticIndex | None" = field(default=None, repr=False, compare=False)
    _package_index: "PackageIndex | None" = field(default=None, repr=False, compare=False)
    _node_index: dict[str, Node] | None = field(default=None, repr=False, compare=False)
    _edge_index: dict[str, list[Edge]] | None = field(default=None, repr=False, compare=False)
    _file_nodes_index: dict[str, list[Node]] | None = field(default=None, repr=False, compare=False)

    # ============================================================
    # Index Building
    # ============================================================

    def build_indexes(self) -> None:
        """
        Build all indexes for fast lookup.

        Call this after loading IR from disk or after generating occurrences.
        Indexes are built lazily (only when needed).
        """
        # Node index (id → Node)
        self._node_index = {n.id: n for n in self.nodes}

        # Edge index (source_id → [Edge])
        self._edge_index = {}
        for edge in self.edges:
            self._edge_index.setdefault(edge.source_id, []).append(edge)

        # File nodes index (file_path → [Node])
        self._file_nodes_index = {}
        for node in self.nodes:
            self._file_nodes_index.setdefault(node.file_path, []).append(node)

        # Occurrence index
        if self.occurrences and not self._occurrence_index:
            from src.contexts.code_foundation.infrastructure.ir.models.occurrence import OccurrenceIndex

            self._occurrence_index = OccurrenceIndex()
            for occ in self.occurrences:
                self._occurrence_index.add(occ)

    def ensure_indexes(self) -> None:
        """Ensure indexes are built (lazy initialization)"""
        if self._node_index is None:
            self.build_indexes()

    # ============================================================
    # Basic Queries (Structural IR)
    # ============================================================

    def get_node(self, node_id: str) -> Node | None:
        """Get node by ID (O(1))"""
        self.ensure_indexes()
        return self._node_index.get(node_id) if self._node_index else None

    def get_edges_from(self, source_id: str) -> list[Edge]:
        """Get all edges from a source node (O(1))"""
        self.ensure_indexes()
        return self._edge_index.get(source_id, []) if self._edge_index else []

    def get_file_nodes(self, file_path: str) -> list[Node]:
        """Get all nodes in a file (O(1))"""
        self.ensure_indexes()
        return self._file_nodes_index.get(file_path, []) if self._file_nodes_index else []

    def find_nodes_by_name(self, name: str) -> list[Node]:
        """Find nodes by name (case-sensitive)"""
        return [n for n in self.nodes if n.name == name]

    def find_nodes_by_kind(self, kind: str) -> list[Node]:
        """Find nodes by kind (e.g., NodeKind.CLASS)"""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        # Handle both string and NodeKind enum
        if isinstance(kind, str):
            try:
                kind_enum = NodeKind(kind)
            except ValueError:
                return []
        else:
            kind_enum = kind

        return [n for n in self.nodes if n.kind == kind_enum]

    # ============================================================
    # Occurrence Queries (SCIP-level, v2.0) ⭐
    # ============================================================

    def find_references(self, symbol_id: str) -> list["Occurrence"]:
        """
        Find all occurrences of a symbol (O(1)).

        Returns:
            List of occurrences (definitions + references)
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_references(symbol_id)

    def find_definitions(self, symbol_id: str) -> list["Occurrence"]:
        """
        Find definition occurrences for a symbol (O(1)).

        Returns:
            List of definition occurrences (usually 1, can be multiple for overloads)
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_definitions(symbol_id)

    def find_usages(self, symbol_id: str, include_definitions: bool = False) -> list["Occurrence"]:
        """
        Find usage occurrences (references, not definitions).

        Args:
            symbol_id: Symbol to find usages for
            include_definitions: Include definition occurrences (default: False)

        Returns:
            List of usage occurrences
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_usages(symbol_id, include_definitions)

    def get_file_occurrences(self, file_path: str) -> list["Occurrence"]:
        """
        Get all occurrences in a file (O(1)).

        Args:
            file_path: File to get occurrences for

        Returns:
            List of occurrences in file
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_file_occurrences(file_path)

    def get_definitions_in_file(self, file_path: str) -> list["Occurrence"]:
        """
        Get all definitions in a file (for outline/symbol list).

        Args:
            file_path: File to get definitions for

        Returns:
            List of definition occurrences in file
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_definitions_in_file(file_path)

    def get_by_role(self, role: "SymbolRole") -> list["Occurrence"]:
        """
        Get occurrences by role (e.g., SymbolRole.WRITE_ACCESS).

        Args:
            role: Role to filter by

        Returns:
            List of occurrences with that role
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_by_role(role)

    def get_high_importance_symbols(self, min_score: float = 0.7) -> list["Occurrence"]:
        """
        Get high-importance occurrences (for ranking).

        Args:
            min_score: Minimum importance score (0.0-1.0)

        Returns:
            List of high-importance occurrences, sorted by score
        """
        self.ensure_indexes()
        if not self._occurrence_index:
            return []
        return self._occurrence_index.get_by_importance(min_score)

    # ============================================================
    # Statistics
    # ============================================================

    def get_stats(self) -> dict[str, Any]:
        """
        Get IR statistics.

        Returns:
            Statistics dict with counts and breakdowns
        """
        stats = {
            "schema_version": self.schema_version,
            "repo_id": self.repo_id,
            "snapshot_id": self.snapshot_id,
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "types": len(self.types),
            "signatures": len(self.signatures),
            "cfgs": len(self.cfgs),
            "occurrences": len(self.occurrences),
        }

        # Occurrence stats
        self.ensure_indexes()
        if self._occurrence_index:
            stats["occurrence_stats"] = self._occurrence_index.get_stats()

        return stats
