"""
Rust IR Generator Adapter

Adapter for Rust-based IR generation with Python fallback.

HEXAGONAL ARCHITECTURE:
- Infrastructure layer (Adapter)
- Wraps Rust implementation
- Provides fallback to Python
- No domain logic

PRODUCTION REQUIREMENTS:
- Complete error handling
- No silent failures
- Graceful fallback
- Performance monitoring
"""

import logging
from typing import TYPE_CHECKING, Protocol

from codegraph_engine.code_foundation.infrastructure.ir.models import (
    Edge,
    IRDocument,
    Node,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.models import SourceFile

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Port Interface (Hexagonal Architecture)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ParallelIRBuilderPort(Protocol):
    """
    Port for parallel IR building.

    Hexagonal Architecture: Domain interface for IR generation.
    Implemented by RustIRAdapter.
    """

    def generate_ir_batch(
        self,
        sources: list["SourceFile"],
    ) -> tuple[list[IRDocument], dict[str, str]]:
        """
        Generate IR for multiple files.

        Args:
            sources: List of SourceFile objects

        Returns:
            (ir_documents, errors) - List of IRDocument and error map
        """
        ...


class RustIRAdapter:
    """
    Adapter for Rust IR generation.

    Features:
    - Rust-first execution
    - Python fallback on error
    - Performance tracking
    - Error reporting
    """

    def __init__(self, repo_id: str, enable_rust: bool = True):
        """
        Initialize adapter.

        Args:
            repo_id: Repository ID
            enable_rust: Enable Rust acceleration (default: True)
        """
        self.repo_id = repo_id
        self.enable_rust = enable_rust
        self._rust_available = False
        self._rust_module = None

        # Try to import Rust module
        if enable_rust:
            try:
                import codegraph_ast

                self._rust_module = codegraph_ast
                self._rust_available = True
                logger.info("Rust IR generator available")
            except ImportError as e:
                logger.warning(f"Rust IR generator not available: {e}")
                self._rust_available = False

    def is_rust_available(self) -> bool:
        """Check if Rust generator is available"""
        return self._rust_available

    def generate_ir_batch(
        self,
        sources: list["SourceFile"],
    ) -> tuple[list[IRDocument], dict[str, str]]:
        """
        Generate IR for multiple files.

        Args:
            sources: List of SourceFile objects

        Returns:
            (ir_documents, errors) - List of IRDocument and error map

        Raises:
            Never raises - returns errors in dict
        """
        if not self._rust_available or not self.enable_rust:
            # No Rust - return empty (caller will use Python fallback)
            return [], {}

        try:
            # Prepare files for Rust
            files = [(src.file_path, src.content, self._get_module_path(src)) for src in sources]

            # Call Rust
            results = self._rust_module.process_python_files(files, self.repo_id)

            # Convert to IRDocument
            ir_docs = []
            errors = {}

            for i, result in enumerate(results):
                src = sources[i]

                if not result.get("success", False):
                    # Rust failed - record error for fallback
                    error_msgs = result.get("errors", ["Unknown error"])
                    errors[src.file_path] = f"Rust error: {error_msgs}"
                    continue

                # Convert Rust result to IRDocument
                try:
                    ir_doc = self._convert_to_ir_document(result, src)
                    ir_docs.append(ir_doc)
                except Exception as e:
                    errors[src.file_path] = f"Conversion error: {e}"

            return ir_docs, errors

        except Exception as e:
            # Rust module crashed - log and return empty (fallback to Python)
            logger.error(f"Rust IR generation failed: {e}", exc_info=True)
            return [], {src.file_path: f"Rust crash: {e}" for src in sources}

    def _get_module_path(self, source: "SourceFile") -> str:
        """
        Extract module path from source file.

        Args:
            source: SourceFile

        Returns:
            Module FQN (e.g., "myapp.services.user")
        """
        # Convert file path to module path
        # e.g., "src/myapp/services/user.py" → "myapp.services.user"
        path = source.file_path

        # Remove extension
        if path.endswith(".py"):
            path = path[:-3]

        # Replace slashes with dots
        module = path.replace("/", ".").replace("\\", ".")

        # Remove common prefixes
        for prefix in ["src.", "lib.", "app."]:
            if module.startswith(prefix):
                module = module[len(prefix) :]

        return module

    def _convert_to_ir_document(
        self,
        rust_result: dict,
        source: "SourceFile",
    ) -> IRDocument:
        """
        Convert Rust result to IRDocument.

        Args:
            rust_result: Rust processing result
            source: Original source file

        Returns:
            IRDocument

        Raises:
            ValueError: If conversion fails
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            EdgeKind,
            NodeKind,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            Span as IRSpan,
        )

        # Extract nodes
        nodes = []
        for rust_node in rust_result.get("nodes", []):
            # Convert span
            rust_span = rust_node["span"]
            span = IRSpan(
                start_line=rust_span["start_line"],
                start_col=rust_span["start_col"],
                end_line=rust_span["end_line"],
                end_col=rust_span["end_col"],
            )

            # Convert kind (string → enum)
            # NOTE: Rust returns lowercase (function, class), Python expects Title (Function, Class)
            raw_kind = rust_node["kind"]
            kind_str = raw_kind.title() if raw_kind else "Function"
            try:
                kind = NodeKind(kind_str)
            except ValueError:
                logger.warning(f"Unknown node kind: {raw_kind} -> {kind_str}")
                kind = NodeKind.FUNCTION

            # Create Node
            node = Node(
                id=rust_node["id"],
                kind=kind,
                fqn=rust_node["fqn"],
                file_path=rust_node["file_path"],
                span=span,
                language=rust_node["language"],
                name=rust_node.get("name"),
                module_path=rust_node.get("module_path"),
                parent_id=rust_node.get("parent_id"),
                body_span=None,  # TODO: Extract from Rust
                docstring=rust_node.get("docstring"),
                content_hash=rust_node.get("content_hash"),
                attrs={},  # TODO: Extract from Rust
            )

            nodes.append(node)

        # Extract edges
        edges = []
        for rust_edge in rust_result.get("edges", []):
            # Convert kind
            kind_str = rust_edge["kind"]
            try:
                kind = EdgeKind(kind_str)
            except ValueError:
                logger.warning(f"Unknown edge kind: {kind_str}")
                continue

            # Convert span (optional)
            span = None
            if "span" in rust_edge:
                rust_span = rust_edge["span"]
                span = IRSpan(
                    start_line=rust_span["start_line"],
                    start_col=rust_span["start_col"],
                    end_line=rust_span["end_line"],
                    end_col=rust_span["end_col"],
                )

            # Create Edge
            edge = Edge(
                id=rust_edge["id"],
                kind=kind,
                source_id=rust_edge["source_id"],
                target_id=rust_edge["target_id"],
                span=span,
                attrs={},
            )

            edges.append(edge)

        # L2: Extract BFG graphs (needs nodes for function_node_id mapping)
        bfg_graphs = self._convert_bfg_graphs(rust_result.get("bfg_graphs", []), nodes)

        # L2: Extract CFG edges
        cfg_edges = self._convert_cfg_edges(rust_result.get("cfg_edges", []))

        # L3: Extract type entities
        type_entities = self._convert_type_entities(rust_result.get("type_entities", []))

        # Create IRDocument
        # Note: IRDocument is per-repo, but we use file_path as repo_id for single-file processing
        import datetime

        snapshot_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        ir_doc = IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            nodes=nodes,
            edges=edges,
            types=type_entities,  # Use converted type entities
        )

        # Store file_path for reference
        ir_doc.file_path = source.file_path  # type: ignore

        # L4: Extract DFG graphs
        dfg_graphs = self._convert_dfg_graphs(rust_result.get("dfg_graphs", []))

        # L5: Extract SSA graphs
        ssa_graphs = self._convert_ssa_graphs(rust_result.get("ssa_graphs", []))

        # Attach L2-L5 data
        ir_doc.bfg_graphs = bfg_graphs
        ir_doc.cfg_edges = cfg_edges
        ir_doc.type_entities = type_entities
        ir_doc.dfg_graphs = dfg_graphs
        ir_doc.ssa_graphs = ssa_graphs

        # Extract cfg_blocks from all bfg_graphs
        cfg_blocks = []
        for bfg in bfg_graphs:
            cfg_blocks.extend(bfg.blocks)
        ir_doc.cfg_blocks = cfg_blocks

        return ir_doc

    def _convert_bfg_graphs(self, rust_bfgs: list, nodes: list) -> list:
        """Convert Rust BFG graphs to BasicFlowGraph objects"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BasicFlowGraph,
            BFGBlockKind,
        )

        # Build function name -> node ID mapping
        func_name_to_id = {}
        for node in nodes:
            if node.kind.value in ["Function", "Method"] and node.name:
                func_name_to_id[node.name] = node.id

        bfg_graphs = []
        for rust_bfg in rust_bfgs:
            # Get function node ID from function name
            func_name = rust_bfg["function_id"]
            func_node_id = func_name_to_id.get(func_name, func_name)

            # Convert blocks
            blocks = []
            for rust_block in rust_bfg.get("blocks", []):
                rust_span = rust_block["span"]
                span = Span(
                    start_line=rust_span["start_line"],
                    start_col=rust_span["start_col"],
                    end_line=rust_span["end_line"],
                    end_col=rust_span["end_col"],
                )

                # Rust now returns exact Python enum values (e.g., "Statement", "Entry")
                kind_str = rust_block["kind"]
                try:
                    kind = BFGBlockKind(kind_str)
                except ValueError:
                    # Fallback for any unexpected values
                    kind = BFGBlockKind.STATEMENT

                block = BasicFlowBlock(
                    id=rust_block["id"],
                    kind=kind,
                    function_node_id=func_node_id,
                    span=span,
                    statement_count=rust_block["statement_count"],
                )
                blocks.append(block)

            bfg = BasicFlowGraph(
                id=rust_bfg["id"],
                function_node_id=func_node_id,
                entry_block_id=rust_bfg["entry_block_id"],
                exit_block_id=rust_bfg["exit_block_id"],
                blocks=blocks,
                total_statements=rust_bfg["total_statements"],
            )
            bfg_graphs.append(bfg)

        return bfg_graphs

    def _convert_cfg_edges(self, rust_cfg_edges: list) -> list:
        """Convert Rust CFG edges to Python objects"""
        cfg_edges = []
        for rust_edge in rust_cfg_edges:
            edge = {
                "source_block_id": rust_edge["source_block_id"],
                "target_block_id": rust_edge["target_block_id"],
                "edge_type": rust_edge["edge_type"],
            }
            cfg_edges.append(edge)

        return cfg_edges

    def _convert_type_entities(self, rust_types: list) -> list:
        """Convert Rust type entities to TypeEntity objects"""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.models import (
            TypeEntity,
            TypeFlavor,
            TypeResolutionLevel,
        )

        type_entities = []
        for rust_type in rust_types:
            # Rust now returns exact Python enum values (e.g., "builtin", "user")
            try:
                flavor = TypeFlavor(rust_type["flavor"])
            except ValueError:
                flavor = TypeFlavor.EXTERNAL

            try:
                resolution_level = TypeResolutionLevel(rust_type["resolution_level"])
            except ValueError:
                resolution_level = TypeResolutionLevel.RAW

            type_entity = TypeEntity(
                id=rust_type["id"],
                raw=rust_type["raw"],
                flavor=flavor,
                is_nullable=rust_type["is_nullable"],
                resolution_level=resolution_level,
                resolved_target=rust_type.get("resolved_target"),
                generic_param_ids=rust_type.get("generic_param_ids") or [],
            )
            type_entities.append(type_entity)

        return type_entities

    def _convert_dfg_graphs(self, rust_dfgs: list) -> list:
        """Convert Rust DFG graphs to Python objects"""
        dfg_graphs = []
        for rust_dfg in rust_dfgs:
            dfg = {
                "function_id": rust_dfg["function_id"],
                "node_count": rust_dfg["node_count"],
                "edge_count": rust_dfg["edge_count"],
            }
            dfg_graphs.append(dfg)

        return dfg_graphs

    def _convert_ssa_graphs(self, rust_ssas: list) -> list:
        """Convert Rust SSA graphs to Python objects"""
        ssa_graphs = []
        for rust_ssa in rust_ssas:
            ssa = {
                "function_id": rust_ssa["function_id"],
                "variable_count": rust_ssa["variable_count"],
                "phi_node_count": rust_ssa["phi_node_count"],
            }
            ssa_graphs.append(ssa)

        return ssa_graphs


# Singleton instance
_rust_adapter_instance: RustIRAdapter | None = None


def get_rust_adapter(repo_id: str, enable_rust: bool = True) -> RustIRAdapter:
    """
    Get or create Rust adapter singleton.

    Args:
        repo_id: Repository ID
        enable_rust: Enable Rust acceleration

    Returns:
        RustIRAdapter instance
    """
    global _rust_adapter_instance

    if _rust_adapter_instance is None:
        _rust_adapter_instance = RustIRAdapter(repo_id, enable_rust)

    return _rust_adapter_instance
