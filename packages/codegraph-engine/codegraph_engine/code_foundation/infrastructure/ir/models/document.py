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

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge, FindingSeverity, Node, NodeKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.template_ports import (
        TemplateElementContract,
        TemplateSlotContract,
    )
    from codegraph_engine.code_foundation.domain.taint.models import Vulnerability
    from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
    from codegraph_engine.code_foundation.infrastructure.dfg.ssa.dominator import DominatorTree
    from codegraph_engine.code_foundation.infrastructure.dfg.ssa.ssa_builder import SSAContext
    from codegraph_engine.code_foundation.infrastructure.ir.models.diagnostic import Diagnostic, DiagnosticIndex
    from codegraph_engine.code_foundation.infrastructure.ir.models.interprocedural import InterproceduralDataFlowEdge
    from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import (
        Occurrence,
        OccurrenceIndex,
        SymbolRole,
    )
    from codegraph_engine.code_foundation.infrastructure.ir.models.package import PackageIndex, PackageMetadata
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock, BasicFlowGraph
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
        CFGBlockKind,
        ControlFlowBlock,
        ControlFlowEdge,
        ControlFlowGraph,
    )
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity
    from codegraph_engine.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder
    from codegraph_engine.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer
    from codegraph_analysis.security_analysis.domain.models import UnifiedSymbol
    from codegraph_shared.kernel.pdg.models import PDGEdge, PDGNode
    from codegraph_shared.kernel.slice.models import SliceResult


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
        from codegraph_engine.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
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
    schema_version: str = "2.3"  # ⭐ IR schema version (v2.3 adds Template IR - RFC-051)

    # [Required] Structural IR
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    # [Optional] Semantic IR
    types: list["TypeEntity"] = field(default_factory=list)
    signatures: list["SignatureEntity"] = field(default_factory=list)
    cfgs: list["ControlFlowGraph"] = field(default_factory=list)

    # ⭐ NEW in v2.1: Extended Semantic IR (CFG/BFG/DFG)
    cfg_blocks: list["ControlFlowBlock"] = field(default_factory=list)
    """CFG blocks (flat list for fast access)"""
    cfg_edges: list["ControlFlowEdge"] = field(default_factory=list)
    """CFG edges (flat list for fast access)"""
    bfg_graphs: list["BasicFlowGraph"] = field(default_factory=list)
    """BFG graphs (basic block graphs)"""
    bfg_blocks: list["BasicFlowBlock"] = field(default_factory=list)
    """BFG blocks (flat list for fast access)"""
    dfg_snapshot: "DfgSnapshot | None" = None
    """DFG snapshot (data flow graph with variables/events/edges)"""
    # SOTA Phase 2: Arena-based storage (backward compatible)
    _expr_arena: "ExpressionArena | None" = field(default=None, repr=False, compare=False)
    """Expression Arena (SOTA: SoA for memory efficiency)"""
    _expressions_list: list["Expression"] | None = field(default=None, repr=False, compare=False)
    """Legacy expression list (for backward compatibility)"""

    interprocedural_edges: list["InterproceduralDataFlowEdge"] = field(default_factory=list)
    """Inter-procedural data flow edges (arg→param, return→callsite) ⭐ NEW"""

    # SOTA Phase 2: String interning
    _string_intern: "StringIntern | None" = field(default=None, repr=False, compare=False)
    """String intern registry (SOTA: deduplication)"""

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

    taint_findings: list["Vulnerability"] = field(default_factory=list)
    """Taint analysis results (security vulnerabilities)"""

    # ⭐ NEW in v2.2: SSA/Dominator Analysis (Path Sensitivity)
    ssa_contexts: dict[str, "SSAContext"] = field(default_factory=dict)
    """SSA contexts per function (function_id -> SSAContext with phi-nodes, dom_tree)"""

    dominator_trees: dict[str, "DominatorTree"] = field(default_factory=dict)
    """Dominator trees per function (function_id -> DominatorTree) for Guard validation"""

    # ⭐ NEW in v2.3: Template IR (RFC-051)
    template_slots: list["TemplateSlotContract"] = field(default_factory=list)
    """Template slots (XSS analysis targets) - TemplateSlotContract"""

    template_elements: list["TemplateElementContract"] = field(default_factory=list)
    """Template elements (Skeleton Parsed) - TemplateElementContract"""

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
    # RFC-020 Phase 2: QueryEngine 최적화 인덱스
    # ============================================================
    _nodes_by_kind: dict["NodeKind", list[Node]] | None = field(default=None, repr=False, compare=False)
    """O(1) node lookup by kind (500-5000x vs O(N) scan)"""

    _edges_by_target: dict[str, list[Edge]] | None = field(default=None, repr=False, compare=False)
    """O(1) reverse edge lookup (backward traversal optimization)"""

    _cfg_blocks_by_kind: dict["CFGBlockKind", list["ControlFlowBlock"]] | None = field(
        default=None, repr=False, compare=False
    )
    """O(1) CFG block lookup by kind (Structural Search 필수)"""

    _expressions_by_kind: dict["ExprKind", list["Expression"]] | None = field(default=None, repr=False, compare=False)
    """O(1) expression lookup by kind (Q.Call filtering)"""

    # ⭐ NEW in v2.3: Template IR indexes (RFC-051)
    _slots_by_context: dict[Any, list[Any]] | None = field(default=None, repr=False, compare=False)
    """O(1) slot lookup by context kind (XSS analysis)"""

    _slots_by_file: dict[str, list[Any]] | None = field(default=None, repr=False, compare=False)
    """O(1) slot lookup by file path"""

    _bindings_by_slot: dict[str, list[Edge]] | None = field(default=None, repr=False, compare=False)
    """O(1) BINDS edge lookup by slot_id (slot → source variable)"""

    _bindings_by_source: dict[str, list[Edge]] | None = field(default=None, repr=False, compare=False)
    """O(1) BINDS edge lookup by source_id (variable → slots)"""

    _slots_by_id: dict[str, "TemplateSlotContract"] | None = field(default=None, repr=False, compare=False)
    """O(1) slot lookup by slot_id (RFC-051 optimization)"""

    # ============================================================
    # SOTA Phase 2: Arena Properties (Backward Compatible)
    # ============================================================

    @property
    def expressions(self) -> list["Expression"]:
        """
        Get expressions (SOTA: Arena-aware property).

        Returns list[Expression] for backward compatibility.
        Internally uses Arena if available, otherwise legacy list.

        Performance:
        - Arena mode: Lazy conversion (only when accessed)
        - Legacy mode: Direct list access
        """
        # Arena mode (SOTA)
        if self._expr_arena is not None:
            # Lazy conversion: Arena → Expression objects
            if self._expressions_list is None:
                from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression

                self._expressions_list = []
                for i in range(self._expr_arena.count):
                    expr_data = self._expr_arena.get(i)
                    # Convert Arena data → Expression object
                    # TODO: Full conversion logic
                    pass
            return self._expressions_list

        # Legacy mode (backward compatible)
        if self._expressions_list is None:
            self._expressions_list = []
        return self._expressions_list

    @expressions.setter
    def expressions(self, value: list["Expression"]) -> None:
        """Set expressions (backward compatible)."""
        self._expressions_list = value
        # Clear arena (legacy mode)
        self._expr_arena = None

    # ============================================================
    # Index Building
    # ============================================================

    def assign_local_seq(self) -> None:
        """
        RFC-RUST-ENGINE Phase 1: Assign local_seq to all nodes and edges.

        local_seq is a sequential integer starting from 0 used as a tie-breaker
        for total ordering. This ensures deterministic ordering across runs.

        Call this after IR generation and BEFORE enforce_total_ordering().
        """
        # Assign local_seq to nodes (in insertion order)
        for idx, node in enumerate(self.nodes):
            node.local_seq = idx

        # Assign local_seq to edges (in insertion order)
        for idx, edge in enumerate(self.edges):
            edge.local_seq = idx

    def enforce_total_ordering(self) -> None:
        """
        RFC-RUST-ENGINE Phase 1: Enforce deterministic total ordering.

        Ordering keys (from RFC Section 6):
        - Nodes: (file_path, kind, start_byte, end_byte, local_seq)
        - Edges: (source_id, target_id, kind, local_seq)

        Tie-breaker: local_seq ensures no two records have equal ordering.
        Guarantees: Same input → same ordering → same hash

        Prerequisites:
        - local_seq must be assigned (call assign_local_seq() first)

        Call this BEFORE serialization to ensure deterministic output.
        """

        def node_ordering_key(node: Node) -> tuple:
            """Total order key for nodes (RFC Section 6.3.1)"""
            return (
                node.file_path,
                node.kind.value if hasattr(node.kind, "value") else str(node.kind),
                node.span.start_line if node.span else 0,
                node.span.end_line if node.span else 0,
                node.local_seq,  # Tie-breaker
            )

        def edge_ordering_key(edge: Edge) -> tuple:
            """Total order key for edges (RFC Section 6.3.2)"""
            return (
                edge.source_id,
                edge.target_id,
                edge.kind.value if hasattr(edge.kind, "value") else str(edge.kind),
                edge.local_seq,  # Tie-breaker
            )

        # Sort with total ordering guarantee
        self.nodes = sorted(self.nodes, key=node_ordering_key)
        self.edges = sorted(self.edges, key=edge_ordering_key)

    def build_indexes(self, sort_key: str = "id") -> None:
        """
        Build all indexes for fast lookup.

        Call this after loading IR from disk or after generating occurrences.
        Indexes are built lazily (only when needed).

        Args:
            sort_key: Key to sort nodes/edges for deterministic iteration (RFC-037)
                     - "id": Stable sorting by ID (backward compat)
                     - "total_order": RFC-RUST-ENGINE total ordering with local_seq
        """
        # RFC-037: Stable sorting for deterministic builds
        # RFC-RUST-ENGINE Phase 1: Total ordering with local_seq
        if sort_key == "total_order":
            self.enforce_total_ordering()
        elif sort_key == "id":
            self.nodes = sorted(self.nodes, key=lambda n: n.id)
            self.edges = sorted(self.edges, key=lambda e: (e.source_id, e.target_id, e.kind.value))

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
            from codegraph_engine.code_foundation.infrastructure.ir.models.occurrence import OccurrenceIndex

            self._occurrence_index = OccurrenceIndex()
            for occ in self.occurrences:
                self._occurrence_index.add(occ)

        # ============================================================
        # RFC-020 Phase 2: QueryEngine 최적화 인덱스 (4개)
        # Overhead: ~3ms for 10K nodes (실측, 허용 가능)
        # ============================================================

        # 1. Nodes by kind (O(N) → O(1), 500-5000x improvement)
        self._nodes_by_kind = {}
        for node in self.nodes:
            self._nodes_by_kind.setdefault(node.kind, []).append(node)

        # 2. Edges by target (backward traversal optimization)
        self._edges_by_target = {}
        for edge in self.edges:
            self._edges_by_target.setdefault(edge.target_id, []).append(edge)

        # 3. CFG blocks by kind (Structural Search 필수)
        self._cfg_blocks_by_kind = {}
        for block in self.cfg_blocks:
            self._cfg_blocks_by_kind.setdefault(block.kind, []).append(block)

        # 4. Expressions by kind (Q.Call filtering)
        self._expressions_by_kind = {}
        for expr in self.expressions:  # Uses property (Arena-aware)
            self._expressions_by_kind.setdefault(expr.kind, []).append(expr)

        # 5. RFC-034: Expression by ID (O(1) lookup for argument resolution)
        self._expr_map = {expr.id: expr for expr in self.expressions}  # Uses property

        # ============================================================
        # RFC-051: Template IR 인덱스 (4개)
        # Overhead: ~1ms for 1K slots (XSS analysis 최적화)
        # ============================================================

        # 1. Slots by context kind (O(1) XSS sink lookup)
        self._slots_by_context = {}
        for slot in self.template_slots:
            # slot.context_kind is SlotContextKind enum
            context_kind = getattr(slot, "context_kind", None)
            if context_kind:
                self._slots_by_context.setdefault(context_kind, []).append(slot)

        # 2. Slots by file (O(1) file-level analysis)
        self._slots_by_file = {}
        self._slots_by_id = {}  # RFC-051 optimization
        for slot in self.template_slots:
            # Extract file_path from slot_id: "slot:file.tsx:42:15"
            slot_id = getattr(slot, "slot_id", "")
            if slot_id:
                # slot_id → slot mapping (O(1) lookup)
                self._slots_by_id[slot_id] = slot

                # file-level index
                if ":" in slot_id:
                    parts = slot_id.split(":")
                    if len(parts) >= 2:
                        file_path = parts[1]
                        self._slots_by_file.setdefault(file_path, []).append(slot)

        # 3. BINDS edges by slot (slot → source variables)
        # Import EdgeKind locally to avoid circular dependency
        from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import EdgeKind as EK

        self._bindings_by_slot = {}
        for edge in self.edges:
            # Use enum comparison (edge.kind is EdgeKind enum)
            if edge.kind == EK.BINDS:
                self._bindings_by_slot.setdefault(edge.target_id, []).append(edge)

        # 4. BINDS edges by source (variable → slots)
        self._bindings_by_source = {}
        for edge in self.edges:
            if edge.kind == EK.BINDS:
                self._bindings_by_source.setdefault(edge.source_id, []).append(edge)

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

    # ============================================================
    # RFC-020 Phase 2: QueryEngine 최적화 조회 메서드
    # ============================================================

    def get_nodes_by_kind(self, kind: "str | NodeKind") -> list[Node]:
        """
        Get nodes by kind (O(1) lookup)

        RFC-020 Phase 2: 500-5000x improvement vs O(N) scan

        Args:
            kind: NodeKind enum or string

        Returns:
            List of nodes with matching kind
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        self.ensure_indexes()

        if not self._nodes_by_kind:
            return []

        # Handle both string and NodeKind enum
        if isinstance(kind, str):
            try:
                kind_enum = NodeKind(kind)
            except ValueError:
                try:
                    kind_enum = NodeKind(kind.upper())
                except ValueError:
                    return []
        else:
            kind_enum = kind

        return self._nodes_by_kind.get(kind_enum, [])

    def get_edges_by_target(self, target_id: str) -> list[Edge]:
        """
        Get edges by target node (O(1) reverse lookup)

        RFC-020 Phase 2: Backward traversal optimization

        Args:
            target_id: Target node ID

        Returns:
            List of edges pointing to target
        """
        self.ensure_indexes()
        return self._edges_by_target.get(target_id, []) if self._edges_by_target else []

    def get_cfg_blocks_by_kind(self, kind: "CFGBlockKind") -> list["ControlFlowBlock"]:
        """
        Get CFG blocks by kind (O(1) lookup)

        RFC-020 Phase 2: Structural Search 필수 최적화

        Args:
            kind: CFGBlockKind enum

        Returns:
            List of CFG blocks with matching kind
        """
        self.ensure_indexes()
        return self._cfg_blocks_by_kind.get(kind, []) if self._cfg_blocks_by_kind else []

    def get_expressions_by_kind(self, kind: "ExprKind") -> list["Expression"]:
        """
        Get expressions by kind (O(1) lookup)

        RFC-020 Phase 2: Q.Call filtering optimization

        Args:
            kind: ExprKind enum

        Returns:
            List of expressions with matching kind
        """
        self.ensure_indexes()
        return self._expressions_by_kind.get(kind, []) if self._expressions_by_kind else []

    def find_nodes_by_name(self, name: str) -> list[Node]:
        """Find nodes by name (case-sensitive)"""
        return [n for n in self.nodes if n.name == name]

    def find_nodes_by_kind(self, kind: "str | NodeKind") -> list[Node]:
        """
        ⭐ RFC-19 FIX: Find nodes by kind (handles both string and NodeKind enum)

        Args:
            kind: Either "METHOD" string or NodeKind.METHOD enum
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        # Handle both string and NodeKind enum
        if isinstance(kind, str):
            # Convert string to NodeKind enum
            try:
                kind_enum = NodeKind(kind)
            except ValueError:
                # Try uppercase
                try:
                    kind_enum = NodeKind(kind.upper())
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
            try:
                # Optional import: reasoning_engine may not be available
                # Hexagonal: This is a convenience method, not a core dependency
                from codegraph_engine.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder

                pdg = PDGBuilder()
                for node in self.pdg_nodes:
                    pdg.nodes[node.node_id] = node
                for edge in self.pdg_edges:
                    pdg.edges.append(edge)

                self._pdg_index = pdg
                return pdg
            except ImportError:
                # reasoning_engine not available - graceful degradation
                return None

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
            try:
                # Optional import: reasoning_engine may not be available
                # Hexagonal: This is a convenience method, not a core dependency
                from codegraph_engine.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer, SliceConfig

                self._slicer = ProgramSlicer(
                    pdg_builder=pdg, config=SliceConfig(interprocedural=True, max_function_depth=2)
                )
                return self._slicer
            except ImportError:
                # reasoning_engine not available - graceful degradation
                return None

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

    def get_taint_findings(self, severity: FindingSeverity | str | None = None) -> list["Vulnerability"]:
        """
        Get taint analysis findings (security vulnerabilities).

        Args:
            severity: Filter by severity (FindingSeverity enum or string) or None for all

        Returns:
            List of taint findings
        """
        if not severity:
            return self.taint_findings

        # Normalize to string for comparison
        severity_value = severity.value if isinstance(severity, FindingSeverity) else severity
        return [f for f in self.taint_findings if f.severity == severity_value]

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

    def get_all_expressions(self) -> list["Expression"]:
        """
        Get all expressions (for taint analysis).

        Returns:
            List of expressions
        """
        return self.expressions

    # ============================================================
    # Template IR Queries (RFC-051) ⭐ v2.3
    # ============================================================

    def get_slots_by_context(self, context_kind: Any) -> list[Any]:
        """
        Get template slots by context kind (O(1) indexed lookup).

        RFC-051: Context-aware XSS sink detection

        Args:
            context_kind: SlotContextKind enum value

        Returns:
            List of TemplateSlotContract with matching context

        Example:
            >>> raw_html_slots = ir_doc.get_slots_by_context(SlotContextKind.RAW_HTML)
            >>> url_sinks = ir_doc.get_slots_by_context(SlotContextKind.URL_ATTR)
        """
        self.ensure_indexes()
        return self._slots_by_context.get(context_kind, []) if self._slots_by_context else []

    def get_raw_html_sinks(self) -> list[Any]:
        """
        Get RAW_HTML slots (XSS critical sinks).

        RFC-051: Primary XSS attack vector detection
        (dangerouslySetInnerHTML, v-html, |safe)

        Returns:
            List of TemplateSlotContract with RAW_HTML context
        """
        # Import here to avoid circular dependency
        try:
            from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind

            return self.get_slots_by_context(SlotContextKind.RAW_HTML)
        except ImportError:
            # Fallback if template_ports not available
            return [s for s in self.template_slots if getattr(s, "is_sink", False)]

    def get_url_sinks(self) -> list[Any]:
        """
        Get URL_ATTR slots (SSRF/XSS sinks).

        RFC-051: URL injection attack vector detection
        (<a href="...">, <img src="...">)

        Returns:
            List of TemplateSlotContract with URL_ATTR context
        """
        try:
            from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind

            return self.get_slots_by_context(SlotContextKind.URL_ATTR)
        except ImportError:
            return []

    def get_slot_bindings(self, slot_id: str) -> list[Edge]:
        """
        Get BINDS edges for a template slot (O(1) indexed lookup).

        RFC-051: Trace data flow from slot back to source variables

        Args:
            slot_id: Template slot ID

        Returns:
            List of Edge with kind=BINDS, target_id=slot_id

        Example:
            >>> bindings = ir_doc.get_slot_bindings("slot:profile.tsx:42:15")
            >>> for edge in bindings:
            ...     source_var = ir_doc.get_node(edge.source_id)
            ...     print(f"Slot bound to: {source_var.name}")
        """
        self.ensure_indexes()
        return self._bindings_by_slot.get(slot_id, []) if self._bindings_by_slot else []

    def get_variable_slots(self, variable_id: str) -> list["TemplateSlotContract"]:
        """
        Get template slots where variable is exposed (O(1) reverse lookup).

        RFC-051: "Where is this variable rendered?" analysis
        SOTA: O(bindings) vs O(N) - 100-1000x improvement

        Args:
            variable_id: Node ID of variable

        Returns:
            List of TemplateSlotContract bound to this variable

        Example:
            >>> slots = ir_doc.get_variable_slots("var:user_bio")
            >>> for slot in slots:
            ...     print(f"Exposed at: {slot.slot_id}, context: {slot.context_kind}")
        """
        self.ensure_indexes()
        if not self._bindings_by_source or not self._slots_by_id:
            return []

        # Get BINDS edges from this variable
        binds_edges = self._bindings_by_source.get(variable_id, [])

        # O(bindings) lookup via slot_id index (vs O(N) scan)
        result = []
        for edge in binds_edges:
            slot = self._slots_by_id.get(edge.target_id)
            if slot:
                result.append(slot)

        return result

    def get_slots_by_file(self, file_path: str) -> list[Any]:
        """
        Get all template slots in a file (O(1) indexed lookup).

        RFC-051: File-level XSS analysis

        Args:
            file_path: Source file path

        Returns:
            List of TemplateSlotContract in file
        """
        self.ensure_indexes()
        return self._slots_by_file.get(file_path, []) if self._slots_by_file else []

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
            # v2.3 additions (RFC-051)
            "template_slots": len(self.template_slots),
            "template_elements": len(self.template_elements),
        }

        # Occurrence stats
        self.ensure_indexes()
        if self._occurrence_index:
            stats["occurrence_stats"] = self._occurrence_index.get_stats()

        # Taint stats
        if self.taint_findings:
            stats["taint_stats"] = {
                "total": len(self.taint_findings),
                FindingSeverity.HIGH.value: len(
                    [f for f in self.taint_findings if f.severity == FindingSeverity.HIGH.value]
                ),
                FindingSeverity.MEDIUM.value: len(
                    [f for f in self.taint_findings if f.severity == FindingSeverity.MEDIUM.value]
                ),
                FindingSeverity.LOW.value: len(
                    [f for f in self.taint_findings if f.severity == FindingSeverity.LOW.value]
                ),
            }

        # Template IR stats (RFC-051)
        if self.template_slots:
            # Count by context kind
            context_breakdown = {}
            for slot in self.template_slots:
                context_kind = getattr(slot, "context_kind", None)
                if context_kind:
                    context_str = str(context_kind.value) if hasattr(context_kind, "value") else str(context_kind)
                    context_breakdown[context_str] = context_breakdown.get(context_str, 0) + 1

            # Count sinks
            sink_count = sum(1 for s in self.template_slots if getattr(s, "is_sink", False))

            stats["template_stats"] = {
                "total_slots": len(self.template_slots),
                "total_elements": len(self.template_elements),
                "sink_count": sink_count,
                "context_breakdown": context_breakdown,
            }

        return stats

    @property
    def estimated_size(self) -> int:
        """
        메모리 크기 추정 (bytes).

        RFC-039: Tiered IR Cache Architecture - L1 MemoryCache size-based eviction

        Used by MemoryCache for size-based eviction to prevent OOM.

        Estimation Formula:
            - Node: ~200 bytes (name, type, location, metadata)
            - Edge: ~100 bytes (source, target, kind)
            - Occurrence: ~50 bytes (symbol, location)
            - TypeEntity: ~150 bytes (type info)
            - SignatureEntity: ~200 bytes (signature info)
            - CFG Block: ~300 bytes (block + statements)
            - CFG Edge: ~50 bytes (edge)
            - BFG Block: ~200 bytes (basic block)
            - PDG Node: ~250 bytes (node + deps)
            - PDG Edge: ~80 bytes (edge)
            - Template Slot: ~150 bytes (slot info)
            - Template Element: ~100 bytes (element info)
            - Base overhead: 2000 bytes (dataclass + indexes)

        SOTA Considerations:
            - Conservative estimates (actual size may be lower)
            - String interning reduces actual memory (not counted here)
            - Expression Arena reduces DFG memory (not counted here)
            - Assumes worst-case (no deduplication)

        Returns:
            Estimated memory size in bytes

        Example:
            >>> ir_doc = IRDocument(...)
            >>> ir_doc.estimated_size
            1048576  # ~1MB
        """
        # Structural IR
        node_size = len(self.nodes) * 200
        edge_size = len(self.edges) * 100
        occurrence_size = len(self.occurrences) * 50

        # Semantic IR
        type_size = len(self.types) * 150
        signature_size = len(self.signatures) * 200
        cfg_size = len(self.cfgs) * 500  # Avg 500 bytes per CFG

        # Extended Semantic IR (v2.1)
        cfg_block_size = len(self.cfg_blocks) * 300
        cfg_edge_size = len(self.cfg_edges) * 50
        bfg_graph_size = len(self.bfg_graphs) * 1000  # Avg 1KB per graph
        bfg_block_size = len(self.bfg_blocks) * 200

        # DFG (conservative estimate)
        dfg_size = 0
        if self.dfg_snapshot:
            # DFG variables + events + edges
            dfg_size = (
                len(getattr(self.dfg_snapshot, "variables", [])) * 100
                + len(getattr(self.dfg_snapshot, "events", [])) * 150
                + len(getattr(self.dfg_snapshot, "edges", [])) * 80
            )

        # Interprocedural edges
        interproc_size = len(self.interprocedural_edges) * 120

        # Analysis Indexes (v2.1)
        pdg_node_size = len(self.pdg_nodes) * 250
        pdg_edge_size = len(self.pdg_edges) * 80
        taint_size = len(self.taint_findings) * 300  # Vulnerabilities are larger

        # Template IR (v2.3 - RFC-051)
        template_slot_size = len(self.template_slots) * 150
        template_element_size = len(self.template_elements) * 100

        # Diagnostics & Packages
        diagnostic_size = len(self.diagnostics) * 200
        package_size = len(self.packages) * 500

        # Unified symbols (cross-language)
        unified_symbol_size = len(self.unified_symbols) * 200

        # SSA contexts (conservative)
        ssa_size = len(self.ssa_contexts) * 2000  # Avg 2KB per function context

        # Base overhead (dataclass + indexes)
        base_overhead = 2000

        total_size = (
            node_size
            + edge_size
            + occurrence_size
            + type_size
            + signature_size
            + cfg_size
            + cfg_block_size
            + cfg_edge_size
            + bfg_graph_size
            + bfg_block_size
            + dfg_size
            + interproc_size
            + pdg_node_size
            + pdg_edge_size
            + taint_size
            + template_slot_size
            + template_element_size
            + diagnostic_size
            + package_size
            + unified_symbol_size
            + ssa_size
            + base_overhead
        )

        return total_size
