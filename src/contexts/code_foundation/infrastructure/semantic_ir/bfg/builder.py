"""
BFG Builder

Extracts Basic Blocks from IR functions.
Separates block segmentation from control flow edge creation.

Memory Safety:
- AST cache limited to 30 trees (reduced for memory safety)
- Each tree ~5-15MB, total ~150MB-450MB
- Cache stats available via get_cache_stats()
"""

from collections import OrderedDict

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.common.observability import get_logger, record_counter, record_histogram
from src.contexts.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind, Span
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.cache_utils import get_optimal_ast_cache_size


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


class AstLRUCache:
    """
    LRU cache for AST trees with memory safety.

    Similar to Expression Builder's cache but optimized for ASTs.
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize AST cache.

        Args:
            max_size: Maximum AST trees to cache (default: 100, ~500MB-1.5GB)
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, AstTree] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> AstTree | None:
        """Get cached AST and mark as recently used"""
        if key not in self._cache:
            self._misses += 1
            return None

        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]

    def put(self, key: str, value: AstTree):
        """Cache AST with LRU eviction"""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = value
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

    def clear(self):
        """Clear cache and reset stats"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_stats(self) -> dict:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": hit_rate,
        }


class BfgBuilder:
    """
    Builds BFG (Basic Flow Graph) from IR.

    Responsibility: Extract basic blocks only
    NOT responsible for: Control flow edges (handled by CFG layer)

    Memory Safety:
    - AST cache limited to 100 trees (~500MB-1.5GB)
    - LRU eviction prevents unbounded growth
    - Aligned with ExpressionBuilder cache size for consistency
    """

    def __init__(self, ast_cache_size: int = 100):
        """
        Initialize BFG Builder.

        Args:
            ast_cache_size: Maximum AST trees to cache (default: 100, aligned with ExpressionBuilder)
        """
        self.logger = get_logger(__name__)
        self._block_counter = 0
        self._blocks: list[BasicFlowBlock] = []
        self._ast_cache = AstLRUCache(max_size=ast_cache_size)
        # Loop context stack for tracking nested loops (Added 2025-11-25)
        self._loop_stack: list[str] = []  # Stack of loop header block IDs

        record_counter("bfg_builder_initialized_total")

    def get_cache_stats(self) -> dict:
        """Get AST cache statistics for monitoring"""
        return self._ast_cache.get_stats()

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, tuple[SourceFile, "AstTree"]] | dict[str, SourceFile]
    ) -> tuple[list[BasicFlowGraph], list[BasicFlowBlock]]:
        """
        Build BFG for all functions in IR document.

        Args:
            ir_doc: Structural IR document
            source_map: file_path -> (SourceFile, AstTree) or file_path -> SourceFile
                       When AstTree is provided, avoids re-parsing (60-70% improvement)

        Returns:
            (bfg_graphs, all_blocks)

        Raises:
            ValueError: If IR document is invalid
        """
        # Input validation
        if not ir_doc:
            raise ValueError("IRDocument cannot be None")
        if not ir_doc.nodes:
            self.logger.warning(
                "bfg_empty_ir_document",
                message="Empty IR document provided",
            )
            return [], []

        # Performance optimization: Dynamically adjust cache size based on project scale
        file_count = len(source_map)
        optimal_cache_size = get_optimal_ast_cache_size(file_count)
        if optimal_cache_size != self._ast_cache.max_size:
            self._ast_cache = AstLRUCache(max_size=optimal_cache_size)
            self.logger.info(
                "bfg_cache_resized",
                file_count=file_count,
                cache_size=optimal_cache_size,
            )

        # Performance optimization: Use pre-parsed AST or parse once and cache
        self._ast_cache.clear()
        parse_success = 0
        parse_failed = 0
        reused_ast = 0
        failed_files = []  # Track failed file paths

        for file_path, source_data in source_map.items():
            try:
                # Check if source_data is tuple (SourceFile, AstTree) or just SourceFile
                if isinstance(source_data, tuple):
                    # Pre-parsed AST provided - reuse it (avoid re-parsing)
                    source, ast = source_data
                    self._ast_cache.put(file_path, ast)
                    reused_ast += 1
                else:
                    # Only SourceFile provided - need to parse
                    source = source_data
                    ast = AstTree.parse(source)
                    self._ast_cache.put(file_path, ast)
                    parse_success += 1
            except Exception as e:
                # Parsing failed - will be handled in _build_function_bfg
                self.logger.warning(
                    "bfg_parse_failed",
                    file_path=file_path,
                    error=str(e),
                )
                parse_failed += 1
                failed_files.append(file_path)

        self.logger.info(
            "bfg_ast_cache_status",
            parse_success=parse_success,
            reused_ast=reused_ast,
            parse_failed=parse_failed,
        )

        # Log failed files if any
        if failed_files:
            self.logger.error(
                "bfg_parse_failures_summary",
                failed_count=len(failed_files),
                failed_files=failed_files[:10],  # Show first 10
                message=f"{len(failed_files)} file(s) failed to parse. BFG generation for these files will be skipped.",
            )

        record_counter("bfg_ast_parse_total", labels={"status": "success"}, value=parse_success)
        record_counter("bfg_ast_reused_total", labels={"status": "reused"}, value=reused_ast)
        record_counter("bfg_ast_parse_total", labels={"status": "failed"}, value=parse_failed)

        bfg_graphs = []
        all_blocks = []
        failed_functions = []  # Track failed function nodes

        # Find all functions/methods
        func_nodes = [n for n in ir_doc.nodes if n.kind in (NodeKind.FUNCTION, NodeKind.METHOD)]

        for func_node in func_nodes:
            # Build BFG for this function (uses cached AST)
            bfg_graph, blocks = self._build_function_bfg(func_node, ir_doc, source_map)

            if bfg_graph:
                bfg_graphs.append(bfg_graph)
                all_blocks.extend(blocks)
            else:
                # BFG generation failed for this function
                failed_functions.append(func_node.fqn or func_node.id)

        # Log cache performance
        cache_stats = self._ast_cache.get_stats()
        self.logger.info(
            "bfg_build_complete",
            total_functions=len(func_nodes),
            graphs_count=len(bfg_graphs),
            blocks_count=len(all_blocks),
            failed_functions_count=len(failed_functions),
            cache_hit_rate=cache_stats["hit_rate"],
            cache_evictions=cache_stats["evictions"],
        )

        # Log failed functions if any
        if failed_functions:
            self.logger.error(
                "bfg_function_failures_summary",
                failed_count=len(failed_functions),
                failed_functions=failed_functions[:10],  # Show first 10
                message=(
                    f"{len(failed_functions)} function(s) failed BFG generation. These will be missing from CFG/DFG."
                ),
            )

        # Metrics
        record_histogram("bfg_graphs_count", len(bfg_graphs))
        record_histogram("bfg_blocks_count", len(all_blocks))
        record_histogram("bfg_cache_hit_rate", cache_stats["hit_rate"])

        return bfg_graphs, all_blocks

    def _build_function_bfg(
        self,
        func_node: Node,
        ir_doc: IRDocument,
        source_map: dict[str, tuple[SourceFile, "AstTree"]] | dict[str, SourceFile],
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
        self._loop_stack = []  # Reset loop stack for each function

        # Generate BFG ID
        bfg_id = _generate_bfg_id(func_node.id)

        # Get source file (handle both tuple and SourceFile formats)
        source_data = source_map.get(func_node.file_path)
        if isinstance(source_data, tuple):
            source, _ = source_data  # Extract SourceFile from tuple
        else:
            source = source_data  # Already SourceFile

        # Log function processing start
        self.logger.debug(
            "bfg_building_function",
            function_name=func_node.name,
            function_id=func_node.id,
            file_path=func_node.file_path,
            source_available=source is not None,
        )

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
            try:
                body_blocks, stmt_count = self._build_body_blocks(bfg_id, func_node, source, entry_block, exit_block)
                total_statements = stmt_count
            except Exception as e:
                # Fallback to simple body block on AST parsing errors
                self.logger.warning(
                    "bfg_build_failed_fallback",
                    function_id=func_node.id,
                    error=str(e),
                    message="Using fallback simple block",
                )
                record_counter("bfg_build_fallback_total", labels={"reason": "ast_error"})

                # Create simple body block as fallback
                _ = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=func_node.id,
                    kind=BFGBlockKind.STATEMENT,
                    span=func_node.body_span or func_node.span,
                    statement_count=1,
                )
                total_statements = 1
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
            blocks=self._blocks,  # No copy needed - immutable after creation
            total_statements=total_statements,
        )

        # Log completion
        block_kinds = [b.kind.value for b in self._blocks]
        self.logger.debug(
            "bfg_function_complete",
            function_name=func_node.name,
            blocks_count=len(self._blocks),
            statements_count=total_statements,
            block_kinds=block_kinds,
        )

        # Metrics
        record_histogram("bfg_function_blocks_count", len(self._blocks))
        record_histogram("bfg_function_statements_count", total_statements)

        return bfg_graph, self._blocks

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
        # Use cached AST instead of parsing again (40% performance improvement)
        ast = self._ast_cache.get(func_node.file_path)
        if ast is None:
            # Cache miss - parse now
            self.logger.debug(
                "bfg_ast_cache_miss",
                file_path=func_node.file_path,
            )
            record_counter("bfg_ast_cache_total", labels={"status": "miss"})
            ast = AstTree.parse(source)
            self._ast_cache.put(func_node.file_path, ast)
        else:
            self.logger.debug(
                "bfg_ast_cache_hit",
                file_path=func_node.file_path,
            )
            record_counter("bfg_ast_cache_total", labels={"status": "hit"})

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
        body_node: "TSNode",
        entry_block: BasicFlowBlock | None,
        exit_block: BasicFlowBlock | None,
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

            # Control flow statements (Added 2025-11-25)
            elif stmt.type == "break_statement":
                # Break statement - jumps to loop exit
                target_loop_id = self._loop_stack[-1] if self._loop_stack else None
                break_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.STATEMENT,
                    span=ast.get_span(stmt),
                    ast_node_type=stmt.type,
                    statement_count=1,
                    is_break=True,
                    target_loop_id=target_loop_id,
                )
                blocks.append(break_block)
                total_stmt_count += 1

            elif stmt.type == "continue_statement":
                # Continue statement - jumps to loop header
                target_loop_id = self._loop_stack[-1] if self._loop_stack else None
                continue_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.STATEMENT,
                    span=ast.get_span(stmt),
                    ast_node_type=stmt.type,
                    statement_count=1,
                    is_continue=True,
                    target_loop_id=target_loop_id,
                )
                blocks.append(continue_block)
                total_stmt_count += 1

            elif stmt.type == "return_statement":
                # Return statement - jumps to function exit
                return_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.STATEMENT,
                    span=ast.get_span(stmt),
                    ast_node_type=stmt.type,
                    statement_count=1,
                    is_return=True,
                )
                blocks.append(return_block)
                total_stmt_count += 1

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
        branch_node: "TSNode",
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
        loop_node: "TSNode",
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

        # Push loop context for nested loop support (Added 2025-11-25)
        self._loop_stack.append(loop_header.id)

        try:
            # Get loop body and recursively process statements
            body = loop_node.child_by_field_name("body")
            if body:
                # Recursively process body statements to detect break/continue
                body_blocks, body_stmt_count = self._build_statement_blocks(
                    bfg_id, function_node_id, body, None, None, ast
                )
                blocks.extend(body_blocks)
                stmt_count += body_stmt_count
        finally:
            # Pop loop context (Added 2025-11-25)
            self._loop_stack.pop()

        return blocks, stmt_count

    def _build_try_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        try_node: "TSNode",
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
        # Control flow metadata (Added 2025-11-25)
        is_break: bool = False,
        is_continue: bool = False,
        is_return: bool = False,
        target_loop_id: str | None = None,
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
            is_break: True if block ends with break statement
            is_continue: True if block ends with continue statement
            is_return: True if block ends with return statement
            target_loop_id: Target loop header block ID for break/continue

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
            # Control flow metadata (Added 2025-11-25)
            is_break=is_break,
            is_continue=is_continue,
            is_return=is_return,
            target_loop_id=target_loop_id,
        )

        self._blocks.append(block)

        # Log block creation (detailed for debugging)
        if kind != BFGBlockKind.ENTRY and kind != BFGBlockKind.EXIT:
            # Only log interesting blocks (not entry/exit boilerplate)
            self.logger.debug(
                "bfg_block_created",
                block_index=self._block_counter - 1,
                block_kind=kind.value,
                start_line=span.start_line,
                end_line=span.end_line,
                statement_count=statement_count,
                is_break=is_break,
                is_continue=is_continue,
                is_return=is_return,
            )

        return block
