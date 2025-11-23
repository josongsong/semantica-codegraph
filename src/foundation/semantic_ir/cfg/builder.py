"""
CFG IR Builder

Builds Control Flow Graph from Structural IR.

Strategy:
- Function 단위로 CFG 생성
- Basic block segmentation (branch, loop 기준)
- Entry/Exit block 추가
- Control flow edge 생성 (fallthrough, branch, loop_back, handler)
"""

from typing import Optional

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ...ir.models import IRDocument, Node, NodeKind, Span
from ...parsing import AstTree, SourceFile
from .models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)


# Helper functions (to avoid circular import)
def _generate_cfg_id(function_node_id: str) -> str:
    """Generate CFG ID from function node ID"""
    return f"cfg:{function_node_id}"


def _generate_cfg_block_id(cfg_id: str, block_index: int) -> str:
    """Generate CFG block ID"""
    return f"{cfg_id}:block:{block_index}"

# Python branch/loop types
PYTHON_BRANCH_TYPES = {
    "if_statement",
    "elif_clause",
    "else_clause",
    "match_statement",
    "case_clause",
}

PYTHON_LOOP_TYPES = {
    "for_statement",
    "while_statement",
}

PYTHON_TRY_TYPES = {
    "try_statement",
    "except_clause",
    "finally_clause",
}


