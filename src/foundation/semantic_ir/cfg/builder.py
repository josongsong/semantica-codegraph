"""
CFG Builder

Builds Control Flow Graph from BFG (Basic Flow Graph).

Responsibility: Add control flow edges to basic blocks
Input: BFG blocks (from BfgBuilder)
Output: CFG with edges
"""

from typing import TYPE_CHECKING

from ..bfg.models import BasicFlowBlock, BasicFlowGraph, BFGBlockKind
from .models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)

if TYPE_CHECKING:
    from ...ir.models import IRDocument
    from ...parsing import SourceFile


# Helper functions
def _generate_cfg_id(function_node_id: str) -> str:
    """Generate CFG ID from function node ID"""
    return f"cfg:{function_node_id}"


# BFG -> CFG kind mapping
BFG_TO_CFG_KIND_MAP = {
    BFGBlockKind.ENTRY: CFGBlockKind.ENTRY,
    BFGBlockKind.EXIT: CFGBlockKind.EXIT,
    BFGBlockKind.STATEMENT: CFGBlockKind.BLOCK,
    BFGBlockKind.CONDITION: CFGBlockKind.CONDITION,
    BFGBlockKind.LOOP_HEADER: CFGBlockKind.LOOP_HEADER,
    BFGBlockKind.TRY: CFGBlockKind.TRY,
    BFGBlockKind.CATCH: CFGBlockKind.CATCH,
    BFGBlockKind.FINALLY: CFGBlockKind.FINALLY,
}


