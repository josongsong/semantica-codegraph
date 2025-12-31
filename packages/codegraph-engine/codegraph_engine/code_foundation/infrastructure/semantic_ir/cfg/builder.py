"""
CFG Builder

Builds Control Flow Graph from BFG (Basic Flow Graph).

Responsibility: Add control flow edges to basic blocks
Input: BFG blocks (from BfgBuilder)
Output: CFG with edges
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.config import _DEBUG_ENABLED

logger = get_logger(__name__)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
    from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile


# Helper functions
def _generate_cfg_id(function_node_id: str) -> str:
    """Generate CFG ID from function node ID"""
    return f"cfg:{function_node_id}"


@dataclass
class EdgeGenerationContext:
    """
    Context for edge generation during CFG building.

    Passed to edge handlers to avoid parameter explosion.
    """

    current_index: int
    next_block: ControlFlowBlock
    body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]]
    exit_block: ControlFlowBlock
    try_context_map: dict[int, list[int]]
    bfg_block: BasicFlowBlock


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
    # Async/await support (Added 2025-12-08)
    BFGBlockKind.SUSPEND: CFGBlockKind.SUSPEND,
    BFGBlockKind.RESUME: CFGBlockKind.RESUME,
    # Generator support (Added 2025-12-09 - Phase 2)
    BFGBlockKind.DISPATCHER: CFGBlockKind.DISPATCHER,
    BFGBlockKind.YIELD: CFGBlockKind.BLOCK,  # YIELD → Block
    BFGBlockKind.RESUME_YIELD: CFGBlockKind.BLOCK,  # RESUME → Block
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
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder

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

            # CRITICAL (Phase 2): Copy generator metadata from BFG to CFG
            # SSA needs generator_all_locals to build variable definitions
            if hasattr(bfg_block, "generator_all_locals") and bfg_block.generator_all_locals:
                cfg_block.generator_all_locals = bfg_block.generator_all_locals

            if hasattr(bfg_block, "generator_dispatch_table") and bfg_block.generator_dispatch_table:
                cfg_block.generator_dispatch_table = bfg_block.generator_dispatch_table

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

        # Build try context map (Added 2025-12-08 for Exception Hell)
        # Maps block index -> list of CATCH block indices
        try_context_map = self._build_try_context_map(body_pairs)

        # Process each block and create edges (Dictionary dispatch pattern)
        for i, (block, bfg_block) in enumerate(body_pairs):
            next_block = body_pairs[i + 1][0] if i + 1 < len(body_pairs) else exit_block

            # Create context for edge handlers
            context = EdgeGenerationContext(
                current_index=i,
                next_block=next_block,
                body_pairs=body_pairs,
                exit_block=exit_block,
                try_context_map=try_context_map,
                bfg_block=bfg_block,
            )

            # Dispatch to appropriate edge handler (no if-elif chain!)
            self._dispatch_edge_handler(block, context)

            # RFC-036: Optimized exception edges
            # Only add for blocks that can actually throw (calls, operations)
            # Skip simple blocks (assignment, return, etc.)
            if i in try_context_map and block.kind not in (CFGBlockKind.TRY, CFGBlockKind.CATCH, CFGBlockKind.FINALLY):
                # Check if block can throw based on block kind
                # BLOCK and CONDITION blocks can potentially throw exceptions
                can_throw = block.kind in (CFGBlockKind.BLOCK, CFGBlockKind.CONDITION)

                if can_throw:
                    catch_indices = try_context_map[i]
                    for catch_idx in catch_indices:
                        catch_block = body_pairs[catch_idx][0]
                        self._create_edge(block.id, catch_block.id, CFGEdgeKind.EXCEPTION)
                        if _DEBUG_ENABLED:
                            logger.debug(f"Exception edge: {block.kind.value} (idx {i}) -> CATCH (idx {catch_idx})")

    def _dispatch_edge_handler(
        self,
        block: ControlFlowBlock,
        context: EdgeGenerationContext,
    ):
        """
        Dispatch to appropriate edge handler based on block kind.

        Uses dictionary dispatch pattern instead of if-elif chain.

        Args:
            block: CFG block to process
            context: Edge generation context

        Added: 2025-12-08 (Refactoring: removed if-elif hell)
        """
        # Dictionary dispatch: block kind -> handler method
        # This is O(1) lookup vs O(N) if-elif chain
        edge_handlers = {
            CFGBlockKind.CONDITION: self._edge_handler_condition,
            CFGBlockKind.LOOP_HEADER: self._edge_handler_loop,
            CFGBlockKind.TRY: self._edge_handler_try,
            CFGBlockKind.CATCH: self._edge_handler_catch,
            CFGBlockKind.FINALLY: self._edge_handler_finally,
            CFGBlockKind.SUSPEND: self._edge_handler_suspend,
            CFGBlockKind.RESUME: self._edge_handler_resume,
            # Generator support (Added 2025-12-09 - Phase 1)
            "Dispatcher": self._edge_handler_dispatcher,  # String key for BFGBlockKind.DISPATCHER
        }

        # Get handler for this block kind (default: regular statement)
        handler = edge_handlers.get(block.kind, self._edge_handler_default)
        handler(block, context)

    # Edge handlers (one per block kind)

    def _edge_handler_condition(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle CONDITION block edges"""
        self._handle_condition_edges(block, ctx.next_block, ctx.body_pairs, ctx.current_index, ctx.bfg_block)

    def _edge_handler_loop(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle LOOP_HEADER block edges"""
        self._handle_loop_edges(block, ctx.next_block, ctx.body_pairs, ctx.current_index)

    def _edge_handler_try(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle TRY block edges"""
        self._handle_try_edges(block, ctx.next_block, ctx.body_pairs, ctx.current_index)

    def _edge_handler_catch(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle CATCH block edges"""
        self._create_edge(block.id, ctx.next_block.id, CFGEdgeKind.NORMAL)

    def _edge_handler_finally(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle FINALLY block edges"""
        self._create_edge(block.id, ctx.next_block.id, CFGEdgeKind.NORMAL)

    def _edge_handler_suspend(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle SUSPEND block edges (async/await)"""
        self._handle_suspend_edges(block, ctx.next_block, ctx.body_pairs, ctx.current_index, ctx.bfg_block)

    def _edge_handler_resume(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle RESUME block edges (async/await)"""
        self._create_edge(block.id, ctx.next_block.id, CFGEdgeKind.NORMAL)

    def _edge_handler_dispatcher(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """
        Handle DISPATCHER block edges (generator state machine)

        DISPATCHER creates conditional edges to each state:
        - State 0 → first STATE block (code before first yield)
        - State 1+ → RESUME blocks (code after yield N)

        Metadata required in BFG block:
            generator_dispatch_table: {0: "state_0", 1: "state_1", ...}

        CFG Edge: DISPATCHER → State blocks (conditional)

        Updated: 2025-12-09 (Phase 1.1 - with actual STATE blocks)
        """
        # Get dispatch table from BFG metadata
        dispatch_table = ctx.bfg_block.generator_dispatch_table if ctx.bfg_block else None

        if not dispatch_table:
            # No dispatch table - error in generator lowering
            logger.warning(f"DISPATCHER block {block.id} has no generator_dispatch_table. Skipping edge generation.")
            return

        # Create conditional edges to each state
        # Phase 1.1: Find actual STATE/RESUME blocks by ID pattern
        for state_id, _target_block_id in dispatch_table.items():
            # Find matching block in body_pairs
            # Pattern: "bfg:func:state:0", "bfg:func:resume:1", etc.

            if state_id == 0:
                # State 0 → STATE block with id ending in ":state:0"
                for cfg_block, bfg_block in ctx.body_pairs:
                    if bfg_block.id.endswith(f":state:{state_id}"):
                        self._create_edge(block.id, cfg_block.id, CFGEdgeKind.NORMAL)
                        if _DEBUG_ENABLED:
                            logger.debug(f"DISPATCHER → State {state_id}: {block.id} → {cfg_block.id}")
                        break
            else:
                # State N → RESUME block with matching state_id
                for cfg_block, bfg_block in ctx.body_pairs:
                    if bfg_block.kind.value == "ResumeYield" and bfg_block.generator_resume_from_state == state_id - 1:
                        self._create_edge(block.id, cfg_block.id, CFGEdgeKind.NORMAL)
                        if _DEBUG_ENABLED:
                            logger.debug(f"DISPATCHER → State {state_id} (resume): {block.id} → {cfg_block.id}")
                        break

        if _DEBUG_ENABLED:
            logger.debug(f"DISPATCHER {block.id}: created {len(dispatch_table)} state edges")

    def _edge_handler_default(self, block: ControlFlowBlock, ctx: EdgeGenerationContext):
        """Handle regular statement blocks (default handler)"""
        self._handle_control_flow_statement(
            block, ctx.bfg_block, ctx.body_pairs, ctx.current_index, ctx.next_block, ctx.exit_block
        )

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

    def _handle_suspend_edges(
        self,
        block: ControlFlowBlock,
        next_block: ControlFlowBlock,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
        current_index: int,
        bfg_block: BasicFlowBlock,
    ):
        """
        Handle edges for SUSPEND blocks (async/await).

        Structure:
        ```
        [ SUSPEND Block ]
            │      ↘ (Exception edge to catch/exit)
            │       [ CATCH Block (if in try) ]
            ↓ (Success)
        [ RESUME Block ]
        ```

        Args:
            block: Suspend block
            next_block: Next block (should be RESUME)
            body_pairs: All body (CFG, BFG) pairs
            current_index: Current block index
            bfg_block: Original BFG block (for metadata)

        Added: 2025-12-08 (SOTA async/await support)
        """
        # Normal flow (success): suspend -> resume (next block)
        if next_block.kind == CFGBlockKind.RESUME:
            self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)
        else:
            # Unexpected: SUSPEND not followed by RESUME
            # Fallback to normal edge
            logger.warning(
                f"SUSPEND block {block.id} not followed by RESUME block. "
                f"Next block kind: {next_block.kind}. Creating fallback NORMAL edge."
            )
            self._create_edge(block.id, next_block.id, CFGEdgeKind.NORMAL)

        # Exception flow (rejection): suspend -> catch blocks (if any)
        # Look backwards to find enclosing try block's catch handlers
        if bfg_block.can_throw_exception:
            catch_blocks = self._find_enclosing_catch_blocks(current_index, body_pairs)
            for catch_block in catch_blocks:
                self._create_edge(block.id, catch_block.id, CFGEdgeKind.EXCEPTION)

            # Log exception edges
            if catch_blocks:
                if _DEBUG_ENABLED:
                    logger.debug(f"SUSPEND block {block.id} has {len(catch_blocks)} exception edges to catch handlers")

    def _find_enclosing_catch_blocks(
        self,
        current_index: int,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
    ) -> list[ControlFlowBlock]:
        """
        Find enclosing try block's catch handlers.

        Looks backwards from current position to find the most recent TRY block,
        then looks forward from that TRY to find associated CATCH blocks.

        Args:
            current_index: Current block index (SUSPEND location)
            body_pairs: All body (CFG, BFG) pairs

        Returns:
            List of CATCH blocks (empty if not in try)

        Added: 2025-12-08
        """
        # Find most recent TRY block before current position
        try_index = None
        for i in range(current_index - 1, -1, -1):
            if body_pairs[i][0].kind == CFGBlockKind.TRY:
                try_index = i
                break

        if try_index is None:
            # Not in try block - no exception handlers
            if _DEBUG_ENABLED:
                logger.debug(f"SUSPEND at index {current_index} not in try block (no TRY found before it)")
            return []

        # Find CATCH blocks after the SUSPEND block (not after TRY)
        # The structure is: TRY → [body statements (incl. SUSPEND)] → CATCH
        catch_blocks = []

        # Start searching from current position onwards for CATCH blocks
        for j in range(current_index + 1, len(body_pairs)):
            cfg_block, bfg_block = body_pairs[j]

            if cfg_block.kind == CFGBlockKind.CATCH:
                catch_blocks.append(cfg_block)
                if _DEBUG_ENABLED:
                    logger.debug(f"Found CATCH block at index {j} for SUSPEND at index {current_index}")
            elif cfg_block.kind == CFGBlockKind.FINALLY:
                # Skip FINALLY (doesn't catch exceptions, just runs after)
                continue
            elif cfg_block.kind in (CFGBlockKind.TRY, CFGBlockKind.ENTRY, CFGBlockKind.EXIT):
                # Reached a new scope - stop searching
                break

        if not catch_blocks:
            if _DEBUG_ENABLED:
                logger.debug(f"No CATCH blocks found for SUSPEND at index {current_index} (try_index: {try_index})")

        return catch_blocks

    def _build_try_context_map(
        self,
        body_pairs: list[tuple[ControlFlowBlock, BasicFlowBlock]],
    ) -> dict[int, list[int]]:
        """
        Build map of try contexts for exception edge generation.

        For each block index, maps to list of CATCH block indices that can handle
        exceptions from that block.

        This enables O(1) lookup during edge generation instead of O(N) search.

        Args:
            body_pairs: All body (CFG, BFG) pairs

        Returns:
            Dict mapping block_index -> [catch_block_indices]

        Added: 2025-12-08 (Exception Hell fix)
        """
        context_map: dict[int, list[int]] = {}
        try_stack: list[tuple[int, list[int]]] = []  # Stack of (try_index, [catch_indices])

        for i, (cfg_block, _bfg_block) in enumerate(body_pairs):
            if cfg_block.kind == CFGBlockKind.TRY:
                # Start of try block - find associated catch blocks
                # Need to skip all blocks inside try body and find CATCH blocks
                catch_indices = []
                in_try_body = True

                for j in range(i + 1, len(body_pairs)):
                    j_kind = body_pairs[j][0].kind

                    if j_kind == CFGBlockKind.CATCH:
                        catch_indices.append(j)
                        in_try_body = False  # Now in exception handler section
                    elif j_kind == CFGBlockKind.FINALLY:
                        # FINALLY doesn't catch, just continues
                        in_try_body = False
                    elif j_kind == CFGBlockKind.TRY:
                        # New try block - stop searching
                        break
                    elif not in_try_body:
                        # We've passed all catch/finally blocks
                        break

                # Push try context onto stack
                try_stack.append((i, catch_indices))

            elif cfg_block.kind == CFGBlockKind.CATCH:
                # End of try scope - pop stack
                # Note: Multiple catches for same try, so only pop when we've seen all
                # Simple heuristic: pop when next block is not CATCH or FINALLY
                if i + 1 < len(body_pairs):
                    next_kind = body_pairs[i + 1][0].kind
                    if next_kind not in (CFGBlockKind.CATCH, CFGBlockKind.FINALLY):
                        if try_stack:
                            try_stack.pop()
                else:
                    # Last block - pop
                    if try_stack:
                        try_stack.pop()

            else:
                # Regular block - inherit try context from stack
                if try_stack:
                    # Get catch handlers from all enclosing try blocks (for nested try)
                    all_catches = []
                    for _try_idx, catch_idxs in try_stack:
                        all_catches.extend(catch_idxs)
                    context_map[i] = all_catches

        return context_map

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