class CfgIrBuilder:
    """
    Builds CFG (Control Flow Graph) from structural IR.

    Phase 2: Function-level CFG only
    Phase 3: + Data flow analysis
    """

    def __init__(self):
        self._block_counter = 0
        self._blocks: list[ControlFlowBlock] = []
        self._edges: list[ControlFlowEdge] = []

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, SourceFile]
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG for all functions in IR document.

        Args:
            ir_doc: Structural IR document
            source_map: file_path -> SourceFile (for AST access)

        Returns:
            (cfg_graphs, all_blocks, all_edges)
        """
        cfg_graphs = []
        all_blocks = []
        all_edges = []

        # Find all functions/methods
        func_nodes = [
            n
            for n in ir_doc.nodes
            if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD)
        ]

        for func_node in func_nodes:
            # Build CFG for this function
            cfg_graph, blocks, edges = self._build_function_cfg(
                func_node, ir_doc, source_map
            )

            if cfg_graph:
                cfg_graphs.append(cfg_graph)
                all_blocks.extend(blocks)
                all_edges.extend(edges)

        return cfg_graphs, all_blocks, all_edges

    def _build_function_cfg(
        self,
        func_node: Node,
        ir_doc: IRDocument,
        source_map: dict[str, SourceFile],
    ) -> tuple[Optional[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Build CFG for a single function.

        Args:
            func_node: Function/Method node
            ir_doc: IR document
            source_map: Source file map

        Returns:
            (cfg_graph, blocks, edges) or (None, [], [])
        """
        # Reset state
        self._block_counter = 0
        self._blocks = []
        self._edges = []

        # Generate CFG ID
        cfg_id = _generate_cfg_id(func_node.id)

        # Get source file
        source = source_map.get(func_node.file_path)

        # Create Entry block
        entry_block = self._create_block(
            cfg_id=cfg_id,
            function_node_id=func_node.id,
            kind=CFGBlockKind.ENTRY,
            span=Span(func_node.span.start_line, 0, func_node.span.start_line, 0),
        )

        # Create Exit block
        exit_block = self._create_block(
            cfg_id=cfg_id,
            function_node_id=func_node.id,
            kind=CFGBlockKind.EXIT,
            span=Span(func_node.span.end_line, 0, func_node.span.end_line, 0),
        )

        # Build body blocks
        if source:
            # Enhanced CFG with AST-based analysis
            body_blocks = self._build_body_blocks(
                cfg_id, func_node, source, entry_block, exit_block
            )
        else:
            # Simplified CFG: single body block
            body_block = self._create_block(
                cfg_id=cfg_id,
                function_node_id=func_node.id,
                kind=CFGBlockKind.BLOCK,
                span=func_node.body_span or func_node.span,
            )
            self._create_edge(entry_block.id, body_block.id, CFGEdgeKind.NORMAL)
            self._create_edge(body_block.id, exit_block.id, CFGEdgeKind.NORMAL)

        # Build CFG graph
        cfg_graph = ControlFlowGraph(
            id=cfg_id,
            function_node_id=func_node.id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=self._blocks.copy(),
            edges=self._edges.copy(),
        )

        return cfg_graph, self._blocks.copy(), self._edges.copy()

    def _build_body_blocks(
        self,
        cfg_id: str,
        func_node: Node,
        source: SourceFile,
        entry_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
    ) -> list[ControlFlowBlock]:
        """
        Build detailed CFG blocks by analyzing function body AST.

        Args:
            cfg_id: CFG ID
            func_node: Function node
            source: Source file
            entry_block: Entry block
            exit_block: Exit block

        Returns:
            List of body blocks created
        """
        from ...parsing import AstTree

        # Parse AST
        ast = AstTree.parse(source)

        # Find function definition node in AST
        func_ast_node = self._find_function_node(ast, func_node)
        if not func_ast_node:
            # Fallback to simple body block
            body_block = self._create_block(
                cfg_id=cfg_id,
                function_node_id=func_node.id,
                kind=CFGBlockKind.BLOCK,
                span=func_node.body_span or func_node.span,
            )
            self._create_edge(entry_block.id, body_block.id, CFGEdgeKind.NORMAL)
            self._create_edge(body_block.id, exit_block.id, CFGEdgeKind.NORMAL)
            return [body_block]

        # Get function body
        body_node = func_ast_node.child_by_field_name("body")
        if not body_node:
            # No body, connect entry to exit
            self._create_edge(entry_block.id, exit_block.id, CFGEdgeKind.NORMAL)
            return []

        # Build CFG from body statements
        body_blocks = self._build_statement_blocks(
            cfg_id, func_node.id, body_node, entry_block, exit_block, ast
        )

        return body_blocks

    def _find_function_node(self, ast: "AstTree", func_node: Node) -> Optional[TSNode]:
        """
        Find the Tree-sitter function node matching the IR function node.

        Args:
            ast: AST tree
            func_node: IR function node

        Returns:
            Tree-sitter function node or None
        """
        # Find function/method definitions at the target line
        target_line = func_node.span.start_line

        # Search for function_definition or decorated_definition
        func_defs = ast.find_by_type("function_definition")
        func_defs.extend(ast.find_by_type("decorated_definition"))

        for node in func_defs:
            span = ast.get_span(node)
            if span.start_line == target_line:
                # If decorated, get the actual function
                if node.type == "decorated_definition":
                    definition = node.child_by_field_name("definition")
                    if definition and definition.type == "function_definition":
                        return definition
                return node

        return None

    def _build_statement_blocks(
        self,
        cfg_id: str,
        function_node_id: str,
        body_node: TSNode,
        entry_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
        ast: "AstTree",
    ) -> list[ControlFlowBlock]:
        """
        Build CFG blocks from statement list.

        Args:
            cfg_id: CFG ID
            function_node_id: Function node ID
            body_node: AST body node (block or suite)
            entry_block: Entry block
            exit_block: Exit block
            ast: AST tree

        Returns:
            List of blocks created
        """
        # Get statements from body
        statements = []
        if body_node.type == "block":
            statements = [child for child in body_node.children if child.is_named]
        else:
            statements = [body_node]

        if not statements:
            # Empty body
            self._create_edge(entry_block.id, exit_block.id, CFGEdgeKind.NORMAL)
            return []

        # Build blocks for each statement
        blocks = []
        prev_block = entry_block

        for stmt in statements:
            if stmt.type in PYTHON_BRANCH_TYPES:
                # Branch statement (if/elif/else)
                branch_blocks = self._build_branch_blocks(
                    cfg_id, function_node_id, stmt, prev_block, exit_block, ast
                )
                blocks.extend(branch_blocks)
                # Update prev_block to last branch block
                if branch_blocks:
                    prev_block = branch_blocks[-1]

            elif stmt.type in PYTHON_LOOP_TYPES:
                # Loop statement (for/while)
                loop_blocks = self._build_loop_blocks(
                    cfg_id, function_node_id, stmt, prev_block, exit_block, ast
                )
                blocks.extend(loop_blocks)
                if loop_blocks:
                    prev_block = loop_blocks[-1]

            elif stmt.type in PYTHON_TRY_TYPES:
                # Try/except/finally
                try_blocks = self._build_try_blocks(
                    cfg_id, function_node_id, stmt, prev_block, exit_block, ast
                )
                blocks.extend(try_blocks)
                if try_blocks:
                    prev_block = try_blocks[-1]

            else:
                # Regular statement - create a basic block
                stmt_block = self._create_block(
                    cfg_id=cfg_id,
                    function_node_id=function_node_id,
                    kind=CFGBlockKind.BLOCK,
                    span=ast.get_span(stmt),
                )
                self._create_edge(prev_block.id, stmt_block.id, CFGEdgeKind.NORMAL)
                blocks.append(stmt_block)
                prev_block = stmt_block

        # Connect last block to exit
        if prev_block != entry_block:
            self._create_edge(prev_block.id, exit_block.id, CFGEdgeKind.NORMAL)
        else:
            # No blocks created, connect entry to exit
            self._create_edge(entry_block.id, exit_block.id, CFGEdgeKind.NORMAL)

        return blocks

    def _build_branch_blocks(
        self,
        cfg_id: str,
        function_node_id: str,
        branch_node: TSNode,
        prev_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
        ast: "AstTree",
    ) -> list[ControlFlowBlock]:
        """
        Build CFG blocks for branch statements (if/elif/else).

        Args:
            cfg_id: CFG ID
            function_node_id: Function node ID
            branch_node: AST branch node
            prev_block: Previous block
            exit_block: Exit block
            ast: AST tree

        Returns:
            List of blocks created
        """
        blocks = []

        # Create condition block
        condition_block = self._create_block(
            cfg_id=cfg_id,
            function_node_id=function_node_id,
            kind=CFGBlockKind.CONDITION,
            span=ast.get_span(branch_node),
        )
        blocks.append(condition_block)

        # Connect previous block to condition
        self._create_edge(prev_block.id, condition_block.id, CFGEdgeKind.NORMAL)

        # Get consequence (then branch)
        consequence = branch_node.child_by_field_name("consequence")
        if consequence:
            then_block = self._create_block(
                cfg_id=cfg_id,
                function_node_id=function_node_id,
                kind=CFGBlockKind.BLOCK,
                span=ast.get_span(consequence),
            )
            blocks.append(then_block)
            self._create_edge(
                condition_block.id, then_block.id, CFGEdgeKind.TRUE_BRANCH
            )
            # Then block eventually goes to merge point (handled by caller)
        else:
            # No then block, true branch goes to merge
            pass

        # Get alternative (else/elif branch)
        alternative = branch_node.child_by_field_name("alternative")
        if alternative:
            else_block = self._create_block(
                cfg_id=cfg_id,
                function_node_id=function_node_id,
                kind=CFGBlockKind.BLOCK,
                span=ast.get_span(alternative),
            )
            blocks.append(else_block)
            self._create_edge(
                condition_block.id, else_block.id, CFGEdgeKind.FALSE_BRANCH
            )
        else:
            # No else branch, false branch goes to merge point
            pass

        return blocks

    def _build_loop_blocks(
        self,
        cfg_id: str,
        function_node_id: str,
        loop_node: TSNode,
        prev_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
        ast: "AstTree",
    ) -> list[ControlFlowBlock]:
        """
        Build CFG blocks for loop statements (for/while).

        Args:
            cfg_id: CFG ID
            function_node_id: Function node ID
            loop_node: AST loop node
            prev_block: Previous block
            exit_block: Exit block
            ast: AST tree

        Returns:
            List of blocks created
        """
        blocks = []

        # Create loop header block
        loop_header = self._create_block(
            cfg_id=cfg_id,
            function_node_id=function_node_id,
            kind=CFGBlockKind.LOOP_HEADER,
            span=ast.get_span(loop_node),
        )
        blocks.append(loop_header)

        # Connect previous block to loop header
        self._create_edge(prev_block.id, loop_header.id, CFGEdgeKind.NORMAL)

        # Get loop body
        body = loop_node.child_by_field_name("body")
        if body:
            loop_body = self._create_block(
                cfg_id=cfg_id,
                function_node_id=function_node_id,
                kind=CFGBlockKind.BLOCK,
                span=ast.get_span(body),
            )
            blocks.append(loop_body)

            # Loop header -> body (true branch)
            self._create_edge(
                loop_header.id, loop_body.id, CFGEdgeKind.TRUE_BRANCH
            )

            # Body -> loop header (loop back)
            self._create_edge(loop_body.id, loop_header.id, CFGEdgeKind.LOOP_BACK)

        # Loop header -> next (false branch, loop exit)
        # This will be connected by the caller

        return blocks

    def _build_try_blocks(
        self,
        cfg_id: str,
        function_node_id: str,
        try_node: TSNode,
        prev_block: ControlFlowBlock,
        exit_block: ControlFlowBlock,
        ast: "AstTree",
    ) -> list[ControlFlowBlock]:
        """
        Build CFG blocks for try/except/finally statements.

        Args:
            cfg_id: CFG ID
            function_node_id: Function node ID
            try_node: AST try node
            prev_block: Previous block
            exit_block: Exit block
            ast: AST tree

        Returns:
            List of blocks created
        """
        blocks = []

        # Create try block
        body = try_node.child_by_field_name("body")
        if body:
            try_block = self._create_block(
                cfg_id=cfg_id,
                function_node_id=function_node_id,
                kind=CFGBlockKind.TRY,
                span=ast.get_span(body),
            )
            blocks.append(try_block)
            self._create_edge(prev_block.id, try_block.id, CFGEdgeKind.NORMAL)

            # Find except clauses
            for child in try_node.children:
                if child.type == "except_clause":
                    except_block = self._create_block(
                        cfg_id=cfg_id,
                        function_node_id=function_node_id,
                        kind=CFGBlockKind.CATCH,
                        span=ast.get_span(child),
                    )
                    blocks.append(except_block)
                    # Exception edge from try to except
                    self._create_edge(
                        try_block.id, except_block.id, CFGEdgeKind.EXCEPTION
                    )

                elif child.type == "finally_clause":
                    finally_block = self._create_block(
                        cfg_id=cfg_id,
                        function_node_id=function_node_id,
                        kind=CFGBlockKind.FINALLY,
                        span=ast.get_span(child),
                    )
                    blocks.append(finally_block)
                    # Finally is always executed
                    self._create_edge(
                        try_block.id, finally_block.id, CFGEdgeKind.NORMAL
                    )

        return blocks

    def _create_block(
        self,
        cfg_id: str,
        function_node_id: str,
        kind: CFGBlockKind,
        span: Span,
    ) -> ControlFlowBlock:
        """
        Create a CFG block.

        Args:
            cfg_id: Parent CFG ID
            function_node_id: Function node ID
            kind: Block kind
            span: Block location

        Returns:
            Created block
        """
        block_id = _generate_cfg_block_id(cfg_id, self._block_counter)
        self._block_counter += 1

        block = ControlFlowBlock(
            id=block_id,
            kind=kind,
            function_node_id=function_node_id,
            span=span,
        )

        self._blocks.append(block)
        return block

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

    def apply_delta(
        self,
        ir_doc: IRDocument,
        source_map: dict[str, SourceFile],
        existing_cfgs: list[ControlFlowGraph],
    ) -> tuple[list[ControlFlowGraph], list[ControlFlowBlock], list[ControlFlowEdge]]:
        """
        Apply incremental changes (simplified - full rebuild for now).

        Args:
            ir_doc: Updated IR document
            source_map: Source file map
            existing_cfgs: Existing CFGs

        Returns:
            (new_cfgs, new_blocks, new_edges)
        """
        # For now, just rebuild
        # TODO: Implement proper delta logic
        return self.build_full(ir_doc, source_map)