class CfgBuilder:
    """
    Builds CFG (Control Flow Graph) from BFG.

    Responsibility: Control flow edge generation only
    Block segmentation is handled by BfgBuilder
    """

    def __init__(self):
        self._edges: list[ControlFlowEdge] = []

    def build_full(
        self,
        ir_doc: "IRDocument",
        source_map: dict[str, "SourceFile"] | None = None,
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG directly from IRDocument (simplified version).

        This is a placeholder for now - returns empty CFG structures.
        Full implementation would extract BFG blocks from IR and convert to CFG.

        Args:
            ir_doc: IR document
            source_map: Optional source file map

        Returns:
            (cfg_graphs, cfg_blocks, cfg_edges)
        """
        # TODO: Implement full CFG building from IRDocument
        # For now, return empty structures to unblock tests
        return [], [], []

    def build_from_bfg(
        self,
        bfg_graphs: list[BasicFlowGraph],
        bfg_blocks: list[BasicFlowBlock],
        source_map: dict[str, "SourceFile"] | None = None,
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG from BFG blocks.

        Args:
            bfg_graphs: BFG graphs
            bfg_blocks: All BFG blocks
            source_map: Optional source file map (unused for now)

        Returns:
            (cfg_graphs, cfg_blocks, cfg_edges)
        """
        cfg_graphs = []
        all_cfg_blocks = []
        all_cfg_edges = []

        for bfg_graph in bfg_graphs:
            # Build CFG for this function
            cfg_graph, cfg_blocks, cfg_edges = self._build_function_cfg(bfg_graph, bfg_blocks)

            if cfg_graph:
                cfg_graphs.append(cfg_graph)
                all_cfg_blocks.extend(cfg_blocks)
                all_cfg_edges.extend(cfg_edges)

        return cfg_graphs, all_cfg_blocks, all_cfg_edges

    def _build_function_cfg(
        self,
        bfg_graph: BasicFlowGraph,
        _all_bfg_blocks: list[BasicFlowBlock],
    ) -> tuple[ControlFlowGraph | None, list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG for a single function from its BFG.

        Args:
            bfg_graph: BFG graph for this function
            _all_bfg_blocks: All BFG blocks (unused, kept for API consistency)

        Returns:
            (cfg_graph, cfg_blocks, cfg_edges)
        """
        # Reset state
        self._edges = []

        # Get BFG blocks for this function
        func_bfg_blocks = list(bfg_graph.blocks)

        # Convert BFG blocks to CFG blocks
        cfg_blocks = self._convert_blocks(func_bfg_blocks, bfg_graph.function_node_id)

        # Generate control flow edges
        self._generate_edges(cfg_blocks, bfg_graph)

        # Create CFG graph
        cfg_id = _generate_cfg_id(bfg_graph.function_node_id)

        # Find entry/exit blocks in CFG blocks
        entry_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.ENTRY), None)
        exit_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.EXIT), None)

        if not entry_block or not exit_block:
            return None, [], []

        cfg_graph = ControlFlowGraph(
            id=cfg_id,
            function_node_id=bfg_graph.function_node_id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=cfg_blocks.copy(),
            edges=self._edges.copy(),
        )

        return cfg_graph, cfg_blocks.copy(), self._edges.copy()

    def _convert_blocks(self, bfg_blocks: list[BasicFlowBlock], function_node_id: str) -> list[ControlFlowBlock]:
        """
        Convert BFG blocks to CFG blocks.

        Args:
            bfg_blocks: BFG blocks
            function_node_id: Function node ID

        Returns:
            CFG blocks
        """
        cfg_blocks = []

        for bfg_block in bfg_blocks:
            # Map BFG kind to CFG kind
            cfg_kind = BFG_TO_CFG_KIND_MAP.get(bfg_block.kind, CFGBlockKind.BLOCK)

            # Create CFG block with same ID
            cfg_block = ControlFlowBlock(
                id=bfg_block.id,  # Keep same ID for easy mapping
                kind=cfg_kind,
                function_node_id=function_node_id,
                span=bfg_block.span,
            )

            cfg_blocks.append(cfg_block)

        return cfg_blocks

    def _generate_edges(
        self,
        cfg_blocks: list[ControlFlowBlock],
        bfg_graph: BasicFlowGraph,
    ):
        """
        Generate control flow edges based on block kinds and structure.

        Args:
            cfg_blocks: CFG blocks
            bfg_graph: Original BFG graph (for metadata)
        """
        # Get original BFG blocks for metadata
        bfg_blocks_by_id = {b.id: b for b in bfg_graph.blocks}

        # Find entry and exit
        entry_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.ENTRY), None)
        exit_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.EXIT), None)

        if not entry_block or not exit_block:
            return

        # Get body blocks (exclude entry/exit)
        body_blocks = [b for b in cfg_blocks if b.kind not in (CFGBlockKind.ENTRY, CFGBlockKind.EXIT)]

        if not body_blocks:
            # No body blocks, connect entry to exit
            self._create_edge(entry_block.id, exit_block.id, CFGEdgeKind.NORMAL)
            return

        # Connect entry to first body block
        self._create_edge(entry_block.id, body_blocks[0].id, CFGEdgeKind.NORMAL)

        # Process each block and create edges
        for i, block in enumerate(body_blocks):
            bfg_block = bfg_blocks_by_id.get(block.id)
            next_block = body_blocks[i + 1] if i + 1 < len(body_blocks) else exit_block

            if block.kind == CFGBlockKind.CONDITION:
                # Branch block
                self._handle_condition_edges(block, next_block, body_blocks, i, bfg_block)

            elif block.kind == CFGBlockKind.LOOP_HEADER:
                # Loop block
                self._handle_loop_edges(block, next_block, body_blocks, i)

            elif block.kind == CFGBlockKind.TRY:
                # Try block
                self._handle_try_edges(block, next_block, body_blocks, i)

            elif block.kind == CFGBlockKind.CATCH:
                # Catch block - connects to next or finally
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

            elif block.kind == CFGBlockKind.FINALLY:
                # Finally block - connects to next
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

            else:
                # Regular statement block
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

    def _handle_condition_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_blocks: list[ControlFlowBlock],
        current_index: int,
        bfg_block: BasicFlowBlock | None,
    ):
        """
        Handle edges for condition blocks (if/elif/else).

        Args:
            block: Current condition block
            next_block: Next block
            body_blocks: All body blocks
            current_index: Current block index
            bfg_block: Original BFG block (for metadata)
        """
        # True branch: next block
        if current_index + 1 < len(body_blocks):
            true_target = body_blocks[current_index + 1]
            self._create_edge(block.id, true_target.id, CFGEdgeKind.TRUE_BRANCH)

        # False branch
        if bfg_block and bfg_block.ast_has_alternative:
            # Has else/elif - false branch goes to alternative
            # Alternative is typically current_index + 2 or later
            # For now, simplified: false branch goes to merge point
            if current_index + 2 < len(body_blocks):
                false_target = body_blocks[current_index + 2]
                self._create_edge(block.id, false_target.id, CFGEdgeKind.FALSE_BRANCH)
            else:
                # No alternative, false branch to next after then
                self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)
        else:
            # No alternative, false branch skips then block
            # Goes to next after then block
            if current_index + 2 < len(body_blocks):
                false_target = body_blocks[current_index + 2]
                self._create_edge(block.id, false_target.id, CFGEdgeKind.FALSE_BRANCH)
            else:
                self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)

    def _handle_loop_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_blocks: list[ControlFlowBlock],
        current_index: int,
    ):
        """
        Handle edges for loop blocks (for/while).

        Args:
            block: Loop header block
            next_block: Next block after loop
            body_blocks: All body blocks
            current_index: Current block index
        """
        # True branch: enter loop body
        if current_index + 1 < len(body_blocks):
            loop_body = body_blocks[current_index + 1]
            self._create_edge(block.id, loop_body.id, CFGEdgeKind.TRUE_BRANCH)

            # Loop back edge: body -> header
            self._create_edge(loop_body.id, block.id, CFGEdgeKind.LOOP_BACK)

        # False branch: exit loop
        if current_index + 2 < len(body_blocks):
            exit_target = body_blocks[current_index + 2]
            self._create_edge(block.id, exit_target.id, CFGEdgeKind.FALSE_BRANCH)
        else:
            self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)

    def _handle_try_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_blocks: list[ControlFlowBlock],
        current_index: int,
    ):
        """
        Handle edges for try blocks.

        Args:
            block: Try block
            next_block: Next block
            body_blocks: All body blocks
            current_index: Current block index
        """
        # Normal flow: try -> next
        self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

        # Exception flow: try -> catch blocks
        # Look ahead for catch blocks
        for j in range(current_index + 1, len(body_blocks)):
            if body_blocks[j].kind == CFGBlockKind.CATCH:
                self._create_edge(block.id, body_blocks[j].id, CFGEdgeKind.EXCEPTION)
            elif body_blocks[j].kind not in (CFGBlockKind.CATCH, CFGBlockKind.FINALLY):
                # Stop at first non-catch/finally block
                break

    def _create_edge(
        self,
        source_block_id: str,
        target_block_id: str,
        kind: CFGEdgeKind,
    ) -> ControlFlowEdge:
        """
        Create a CFG edge.

        Args:
            source_block_id: Source block ID
            target_block_id: Target block ID
            kind: Edge kind

        Returns:
            Created edge
        """
        edge = ControlFlowEdge(
            source_block_id=source_block_id,
            target_block_id=target_block_id,
            kind=kind,
        )

        self._edges.append(edge)
        return edge
