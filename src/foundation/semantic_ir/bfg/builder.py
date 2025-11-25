"""
BFG Builder

Extracts Basic Blocks from IR functions.
Separates block segmentation from control flow edge creation.
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from ...ir.models import IRDocument, Node, NodeKind, Span
from ...parsing import AstTree, SourceFile
from .models import BasicFlowBlock, BasicFlowGraph, BFGBlockKind


# Helper functions
def _generate_bfg_id(function_node_id: str) -> str:
    """Generate BFG ID from function node ID"""
    return f"bfg:{function_node_id}"


def _generate_bfg_block_id(bfg_id: str, block_index: int) -> str:
    """Generate BFG block ID"""
    return f"{bfg_id}:block:{block_index}"


# Python syntax types
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


class BfgBuilder:
    """
    Builds BFG (Basic Flow Graph) from IR.

    Responsibility: Extract basic blocks only
    NOT responsible for: Control flow edges (handled by CFG layer)
    """

    def __init__(self):
        self._block_counter = 0
        self._blocks: list[BasicFlowBlock] = []

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, SourceFile]
    ) -> tuple[list[BasicFlowGraph], list[BasicFlowBlock]]:
        """
        Build BFG for all functions in IR document.

        Args:
            ir_doc: Structural IR document
            source_map: file_path -> SourceFile (for AST access)

        Returns:
            (bfg_graphs, all_blocks)
        """
        bfg_graphs = []
        all_blocks = []

        # Find all functions/methods
        func_nodes = [n for n in ir_doc.nodes if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD)]

        for func_node in func_nodes:
            # Build BFG for this function
            bfg_graph, blocks = self._build_function_bfg(func_node, ir_doc, source_map)

            if bfg_graph:
                bfg_graphs.append(bfg_graph)
                all_blocks.extend(blocks)

        return bfg_graphs, all_blocks

    def _build_function_bfg(
        self,
        func_node: Node,
        ir_doc: IRDocument,
        source_map: dict[str, SourceFile],
    ) -> tuple[BasicFlowGraph | None, list[BasicFlowBlock]]:
        """
        Build BFG for a single function.

        Args:
            func_node: Function/Method node
            ir_doc: IR document
            source_map: Source file map

        Returns:
            (bfg_graph, blocks) or (None, [])
        """
        # Reset state
        self._block_counter = 0
        self._blocks = []

        # Generate BFG ID
        bfg_id = _generate_bfg_id(func_node.id)

        # Get source file
        source = source_map.get(func_node.file_path)

        # Create Entry block
        entry_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=func_node.id,
            kind=BFGBlockKind.ENTRY,
            span=Span(func_node.span.start_line, 0, func_node.span.start_line, 0),
        )

        # Create Exit block
        exit_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=func_node.id,
            kind=BFGBlockKind.EXIT,
            span=Span(func_node.span.end_line, 0, func_node.span.end_line, 0),
        )

        # Build body blocks
        total_statements = 0
        if source:
            # Enhanced BFG with AST-based analysis
            body_blocks, stmt_count = self._build_body_blocks(bfg_id, func_node, source, entry_block, exit_block)
            total_statements = stmt_count
        else:
            # Simplified BFG: single body block
            # Block is automatically added to self._blocks by _create_block
            _ = self._create_block(
                bfg_id=bfg_id,
                function_node_id=func_node.id,
                kind=BFGBlockKind.STATEMENT,
                span=func_node.body_span or func_node.span,
                statement_count=1,
            )
            total_statements = 1

        # Build BFG graph
        bfg_graph = BasicFlowGraph(
            id=bfg_id,
            function_node_id=func_node.id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=self._blocks.copy(),
            total_statements=total_statements,
        )

        return bfg_graph, self._blocks.copy()

    def _build_body_blocks(
        self,
        bfg_id: str,
        func_node: Node,
        source: SourceFile,
        entry_block: BasicFlowBlock,
        exit_block: BasicFlowBlock,
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build detailed BFG blocks by analyzing function body AST.

        Args:
            bfg_id: BFG ID
            func_node: Function node
            source: Source file
            entry_block: Entry block
            exit_block: Exit block

        Returns:
            (body_blocks, total_statement_count)
        """
        from ...parsing import AstTree

        # Parse AST
        ast = AstTree.parse(source)

        # Find function definition node in AST
        func_ast_node = self._find_function_node(ast, func_node)
        if not func_ast_node:
            # Fallback to simple body block
            body_block = self._create_block(
                bfg_id=bfg_id,
                function_node_id=func_node.id,
                kind=BFGBlockKind.STATEMENT,
                span=func_node.body_span or func_node.span,
                statement_count=1,
            )
            return [body_block], 1

        # Get function body
        body_node = func_ast_node.child_by_field_name("body")
        if not body_node:
            # No body
            return [], 0

        # Build BFG from body statements
        body_blocks, stmt_count = self._build_statement_blocks(
            bfg_id, func_node.id, body_node, entry_block, exit_block, ast
        )

        return body_blocks, stmt_count

    def _find_function_node(self, ast: "AstTree", func_node: Node) -> TSNode | None:
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
        bfg_id: str,
        function_node_id: str,
        body_node: TSNode,
        entry_block: BasicFlowBlock,
        exit_block: BasicFlowBlock,
        ast: "AstTree",
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build BFG blocks from statement list.

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            body_node: AST body node (block or suite)
            entry_block: Entry block
            exit_block: Exit block
            ast: AST tree

        Returns:
            (blocks, total_statement_count)
        """
        # Get statements from body
        statements = []
        if body_node.type == "block":
            statements = [child for child in body_node.children if child.is_named]
        else:
            statements = [body_node]

        if not statements:
            # Empty body
            return [], 0

        # Build blocks for each statement
        blocks = []
        total_stmt_count = 0

        for stmt in statements:
            if stmt.type in PYTHON_BRANCH_TYPES:
                # Branch statement (if/elif/else)
                branch_blocks, stmt_count = self._build_branch_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(branch_blocks)
                total_stmt_count += stmt_count

            elif stmt.type in PYTHON_LOOP_TYPES:
                # Loop statement (for/while)
                loop_blocks, stmt_count = self._build_loop_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(loop_blocks)
                total_stmt_count += stmt_count

            elif stmt.type in PYTHON_TRY_TYPES:
                # Try/except/finally
                try_blocks, stmt_count = self._build_try_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(try_blocks)
                total_stmt_count += stmt_count

            else:
                # Regular statement - create a basic block
                stmt_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.STATEMENT,
                    span=ast.get_span(stmt),
                    ast_node_type=stmt.type,
                    statement_count=1,
                )
                blocks.append(stmt_block)
                total_stmt_count += 1

        return blocks, total_stmt_count

    def _build_branch_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        branch_node: TSNode,
        ast: "AstTree",
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build BFG blocks for branch statements (if/elif/else).

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            branch_node: AST branch node
            ast: AST tree

        Returns:
            (blocks, statement_count)
        """
        blocks = []
        stmt_count = 0

        # Create condition block
        condition_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=function_node_id,
            kind=BFGBlockKind.CONDITION,
            span=ast.get_span(branch_node),
            ast_node_type=branch_node.type,
            ast_has_alternative=branch_node.child_by_field_name("alternative") is not None,
            statement_count=1,
        )
        blocks.append(condition_block)
        stmt_count += 1

        # Get consequence (then branch)
        consequence = branch_node.child_by_field_name("consequence")
        if consequence:
            then_block = self._create_block(
                bfg_id=bfg_id,
                function_node_id=function_node_id,
                kind=BFGBlockKind.STATEMENT,
                span=ast.get_span(consequence),
                ast_node_type="consequence",
                statement_count=1,
            )
            blocks.append(then_block)
            stmt_count += 1

        # Get alternative (else/elif branch)
        alternative = branch_node.child_by_field_name("alternative")
        if alternative:
            # Recursively handle elif/else
            if alternative.type in PYTHON_BRANCH_TYPES:
                # elif - recursive
                alt_blocks, alt_count = self._build_branch_blocks(bfg_id, function_node_id, alternative, ast)
                blocks.extend(alt_blocks)
                stmt_count += alt_count
            else:
                # else - simple block
                else_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.STATEMENT,
                    span=ast.get_span(alternative),
                    ast_node_type="alternative",
                    statement_count=1,
                )
                blocks.append(else_block)
                stmt_count += 1

        return blocks, stmt_count

    def _build_loop_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        loop_node: TSNode,
        ast: "AstTree",
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build BFG blocks for loop statements (for/while).

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            loop_node: AST loop node
            ast: AST tree

        Returns:
            (blocks, statement_count)
        """
        blocks = []
        stmt_count = 0

        # Create loop header block
        loop_header = self._create_block(
            bfg_id=bfg_id,
            function_node_id=function_node_id,
            kind=BFGBlockKind.LOOP_HEADER,
            span=ast.get_span(loop_node),
            ast_node_type=loop_node.type,
            statement_count=1,
        )
        blocks.append(loop_header)
        stmt_count += 1

        # Get loop body
        body = loop_node.child_by_field_name("body")
        if body:
            loop_body = self._create_block(
                bfg_id=bfg_id,
                function_node_id=function_node_id,
                kind=BFGBlockKind.STATEMENT,
                span=ast.get_span(body),
                ast_node_type="loop_body",
                statement_count=1,
            )
            blocks.append(loop_body)
            stmt_count += 1

        return blocks, stmt_count

    def _build_try_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        try_node: TSNode,
        ast: "AstTree",
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build BFG blocks for try/except/finally statements.

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            try_node: AST try node
            ast: AST tree

        Returns:
            (blocks, statement_count)
        """
        blocks = []
        stmt_count = 0

        # Create try block
        body = try_node.child_by_field_name("body")
        if body:
            try_block = self._create_block(
                bfg_id=bfg_id,
                function_node_id=function_node_id,
                kind=BFGBlockKind.TRY,
                span=ast.get_span(body),
                ast_node_type="try_body",
                statement_count=1,
            )
            blocks.append(try_block)
            stmt_count += 1

            # Find except clauses
            for child in try_node.children:
                if child.type == "except_clause":
                    except_block = self._create_block(
                        bfg_id=bfg_id,
                        function_node_id=function_node_id,
                        kind=BFGBlockKind.CATCH,
                        span=ast.get_span(child),
                        ast_node_type="except_clause",
                        statement_count=1,
                    )
                    blocks.append(except_block)
                    stmt_count += 1

                elif child.type == "finally_clause":
                    finally_block = self._create_block(
                        bfg_id=bfg_id,
                        function_node_id=function_node_id,
                        kind=BFGBlockKind.FINALLY,
                        span=ast.get_span(child),
                        ast_node_type="finally_clause",
                        statement_count=1,
                    )
                    blocks.append(finally_block)
                    stmt_count += 1

        return blocks, stmt_count

    def _create_block(
        self,
        bfg_id: str,
        function_node_id: str,
        kind: BFGBlockKind,
        span: Span,
        ast_node_type: str | None = None,
        ast_has_alternative: bool = False,
        statement_count: int = 0,
    ) -> BasicFlowBlock:
        """
        Create a BFG block.

        Args:
            bfg_id: Parent BFG ID
            function_node_id: Function node ID
            kind: Block kind
            span: Block location
            ast_node_type: AST node type (for CFG edge generation)
            ast_has_alternative: Has else/elif branch
            statement_count: Number of statements

        Returns:
            Created block
        """
        block_id = _generate_bfg_block_id(bfg_id, self._block_counter)
        self._block_counter += 1

        block = BasicFlowBlock(
            id=block_id,
            kind=kind,
            function_node_id=function_node_id,
            span=span,
            ast_node_type=ast_node_type,
            ast_has_alternative=ast_has_alternative,
            statement_count=statement_count,
        )

        self._blocks.append(block)
        return block
