"""
CFG Builder

Builds Control Flow Graph from BFG (Basic Flow Graph).

Responsibility: Add control flow edges to basic blocks
Input: BFG blocks (from BfgBuilder)
Output: CFG with edges
"""

from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile


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

    def __init__(self, bfg_builder=None):
        """
        Initialize CFG Builder.

        Args:
            bfg_builder: Optional BFG builder for build_full(). If not provided, will create one.
        """
        self._edges: list[ControlFlowEdge] = []
        self._bfg_builder = bfg_builder  # Lazy import to avoid circular dependency

    def build_full(
        self,
        ir_doc: "IRDocument",
        source_map: dict[str, "SourceFile"] | None = None,
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG directly from IRDocument.

        This method first builds BFG (Basic Flow Graph) from IR, then converts to CFG.
        For better performance, prefer using build_from_bfg() if you already have BFG.

        Args:
            ir_doc: IR document
            source_map: Optional source file map

        Returns:
            (cfg_graphs, cfg_blocks, cfg_edges)

        Raises:
            ValueError: If IRDocument is invalid or empty
        """
        # Validate input
        if not ir_doc:
            raise ValueError("IRDocument cannot be None")
        if not ir_doc.nodes:
            # Empty document - return empty structures
            return [], [], []

        # Lazy import to avoid circular dependency
        if self._bfg_builder is None:
            from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder

            self._bfg_builder = BfgBuilder()

        # Step 1: Build BFG from IR
        source_map = source_map or {}
        bfg_graphs, bfg_blocks = self._bfg_builder.build_full(ir_doc, source_map)

        # FIX: HIGH #3 - Validate BFG output and raise on critical corruption
        if not bfg_graphs and bfg_blocks:
            # Critical: BFG builder produced blocks without graphs - data corruption risk
            error_msg = (
                f"BFG builder CRITICAL ERROR: {len(bfg_blocks)} orphaned blocks without graphs. "
                "This indicates BFG builder failure and may cause data loss."
            )
            logger.error(error_msg)
            # Raise to prevent silently processing corrupt data
            raise ValueError(error_msg)

        # Step 2: Convert BFG to CFG
        cfg_graphs, cfg_blocks, cfg_edges = self.build_from_bfg(bfg_graphs, bfg_blocks, source_map)

        # FIX: HIGH #3 - Validate CFG output consistency and raise on critical failure
        if bfg_graphs and not cfg_graphs:
            error_msg = (
                f"CFG conversion CRITICAL ERROR: {len(bfg_graphs)} BFG graphs produced NO CFG graphs. "
                f"Entry/exit block generation may have failed."
            )
            logger.error(error_msg)
            # Raise - this is a critical failure, not partial results
            raise ValueError(error_msg)

        # Validate consistency
        if len(bfg_graphs) != len(cfg_graphs):
            logger.warning(
                f"BFG-CFG count mismatch: {len(bfg_graphs)} BFG graphs -> {len(cfg_graphs)} CFG graphs. "
                "Some functions may have failed CFG conversion."
            )

        return cfg_graphs, cfg_blocks, cfg_edges

    def build_from_bfg(
        self,
        bfg_graphs: list[BasicFlowGraph],
        bfg_blocks: list[BasicFlowBlock],
        source_map: dict[str, tuple["SourceFile", "AstTree"]] | dict[str, "SourceFile"] | None = None,
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG from BFG blocks.

        Args:
            bfg_graphs: BFG graphs
            bfg_blocks: All BFG blocks
            source_map: Optional source file map with pre-parsed AST (unused in CFG, passed for consistency)

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

        # Convert BFG blocks to CFG blocks (returns paired tuples to avoid N+1 lookups)
        cfg_blocks, paired_blocks = self._convert_blocks(func_bfg_blocks, bfg_graph.function_node_id)

        # Generate control flow edges (uses paired blocks to avoid dictionary lookups)
        self._generate_edges(cfg_blocks, paired_blocks)

        # Create CFG graph
        cfg_id = _generate_cfg_id(bfg_graph.function_node_id)

        # Find entry/exit blocks in CFG blocks
        entry_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.ENTRY), None)
        exit_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.EXIT), None)

        # FIX: High #6 - Better error reporting for missing entry/exit blocks
        if not entry_block or not exit_block:
            logger.error(
                f"CFG build failed for function {bfg_graph.function_node_id}: "
                f"Missing {'entry' if not entry_block else 'exit'} block. "
                f"BFG had {len(func_bfg_blocks)} blocks, converted to {len(cfg_blocks)} CFG blocks."
            )
            return None, [], []

        cfg_graph = ControlFlowGraph(
            id=cfg_id,
            function_node_id=bfg_graph.function_node_id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=cfg_blocks,  # No copy needed - immutable after creation
            edges=self._edges,  # No copy needed - immutable after creation
        )

        return cfg_graph, cfg_blocks, self._edges

    def _convert_blocks(
        self, bfg_blocks: list[BasicFlowBlock], function_node_id: str
    ) -> tuple[list[ControlFlowBlock], list[tuple[ControlFlowBlock, BasicFlowBlock]]]:
        """
        Convert BFG blocks to CFG blocks.

        Returns both the CFG blocks and paired (CFG, BFG) tuples to avoid N+1 lookups.

        Args:
            bfg_blocks: BFG blocks
            function_node_id: Function node ID

        Returns:
            (cfg_blocks, paired_blocks)
        """
        cfg_blocks = []
        paired_blocks = []

        for bfg_block in bfg_blocks:
            # Map BFG kind to CFG kind
            cfg_kind = BFG_TO_CFG_KIND_MAP.get(bfg_block.kind, CFGBlockKind.BLOCK)

            # Create CFG block with cfg: prefix (replace bfg: prefix for consistency)
            cfg_block_id = bfg_block.id.replace("bfg:", "cfg:", 1) if bfg_block.id.startswith("bfg:") else bfg_block.id
            cfg_block = ControlFlowBlock(
                id=cfg_block_id,
                kind=cfg_kind,
                function_node_id=function_node_id,
                span=bfg_block.span,
            )

            cfg_blocks.append(cfg_block)
            paired_blocks.append((cfg_block, bfg_block))

        return cfg_blocks, paired_blocks

    def _generate_edges(
        self,
        cfg_blocks: list[ControlFlowBlock],
        paired_blocks: list[tuple[ControlFlowBlock, BasicFlowBlock]],
    ):
        """
        Generate control flow edges based on block kinds and structure.

        Args:
            cfg_blocks: CFG blocks
            paired_blocks: Paired (CFG, BFG) tuples to avoid N+1 lookups
        """
        # Find entry and exit
        entry_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.ENTRY), None)
        exit_block = next((b for b in cfg_blocks if b.kind == CFGBlockKind.EXIT), None)

        if not entry_block or not exit_block:
            return

        # Get body blocks (exclude entry/exit) with their BFG counterparts
        body_pairs = [
            (cfg, bfg) for cfg, bfg in paired_blocks if cfg.kind not in (CFGBlockKind.ENTRY, CFGBlockKind.EXIT)
        ]

        if not body_pairs:
            # No body blocks, connect entry to exit
            self._create_edge(entry_block.id, exit_block.id, CFGEdgeKind.NORMAL)
            return

        # Connect entry to first body block
        self._create_edge(entry_block.id, body_pairs[0][0].id, CFGEdgeKind.NORMAL)

        # Process each block and create edges (no dictionary lookups needed)
        for i, (block, bfg_block) in enumerate(body_pairs):
            next_block = body_pairs[i + 1][0] if i + 1 < len(body_pairs) else exit_block

            if block.kind == CFGBlockKind.CONDITION:
                # Branch block
                self._handle_condition_edges(block, next_block, body_pairs, i, bfg_block)

            elif block.kind == CFGBlockKind.LOOP_HEADER:
                # Loop block
                self._handle_loop_edges(block, next_block, body_pairs, i)

            elif block.kind == CFGBlockKind.TRY:
                # Try block
                self._handle_try_edges(block, next_block, body_pairs, i)

            elif block.kind == CFGBlockKind.CATCH:
                # Catch block - connects to next or finally
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

            elif block.kind == CFGBlockKind.FINALLY:
                # Finally block - connects to next
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

            else:
                # Regular statement or control flow statement (break/continue/return)
                # Delegate to dedicated handler (Added 2025-11-25, refactored for complexity)
                self._handle_control_flow_statement(block, bfg_block, body_pairs, i, next_block, exit_block)

    def _handle_condition_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
        bfg_block: BasicFlowBlock | None,
    ):
        """
        Handle edges for condition blocks (if/elif/else).

        Args:
            block: Current condition block
            next_block: Next block
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index
            bfg_block: Original BFG block (for metadata)
        """
        # True branch: next block
        if current_index + 1 < len(body_pairs):
            true_target = body_pairs[current_index + 1][0]
            self._create_edge(block.id, true_target.id, CFGEdgeKind.TRUE_BRANCH)

        # False branch
        if bfg_block and bfg_block.ast_has_alternative:
            # Has else/elif - false branch goes to alternative
            # Alternative is typically current_index + 2 or later
            # For now, simplified: false branch goes to merge point
            if current_index + 2 < len(body_pairs):
                false_target = body_pairs[current_index + 2][0]
                self._create_edge(block.id, false_target.id, CFGEdgeKind.FALSE_BRANCH)
            else:
                # No alternative, false branch to next after then
                self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)
        else:
            # No alternative, false branch skips then block
            # Goes to next after then block
            if current_index + 2 < len(body_pairs):
                false_target = body_pairs[current_index + 2][0]
                self._create_edge(block.id, false_target.id, CFGEdgeKind.FALSE_BRANCH)
            else:
                self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)

    def _handle_loop_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
    ):
        """
        Handle edges for loop blocks (for/while).

        Args:
            block: Loop header block
            next_block: Next block after loop
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index
        """
        # True branch: enter loop body
        if current_index + 1 < len(body_pairs):
            loop_body_cfg, loop_body_bfg = body_pairs[current_index + 1]
            self._create_edge(block.id, loop_body_cfg.id, CFGEdgeKind.TRUE_BRANCH)

            # Loop back edge: body -> header (only if body doesn't have control flow statements)
            # Updated 2025-11-25: Skip LOOP_BACK if body has break/continue/return
            if not (loop_body_bfg.is_break or loop_body_bfg.is_continue or loop_body_bfg.is_return):
                self._create_edge(loop_body_cfg.id, block.id, CFGEdgeKind.LOOP_BACK)

        # False branch: exit loop
        if current_index + 2 < len(body_pairs):
            exit_target = body_pairs[current_index + 2][0]
            self._create_edge(block.id, exit_target.id, CFGEdgeKind.FALSE_BRANCH)
        else:
            self._create_edge(block.id, next_block.id, CFGEdgeKind.FALSE_BRANCH)

    def _handle_control_flow_statement(
        self,
        block: ControlFlowBlock,
        bfg_block: BasicFlowBlock,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
        next_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
    ):
        """
        Handle break/continue/return control flow statements.

        This method handles special control flow statements that alter normal
        sequential execution flow. Break/continue statements jump to specific
        loop locations, while return statements exit the function.

        Args:
            block: Current CFG block
            bfg_block: Corresponding BFG block with metadata
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index
            next_block: Next sequential block
            exit_block: Function exit block

        Added: 2025-11-25 (refactored from _generate_edges for complexity reduction)
        """
        if bfg_block.is_break:
            # Break - find loop exit block
            loop_exit = self._find_loop_exit_block(bfg_block.target_loop_id, body_pairs, current_index)
            if loop_exit:
                self._create_edge(block.id, loop_exit.id, CFGEdgeKind.BREAK)
            else:
                # Fallback: break without target goes to function exit
                self._create_edge(block.id, exit_block.id, CFGEdgeKind.BREAK)

        elif bfg_block.is_continue:
            # Continue - jump to loop header
            loop_header = self._find_loop_header_block(bfg_block.target_loop_id, body_pairs)
            if loop_header:
                self._create_edge(block.id, loop_header.id, CFGEdgeKind.CONTINUE)
            else:
                # Fallback: continue without target goes to next block (shouldn't happen)
                self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

        elif bfg_block.is_return:
            # Return - jump to function exit
            self._create_edge(block.id, exit_block.id, CFGEdgeKind.RETURN)

        else:
            # Regular statement block - normal sequential flow
            self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

    def _handle_try_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
    ):
        """
        Handle edges for try blocks.

        Args:
            block: Try block
            next_block: Next block
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index
        """
        # Normal flow: try -> next
        self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

        # Exception flow: try -> catch blocks
        # Look ahead for catch blocks
        for j in range(current_index + 1, len(body_pairs)):
            if body_pairs[j][0].kind == CFGBlockKind.CATCH:
                self._create_edge(block.id, body_pairs[j][0].id, CFGEdgeKind.EXCEPTION)
            elif body_pairs[j][0].kind not in (CFGBlockKind.CATCH, CFGBlockKind.FINALLY):
                # Stop at first non-catch/finally block
                break

    def _find_loop_header_block(
        self,
        target_loop_id: str | None,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
    ) -> ControlFlowBlock | None:
        """
        Find loop header block by BFG block ID.

        Args:
            target_loop_id: BFG loop header block ID
            body_pairs: All body (CFG, BFG) pairs

        Returns:
            CFG loop header block or None
        """
        if not target_loop_id:
            return None

        for cfg_block, bfg_block in body_pairs:
            if bfg_block.id == target_loop_id and cfg_block.kind == CFGBlockKind.LOOP_HEADER:
                return cfg_block

        return None

    def _find_loop_exit_block(
        self,
        target_loop_id: str | None,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
    ) -> ControlFlowBlock | None:
        """
        Find loop exit block (block after loop body).

        Args:
            target_loop_id: BFG loop header block ID
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index (break statement location)

        Returns:
            CFG block after loop or None
        """
        if not target_loop_id:
            return None

        # Find loop header index
        loop_header_index = None
        for i, (_, bfg_block) in enumerate(body_pairs):
            if bfg_block.id == target_loop_id:
                loop_header_index = i
                break

        if loop_header_index is None:
            return None

        # Find loop exit: first block after loop body
        # Simple heuristic: look for first block after current that is not in loop
        # For now: next block after loop header + 1 (loop body is at header + 1)
        # More accurate: find block after all loop body blocks
        # Simplified: use next block after loop header's expected body
        loop_exit_index = loop_header_index + 2  # header, body, then exit

        if loop_exit_index < len(body_pairs):
            return body_pairs[loop_exit_index][0]

        # If no block after loop, break goes to function exit (handled by fallback in caller)
        return None

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

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.

        Note: CFG builder does not use caching (builds directly from BFG).
        This method exists for API consistency with other builders.

        Returns:
            Empty dict indicating no caching
        """
        return {"note": "CFG builder does not use caching"}
