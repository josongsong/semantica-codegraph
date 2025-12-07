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
    from src.contexts.code_foundation.infrastructure.ir.models.package import PackageIndex, PackageMetadata
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
    schema_version: str = "2.1"  # ⭐ IR schema version (v2.1 adds PDG/Slicing/Taint)

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

    # ⭐ NEW: Cross-Language Symbol Resolution (Phase 1)
    unified_symbols: list["UnifiedSymbol"] = field(default_factory=list)
    """Unified cross-language symbols (SCIP-compatible)"""

    # [Optional] Metadata
    meta: dict[str, Any] = field(default_factory=dict)

    # ⭐ NEW in v2.1: Advanced Analysis (PDG, Slicing, Taint)
    pdg_nodes: list["PDGNode"] = field(default_factory=list)
    """Program Dependence Graph nodes (control + data dependencies)"""

    pdg_edges: list["PDGEdge"] = field(default_factory=list)
    """PDG edges (CONTROL_DEP, DATA_DEP)"""

    taint_findings: list["TaintFinding"] = field(default_factory=list)
    """Taint analysis results (security vulnerabilities)"""

    # ============================================================
    # Private indexes (lazy-built, not serialized)
    # ============================================================
    _occurrence_index: "OccurrenceIndex | None" = field(default=None, repr=False, compare=False)
    _diagnostic_index: "DiagnosticIndex | None" = field(default=None, repr=False, compare=False)
    _package_index: "PackageIndex | None" = field(default=None, repr=False, compare=False)
    _node_index: dict[str, Node] | None = field(default=None, repr=False, compare=False)
    _edge_index: dict[str, list[Edge]] | None = field(default=None, repr=False, compare=False)
    _file_nodes_index: dict[str, list[Node]] | None = field(default=None, repr=False, compare=False)
    _pdg_index: "PDGBuilder | None" = field(default=None, repr=False, compare=False)
    _slicer: "ProgramSlicer | None" = field(default=None, repr=False, compare=False)

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
    # Advanced Analysis Queries (PDG, Slicing, Taint) ⭐ v2.1
    # ============================================================

    def get_pdg_builder(self) -> "PDGBuilder | None":
        """
        Get or build PDG (Program Dependence Graph).

        Returns:
            PDGBuilder instance or None if not available
        """
        if self._pdg_index:
            return self._pdg_index

        # Lazy build from pdg_nodes/edges
        if self.pdg_nodes:
            from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder

            pdg = PDGBuilder()
            for node in self.pdg_nodes:
                pdg.nodes[node.node_id] = node
            for edge in self.pdg_edges:
                pdg.edges.append(edge)

            self._pdg_index = pdg
            return pdg

        return None

    def get_slicer(self) -> "ProgramSlicer | None":
        """
        Get program slicer (requires PDG).

        Returns:
            ProgramSlicer instance or None if PDG not available
        """
        if self._slicer:
            return self._slicer

        pdg = self.get_pdg_builder()
        if pdg:
            from src.contexts.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer, SliceConfig

            self._slicer = ProgramSlicer(
                pdg_builder=pdg, config=SliceConfig(interprocedural=True, max_function_depth=2)
            )
            return self._slicer

        return None

    def backward_slice(self, target_node_id: str, max_depth: int = 50) -> "SliceResult | None":
        """
        Backward slice: 이 노드에 영향을 준 모든 코드.

        Args:
            target_node_id: Target node ID
            max_depth: Maximum dependency depth

        Returns:
            SliceResult or None if slicer not available
        """
        slicer = self.get_slicer()
        if slicer:
            return slicer.backward_slice(target_node_id, max_depth)
        return None

    def forward_slice(self, source_node_id: str, max_depth: int = 50) -> "SliceResult | None":
        """
        Forward slice: 이 노드가 영향을 주는 모든 코드.

        Args:
            source_node_id: Source node ID
            max_depth: Maximum dependency depth

        Returns:
            SliceResult or None if slicer not available
        """
        slicer = self.get_slicer()
        if slicer:
            return slicer.forward_slice(source_node_id, max_depth)
        return None

    def get_taint_findings(self, severity: str | None = None) -> list["TaintFinding"]:
        """
        Get taint analysis findings (security vulnerabilities).

        Args:
            severity: Filter by severity (high, medium, low) or None for all

        Returns:
            List of taint findings
        """
        if not severity:
            return self.taint_findings

        return [f for f in self.taint_findings if f.severity == severity]

    def find_dataflow_path(self, from_node_id: str, to_node_id: str) -> list[str] | None:
        """
        Find dataflow path between two nodes.

        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID

        Returns:
            List of node IDs in path or None if no path found
        """
        pdg = self.get_pdg_builder()
        if not pdg:
            return None

        # BFS to find path
        from collections import deque

        queue = deque([(from_node_id, [from_node_id])])
        visited = set()

        while queue:
            current, path = queue.popleft()

            if current == to_node_id:
                return path

            if current in visited:
                continue

            visited.add(current)

            # Get data dependencies
            deps = pdg.get_dependents(current)
            for dep in deps:
                if dep.dependency_type.value == "DATA" and dep.to_node not in visited:
                    queue.append((dep.to_node, path + [dep.to_node]))

        return None

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
            # v2.1 additions
            "pdg_nodes": len(self.pdg_nodes),
            "pdg_edges": len(self.pdg_edges),
            "taint_findings": len(self.taint_findings),
        }

        # Occurrence stats
        self.ensure_indexes()
        if self._occurrence_index:
            stats["occurrence_stats"] = self._occurrence_index.get_stats()

        # Taint stats
        if self.taint_findings:
            stats["taint_stats"] = {
                "total": len(self.taint_findings),
                "high": len([f for f in self.taint_findings if f.severity == "high"]),
                "medium": len([f for f in self.taint_findings if f.severity == "medium"]),
                "low": len([f for f in self.taint_findings if f.severity == "low"]),
            }

        return stats
