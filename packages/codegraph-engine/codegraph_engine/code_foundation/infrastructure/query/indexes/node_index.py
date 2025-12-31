"""
NodeIndex - Node Indexing (SRP)

Single Responsibility: Node 인덱싱 및 조회
- O(1) node lookup by ID
- O(1) node existence check
- Memory-efficient storage

SOLID:
- S: Node 인덱싱만 담당
- O: Extensible for new node types
- L: Substitutable with Port
- I: Minimal interface
- D: Depends on abstractions (IRDocument)

RFC-031 Compliance:
- NodeKind: Canonical from ir/models/kinds.py
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.results import UnifiedNode
from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import NodeKind  # RFC-031: Canonical

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import (
        ControlFlowBlock,
        IRDocument,
        Node,
    )

logger = get_logger(__name__)


class NodeIndex:
    """
    Node indexing layer

    Responsibilities:
    1. Build node index from IR
    2. O(1) node lookup by ID
    3. Get all nodes (for wildcard queries)

    Performance:
    - Build: O(N) where N = total nodes
    - Lookup: O(1)
    - Memory: ~N * avg_node_size
    """

    def __init__(self, ir_doc: "IRDocument"):
        """
        Initialize node index

        Args:
            ir_doc: IR document
        """
        self._node_by_id: dict[str, UnifiedNode] = {}
        self._build(ir_doc)

        logger.info("node_index_built", node_count=len(self._node_by_id))

    def _build(self, ir_doc: "IRDocument") -> None:
        """Build node index from IR"""
        # Index IR nodes
        for node in ir_doc.nodes:
            unified = self._convert_ir_node(node)
            self._node_by_id[node.id] = unified

        # Index DFG variables
        if ir_doc.dfg_snapshot:
            for var in ir_doc.dfg_snapshot.variables:
                unified = self._convert_variable(var)
                self._node_by_id[var.id] = unified

        # Index CFG blocks
        for block in ir_doc.cfg_blocks:
            unified = self._convert_block(block, ir_doc)
            self._node_by_id[block.id] = unified

        # Index expressions (for Q.Call support)
        for expr in ir_doc.expressions:
            unified = self._convert_expression(expr)
            self._node_by_id[expr.id] = unified

        # 🔥 Index abstract heap nodes from interprocedural edges
        # Collection edges use abstract element IDs like "var:...:queries@6:4[*]"
        # These need to be registered as nodes for traversal to work
        if hasattr(ir_doc, "interprocedural_edges"):
            for edge in ir_doc.interprocedural_edges:
                # Add from_var_id as node if not exists
                if edge.from_var_id and edge.from_var_id not in self._node_by_id:
                    self._node_by_id[edge.from_var_id] = self._create_abstract_node(edge.from_var_id)

                # Add to_var_id as node if not exists (especially [*] elements)
                if edge.to_var_id and edge.to_var_id not in self._node_by_id:
                    self._node_by_id[edge.to_var_id] = self._create_abstract_node(edge.to_var_id)

        # 🔥 SOTA: Index callee target nodes from DFG edges
        # DFG edges use "callee:func_name:param:N" as targets for function arguments
        # These need to be registered as nodes for traversal to work
        if ir_doc.dfg_snapshot:
            for dfg_edge in ir_doc.dfg_snapshot.edges:
                # Add callee target nodes (reuse _create_abstract_node which handles callee: prefix)
                if dfg_edge.to_variable_id.startswith("callee:") and dfg_edge.to_variable_id not in self._node_by_id:
                    self._node_by_id[dfg_edge.to_variable_id] = self._create_abstract_node(dfg_edge.to_variable_id)

    def get(self, node_id: str) -> UnifiedNode | None:
        """
        Get node by ID (O(1))

        Args:
            node_id: Node ID

        Returns:
            UnifiedNode or None if not found
        """
        return self._node_by_id.get(node_id)

    def exists(self, node_id: str) -> bool:
        """Check if node exists (O(1))"""
        return node_id in self._node_by_id

    def get_all(self) -> list[UnifiedNode]:
        """
        Get all nodes

        Warning: Expensive operation (O(N))
        Use only for Q.Any() queries.
        """
        return list(self._node_by_id.values())

    def get_count(self) -> int:
        """Get total node count"""
        return len(self._node_by_id)

    # ============================================================
    # Conversion Methods (IR → Domain)
    # ============================================================

    def _convert_ir_node(self, node: "Node") -> UnifiedNode:
        """
        Convert IR Node to UnifiedNode

        RFC-031: Uses canonical NodeKind from ir/models/kinds.py.
        node.kind is already canonical NodeKind (same source).
        """
        span = None
        if node.span:
            span = (node.span.start_line, node.span.start_col, node.span.end_line, node.span.end_col)

        # RFC-031: node.kind is already canonical NodeKind
        # No conversion needed - both use the same enum
        domain_kind = node.kind

        return UnifiedNode(
            id=node.id,
            kind=domain_kind,
            name=node.name,
            file_path=node.file_path,
            span=span,
            attrs={"fqn": node.fqn, **node.attrs},
        )

    def _convert_variable(self, var) -> UnifiedNode:
        """
        Convert VariableEntity to UnifiedNode

        RFC-031: Uses canonical NodeKind.VARIABLE
        """
        span = None
        if var.decl_span:
            span = (var.decl_span.start_line, var.decl_span.start_col, var.decl_span.end_line, var.decl_span.end_col)

        return UnifiedNode(
            id=var.id,
            kind=NodeKind.VARIABLE,  # RFC-031: Canonical
            name=var.name,
            file_path=var.file_path,
            span=span,
            attrs={
                "function_fqn": var.function_fqn,
                "var_kind": var.kind,
                "type_id": var.type_id,
                "scope_id": var.scope_id,
            },
        )

    def _convert_block(self, block: "ControlFlowBlock", ir_doc: "IRDocument") -> UnifiedNode:
        """
        Convert ControlFlowBlock to UnifiedNode

        RFC-031: Uses canonical NodeKind.BLOCK
        """
        span = None
        if block.span:
            span = (block.span.start_line, block.span.start_col, block.span.end_line, block.span.end_col)

        # Get file_path from function node
        func_node = ir_doc.get_node(block.function_node_id)
        file_path = func_node.file_path if func_node else ""

        return UnifiedNode(
            id=block.id,
            kind=NodeKind.BLOCK,  # RFC-031: Canonical
            name=block.kind.value,
            file_path=file_path,
            span=span,
            attrs={"block_kind": block.kind.value, "function_node_id": block.function_node_id},
        )

    def _convert_expression(self, expr) -> UnifiedNode:
        """
        Convert Expression to UnifiedNode

        RFC-031: Uses canonical NodeKind.EXPRESSION
        """
        span = None
        if expr.span:
            span = (expr.span.start_line, expr.span.start_col, expr.span.end_line, expr.span.end_col)

        return UnifiedNode(
            id=expr.id,
            kind=NodeKind.EXPRESSION,  # RFC-031: Canonical
            name=expr.attrs.get("callee_name", ""),
            file_path=expr.file_path,
            span=span,
            attrs={
                "expr_kind": expr.kind.value,
                "function_fqn": expr.function_fqn,
                **expr.attrs,
            },
        )

    def _create_abstract_node(self, node_id: str) -> UnifiedNode:
        """
        Create a synthetic node for abstract heap elements

        Used for collection analysis where abstract element IDs like
        "var:...:queries@6:4[*]" need to be traversable nodes.

        Args:
            node_id: Abstract node ID (e.g., "var:...[*]")

        Returns:
            UnifiedNode representing the abstract heap location

        RFC-031: Uses canonical NodeKind.VARIABLE, NodeKind.FUNCTION
        """
        # Extract name from node_id
        # Format: var:{repo}:{file}:{fqn}:{name}@{block}:{shadow}[*]
        name = node_id
        if ":" in node_id:
            last_part = node_id.rsplit(":", 1)[-1]
            # Handle [*] suffix
            if "[*]" in last_part:
                name = last_part
            elif "@" in last_part:
                name = last_part.split("@")[0]

        # Determine kind based on ID pattern - RFC-031: Canonical kinds
        if "[*]" in node_id:
            kind = NodeKind.VARIABLE  # Abstract heap element
            name = f"<heap:{name}>"
        elif node_id.startswith("var:"):
            kind = NodeKind.VARIABLE
        elif node_id.startswith("callee:"):
            kind = NodeKind.FUNCTION
        else:
            kind = NodeKind.VARIABLE

        return UnifiedNode(
            id=node_id,
            kind=kind,
            name=name,
            file_path="",  # Abstract nodes don't have file paths
            span=None,
            attrs={"abstract": True, "synthetic": True},
        )
