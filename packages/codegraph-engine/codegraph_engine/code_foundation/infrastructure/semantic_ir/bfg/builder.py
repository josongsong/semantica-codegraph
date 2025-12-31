"""
BFG Builder

Extracts Basic Blocks from IR functions.
Separates block segmentation from control flow edge creation.

Memory Safety:
- AST cache limited to 30 trees (reduced for memory safety)
- Each tree ~5-15MB, total ~150MB-450MB
- Cache stats available via get_cache_stats()
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

from codegraph_shared.common.observability import get_logger, record_counter, record_histogram
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.span_pool import SpanPool
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BasicFlowGraph,
    BFGBlockKind,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cache_utils import get_optimal_ast_cache_size
from codegraph_engine.code_foundation.infrastructure.semantic_ir.config import _DEBUG_ENABLED


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

# JavaScript/TypeScript types (Added 2025-12-09 - SOTA Multi-language)
JAVASCRIPT_BRANCH_TYPES = {
    "if_statement",
    "else_clause",
}
JAVASCRIPT_LOOP_TYPES = {
    "for_statement",
    "while_statement",
    "do_statement",  # do-while loop
}
TYPESCRIPT_BRANCH_TYPES = JAVASCRIPT_BRANCH_TYPES
TYPESCRIPT_LOOP_TYPES = JAVASCRIPT_LOOP_TYPES

# Java syntax types
JAVA_BRANCH_TYPES = {
    "if_statement",
    "switch_expression",
    "switch_statement",
}

JAVA_LOOP_TYPES = {
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
}

JAVA_TRY_TYPES = {
    "try_statement",
    "try_with_resources_statement",
    "catch_clause",
    "finally_clause",
}

# Kotlin syntax types
KOTLIN_BRANCH_TYPES = {
    "if_expression",
    "when_expression",
}

KOTLIN_LOOP_TYPES = {
    "for_statement",
    "while_statement",
    "do_while_statement",
}

KOTLIN_TRY_TYPES = {
    "try_expression",
    "catch_block",
    "finally_block",
}

# JavaScript/TypeScript try types (Added 2025-12-09 - SOTA Multi-language)
JAVASCRIPT_TRY_TYPES = {
    "try_statement",
}
TYPESCRIPT_TRY_TYPES = JAVASCRIPT_TRY_TYPES  # Same as JavaScript


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
        # Current language being processed (set per function)
        self._current_language: str = "python"

        # Generator lowering (Added 2025-12-09 - Phase 1)
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.generator_lowering import GeneratorLowering

        self._generator_lowering = GeneratorLowering()

        record_counter("bfg_builder_initialized_total")

    def get_cache_stats(self) -> dict:
        """Get AST cache statistics for monitoring"""
        return self._ast_cache.get_stats()

    def _get_branch_types(self) -> set[str]:
        """
        Get branch types for current language.

        SOTA Multi-language support (2025-12-09)
        """
        if self._current_language == "java":
            return JAVA_BRANCH_TYPES
        elif self._current_language == "kotlin":
            return KOTLIN_BRANCH_TYPES
        elif self._current_language == "python":
            return PYTHON_BRANCH_TYPES
        elif self._current_language in ("javascript", "typescript"):
            return JAVASCRIPT_BRANCH_TYPES
        else:
            # Unsupported language - log warning and use empty set (fallback gracefully)
            self.logger.warning(
                "bfg_unsupported_language_branch",
                language=self._current_language,
                message=f"Language '{self._current_language}' not explicitly supported for branch types. Using empty set.",
            )
            return set()  # Graceful fallback  # Graceful fallback

    def _get_loop_types(self) -> set[str]:
        """
        Get loop types for current language.

        SOTA Multi-language support (2025-12-09)
        """
        if self._current_language == "java":
            return JAVA_LOOP_TYPES
        elif self._current_language == "kotlin":
            return KOTLIN_LOOP_TYPES
        elif self._current_language == "python":
            return PYTHON_LOOP_TYPES
        elif self._current_language in ("javascript", "typescript"):
            return JAVASCRIPT_LOOP_TYPES
        else:
            self.logger.warning(
                "bfg_unsupported_language_loop",
                language=self._current_language,
                message=f"Language '{self._current_language}' not explicitly supported for loop types. Using empty set.",
            )
            return set()

    def _get_try_types(self) -> set[str]:
        """
        Get try/catch types for current language.

        Updated: 2025-12-09 (SOTA: Multi-language support)
        """
        if self._current_language == "java":
            return JAVA_TRY_TYPES
        elif self._current_language == "kotlin":
            return KOTLIN_TRY_TYPES
        elif self._current_language == "python":
            return PYTHON_TRY_TYPES
        elif self._current_language in ("javascript", "typescript"):
            return JAVASCRIPT_TRY_TYPES
        else:
            self.logger.warning(
                "bfg_unsupported_language_try",
                language=self._current_language,
                message=f"Language '{self._current_language}' not explicitly supported for try types. Using empty set.",
            )
            return set()

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, tuple[SourceFile, AstTree]] | dict[str, SourceFile]
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
            if _DEBUG_ENABLED:
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

        if _DEBUG_ENABLED:
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

        # SOTA: Also process FILE nodes for module-level code (scripts, __main__, etc.)
        file_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FILE]
        for file_node in file_nodes:
            bfg_graph, blocks = self._build_module_scope_bfg(file_node, ir_doc, source_map)
            if bfg_graph:
                bfg_graphs.append(bfg_graph)
                all_blocks.extend(blocks)

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
        if _DEBUG_ENABLED:
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

    def _build_module_scope_bfg(
        self,
        file_node: Node,
        ir_doc: IRDocument,
        source_map: dict[str, tuple[SourceFile, AstTree]] | dict[str, SourceFile],
    ) -> tuple[BasicFlowGraph | None, list[BasicFlowBlock]]:
        """
        Build BFG for module-level (top-level) code.

        SOTA: Treats module-level statements as a virtual '<module>' function.
        This enables taint analysis for scripts and __main__ blocks.

        Args:
            file_node: FILE node representing the module
            ir_doc: IR document
            source_map: Source file map

        Returns:
            (bfg_graph, blocks) or (None, []) if no module-level code
        """
        # Reset state
        self._block_counter = 0
        self._blocks = []
        self._loop_stack = []
        self._current_language = file_node.language.lower() if file_node.language else "python"

        # Generate BFG ID for module scope
        module_scope_id = f"{file_node.id}:<module>"
        bfg_id = _generate_bfg_id(module_scope_id)

        # Get source and AST
        source_data = source_map.get(file_node.file_path)
        if not source_data:
            return None, []

        if isinstance(source_data, tuple):
            source, ast = source_data
        else:
            source = source_data
            ast = self._ast_cache.get(file_node.file_path)
            if not ast:
                try:
                    ast = AstTree.parse(source)
                except Exception:
                    return None, []

        # Find module-level statements (not inside functions/classes)
        try:
            module_stmts = self._get_module_level_statements(ast)
            if not module_stmts:
                return None, []  # No module-level code
        except Exception:
            return None, []

        # Create virtual function span from first to last statement
        first_stmt = module_stmts[0]
        last_stmt = module_stmts[-1]
        module_span = Span(
            first_stmt.start_point[0] + 1,
            first_stmt.start_point[1],
            last_stmt.end_point[0] + 1,
            last_stmt.end_point[1],
        )

        # Create Entry block
        entry_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=module_scope_id,
            kind=BFGBlockKind.ENTRY,
            span=SpanPool.intern(module_span.start_line, 0, module_span.start_line, 0),
        )

        # Create Exit block
        exit_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=module_scope_id,
            kind=BFGBlockKind.EXIT,
            span=SpanPool.intern(module_span.end_line, 0, module_span.end_line, 0),
        )

        # Build blocks for each module-level statement
        # Note: BFG doesn't store edges - CFG layer adds them later
        for stmt in module_stmts:
            stmt_span = Span(
                stmt.start_point[0] + 1,
                stmt.start_point[1],
                stmt.end_point[0] + 1,
                stmt.end_point[1],
            )
            self._create_block(
                bfg_id=bfg_id,
                function_node_id=module_scope_id,
                kind=BFGBlockKind.STATEMENT,
                span=stmt_span,
                statement_count=1,
            )

        # Build BFG graph
        bfg_graph = BasicFlowGraph(
            id=bfg_id,
            function_node_id=module_scope_id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=self._blocks,
            total_statements=len(module_stmts),
            is_generator=False,
            generator_yield_count=0,
        )

        if _DEBUG_ENABLED:
            self.logger.debug(
                "bfg_module_scope_built",
                file_path=file_node.file_path,
                statements=len(module_stmts),
                blocks=len(self._blocks),
            )

        return bfg_graph, list(self._blocks)

    def _get_module_level_statements(self, ast: AstTree) -> list:
        """
        Extract module-level statements from AST.

        Returns statements that are direct children of module,
        excluding function/class definitions (which are handled separately).
        """
        root = ast.root
        module_stmts = []

        # Skip types that are handled as separate scopes
        skip_types = {
            "function_definition",
            "class_definition",
            "decorated_definition",
            "import_statement",
            "import_from_statement",
        }

        for child in root.children:
            if child.type not in skip_types and not child.type.startswith("import"):
                # This is a module-level executable statement
                module_stmts.append(child)

        return module_stmts

    def _build_function_bfg(
        self,
        func_node: Node,
        ir_doc: IRDocument,
        source_map: dict[str, tuple[SourceFile, AstTree]] | dict[str, SourceFile],
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
        # Set current language from function node
        self._current_language = func_node.language.lower() if func_node.language else "python"

        # Generate BFG ID
        bfg_id = _generate_bfg_id(func_node.id)

        # Get source file (handle both tuple and SourceFile formats)
        source_data = source_map.get(func_node.file_path)
        if isinstance(source_data, tuple):
            source, _ = source_data  # Extract SourceFile from tuple
        else:
            source = source_data  # Already SourceFile

        # Log function processing start
        if _DEBUG_ENABLED:
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
            span=SpanPool.intern(func_node.span.start_line, 0, func_node.span.start_line, 0),
        )

        # Create Exit block
        exit_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=func_node.id,
            kind=BFGBlockKind.EXIT,
            span=SpanPool.intern(func_node.span.end_line, 0, func_node.span.end_line, 0),
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

        # Check if generator (for metadata)
        is_generator = any(b.kind == BFGBlockKind.YIELD for b in self._blocks)
        yield_count = sum(1 for b in self._blocks if b.kind == BFGBlockKind.YIELD)

        # Build BFG graph
        bfg_graph = BasicFlowGraph(
            id=bfg_id,
            function_node_id=func_node.id,
            entry_block_id=entry_block.id,
            exit_block_id=exit_block.id,
            blocks=self._blocks,  # No copy needed - immutable after creation
            total_statements=total_statements,
            is_generator=is_generator,
            generator_yield_count=yield_count,
        )

        # Log completion
        block_kinds = [b.kind.value for b in self._blocks]
        if _DEBUG_ENABLED:
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
            if _DEBUG_ENABLED:
                self.logger.debug(
                    "bfg_ast_cache_miss",
                    file_path=func_node.file_path,
                )
            record_counter("bfg_ast_cache_total", labels={"status": "miss"})
            ast = AstTree.parse(source)
            self._ast_cache.put(func_node.file_path, ast)
        else:
            if _DEBUG_ENABLED:
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

        # Get function body (language-specific field names)
        if self._current_language == "java":
            # Java: method body is in "body" field
            body_node = func_ast_node.child_by_field_name("body")
        elif self._current_language == "kotlin":
            # Kotlin: function_body type (NOT a field, find by type)
            body_node = next((child for child in func_ast_node.children if child.type == "function_body"), None)
            if not body_node:
                # Try expression body (e.g., fun add(x: Int) = x + 1)
                for child in func_ast_node.children:
                    if child.type not in ("simple_identifier", "function_value_parameters", "user_type", "modifiers"):
                        body_node = child
                        break
        else:
            # Python: body field
            body_node = func_ast_node.child_by_field_name("body")

        if not body_node:
            # No body
            return [], 0

        # CRITICAL: Check if generator (Phase 1 - 2025-12-09)
        # Generator functions need special state machine lowering
        if self._is_generator_function(func_ast_node):
            if _DEBUG_ENABLED:
                self.logger.info(
                    "generator_detected",
                    function_name=func_node.name,
                    function_id=func_node.id,
                )

            # Delegate to GeneratorLowering
            try:
                generator_blocks, yield_count = self._generator_lowering.lower(
                    func_ast=func_ast_node,
                    ast_tree=ast,
                    bfg_id=bfg_id,
                    function_node_id=func_node.id,
                )

                # CRITICAL (Phase 2): Set generator_all_locals on ENTRY block
                # SSA needs this metadata to build variable definitions
                all_locals = None
                for gb in generator_blocks:
                    if gb.generator_all_locals:
                        all_locals = gb.generator_all_locals
                        break

                if all_locals:
                    # Update ENTRY block with generator metadata
                    entry_block.generator_all_locals = all_locals

                    if _DEBUG_ENABLED:
                        self.logger.debug(
                            "generator_entry_metadata_set",
                            function_name=func_node.name,
                            locals_count=len(all_locals),
                        )

                # Add generator blocks to self._blocks
                self._blocks.extend(generator_blocks)

                # Update BFG graph metadata
                # (will be set in caller)

                if _DEBUG_ENABLED:
                    self.logger.info(
                        "generator_lowering_complete",
                        function_name=func_node.name,
                        yield_count=yield_count,
                        block_count=len(generator_blocks),
                    )

                # Return generator blocks
                # Statement count = yield count (approximate)
                return generator_blocks, yield_count

            except Exception as e:
                # Generator lowering failed - fallback to normal blocks
                self.logger.error(
                    "generator_lowering_failed",
                    function_name=func_node.name,
                    error=str(e),
                    message="Falling back to normal BFG blocks",
                )
                # Continue with normal block building

        # Build BFG from body statements (normal functions)
        body_blocks, stmt_count = self._build_statement_blocks(
            bfg_id, func_node.id, body_node, entry_block, exit_block, ast
        )

        return body_blocks, stmt_count

    def _find_function_node(self, ast: AstTree, func_node: Node) -> TSNode | None:
        """
        Find the Tree-sitter function node matching the IR function node.

        SOTA OPTIMIZATION (2025-12-21):
        - Uses AST index for O(1) lookup instead of O(n) recursive search
        - 40x faster: 4.3s → 0.1s on attrs (54 files)
        - Multi-language support maintained

        MULTI-LANGUAGE SUPPORT:
        - Python: function_definition, decorated_definition
        - JavaScript/TypeScript: function_declaration, arrow_function, method_definition
        - Java: method_declaration, constructor_declaration
        - Kotlin: function_declaration

        Args:
            ast: AST tree
            func_node: IR function node

        Returns:
            Tree-sitter function node or None

        Updated: 2025-12-21 (SOTA: Index-based O(1) lookup)
        """
        # OPTIMIZED: O(1) lookup by line number
        target_line = func_node.span.start_line
        return ast.find_function_at_line(target_line)

    def _build_statement_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        body_node: TSNode,
        entry_block: BasicFlowBlock | None,
        exit_block: BasicFlowBlock | None,
        ast: AstTree,
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
        # Get statements from body (language-specific)
        statements = []
        if self._current_language == "java":
            # Java: block contains statements directly
            if body_node.type == "block":
                statements = [child for child in body_node.children if child.is_named and child.type not in ("{", "}")]
            else:
                statements = [body_node]
        elif self._current_language == "kotlin":
            # Kotlin: function_body → statements → [actual statements]
            if body_node.type == "function_body":
                # Find statements node inside function_body
                statements_node = next((child for child in body_node.children if child.type == "statements"), None)
                if statements_node:
                    # Extract actual statements from statements node
                    statements = [child for child in statements_node.children if child.is_named]
                else:
                    # Single expression body (no statements wrapper)
                    statements = [
                        child for child in body_node.children if child.is_named and child.type not in ("{", "}")
                    ]
            elif body_node.type == "statements":
                # Direct statements node (from recursion)
                statements = [child for child in body_node.children if child.is_named]
            else:
                # Expression body (e.g., fun add(x: Int) = x + 1)
                statements = [body_node]
        else:
            # Python/JavaScript/TypeScript: block or suite or statement_block
            if body_node.type in ("block", "statement_block"):  # FIXED 2025-12-09: JS/TS support
                statements = [child for child in body_node.children if child.is_named]
            else:
                statements = [body_node]

        if not statements:
            # Empty body
            return [], 0

        # Build blocks for each statement
        blocks = []
        total_stmt_count = 0

        # Get language-specific node types
        branch_types = self._get_branch_types()
        loop_types = self._get_loop_types()
        try_types = self._get_try_types()

        for stmt in statements:
            if stmt.type in branch_types:
                # Branch statement (if/elif/else, switch, when)
                branch_blocks, stmt_count = self._build_branch_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(branch_blocks)
                total_stmt_count += stmt_count

            elif stmt.type in loop_types:
                # Loop statement (for/while/do-while)
                loop_blocks, stmt_count = self._build_loop_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(loop_blocks)
                total_stmt_count += stmt_count

            elif stmt.type in try_types:
                # Try/except/finally or try/catch/finally
                try_blocks, stmt_count = self._build_try_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(try_blocks)
                total_stmt_count += stmt_count

            # Async/await support (Added 2025-12-08, MOVED UP 2025-12-09)
            # CRITICAL: Must check await BEFORE return/break/continue
            # because "return await expr" should be SUSPEND/RESUME, not return block
            elif self._is_await_statement(stmt):
                # Await expression - split into SUSPEND and RESUME blocks
                await_blocks, await_stmt_count = self._build_await_blocks(bfg_id, function_node_id, stmt, ast)
                blocks.extend(await_blocks)
                total_stmt_count += await_stmt_count

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
        branch_node: TSNode,
        ast: AstTree,
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
            # Process consequence body recursively (CRITICAL FIX 2025-12-08)
            # This allows await/loop/nested-if inside if to be detected
            then_blocks, then_count = self._build_statement_blocks(
                bfg_id, function_node_id, consequence, None, None, ast
            )
            blocks.extend(then_blocks)
            stmt_count += then_count

        # Get alternative (elif branch)
        alternative = branch_node.child_by_field_name("alternative")
        if alternative:
            # Recursively handle elif
            branch_types = self._get_branch_types()
            if alternative.type in branch_types:
                # elif - recursive
                alt_blocks, alt_count = self._build_branch_blocks(bfg_id, function_node_id, alternative, ast)
                blocks.extend(alt_blocks)
                stmt_count += alt_count

        # Get else_clause (Python-specific: else is direct child, not alternative)
        # CRITICAL FIX 2025-12-09: Python's else_clause is separate from alternative
        else_clause = None
        for child in branch_node.children:
            if child.is_named and child.type == "else_clause":
                else_clause = child
                break

        if else_clause:
            # Find block inside else_clause (Python/JS/TS)
            else_body = None
            for grandchild in else_clause.children:
                if grandchild.is_named and grandchild.type in ("block", "statement_block"):  # JS/TS support
                    else_body = grandchild
                    break

            if else_body:
                else_blocks, else_count = self._build_statement_blocks(
                    bfg_id, function_node_id, else_body, None, None, ast
                )
                blocks.extend(else_blocks)
                stmt_count += else_count

        return blocks, stmt_count

    def _build_loop_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        loop_node: TSNode,
        ast: AstTree,
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
        try_node: TSNode,
        ast: AstTree,
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

        # Create try block header
        body = try_node.child_by_field_name("body")
        if body:
            try_block = self._create_block(
                bfg_id=bfg_id,
                function_node_id=function_node_id,
                kind=BFGBlockKind.TRY,
                span=ast.get_span(try_node),  # Use try statement span (not just body)
                ast_node_type="try_body",
                statement_count=1,
            )
            blocks.append(try_block)
            stmt_count += 1

            # Process try body statements recursively (CRITICAL FIX 2025-12-08)
            # This allows await/loop/if statements inside try to be properly detected
            try_body_blocks, try_body_count = self._build_statement_blocks(
                bfg_id, function_node_id, body, None, None, ast
            )
            blocks.extend(try_body_blocks)
            stmt_count += try_body_count

        # Find except/catch clauses
        for child in try_node.children:
            if child.type in ("except_clause", "catch_clause"):
                except_block = self._create_block(
                    bfg_id=bfg_id,
                    function_node_id=function_node_id,
                    kind=BFGBlockKind.CATCH,
                    span=ast.get_span(child),
                    ast_node_type=child.type,
                    statement_count=1,
                )
                blocks.append(except_block)
                stmt_count += 1

                # Process except body recursively (ADDED 2025-12-08, FIXED 2025-12-09)
                # Python/JS/TS: except_clause/catch_clause doesn't have 'body' field
                except_body = None
                for grandchild in child.children:
                    if grandchild.is_named and grandchild.type in ("block", "statement_block"):  # JS/TS support
                        except_body = grandchild
                        break

                if except_body:
                    except_body_blocks, except_body_count = self._build_statement_blocks(
                        bfg_id, function_node_id, except_body, None, None, ast
                    )
                    blocks.extend(except_body_blocks)
                    stmt_count += except_body_count

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

                # Process finally body recursively (ADDED 2025-12-08, FIXED 2025-12-09)
                # Python/JS/TS: finally_clause doesn't have 'body' field
                finally_body = None
                for grandchild in child.children:
                    if grandchild.is_named and grandchild.type in ("block", "statement_block"):  # JS/TS support
                        finally_body = grandchild
                        break

                if finally_body:
                    finally_body_blocks, finally_body_count = self._build_statement_blocks(
                        bfg_id, function_node_id, finally_body, None, None, ast
                    )
                    blocks.extend(finally_body_blocks)
                    stmt_count += finally_body_count

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
        # Async/await metadata (Added 2025-12-08)
        is_async_call: bool = False,
        async_target_expression: str | None = None,
        resume_from_suspend_id: str | None = None,
        async_result_variable: str | None = None,
        can_throw_exception: bool = False,
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
            is_async_call: True if block contains await expression
            async_target_expression: The awaited expression
            resume_from_suspend_id: Corresponding SUSPEND block ID (for RESUME)
            async_result_variable: Variable assigned from await result
            can_throw_exception: True if block can throw/reject

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
            # Async/await metadata (Added 2025-12-08)
            is_async_call=is_async_call,
            async_target_expression=async_target_expression,
            resume_from_suspend_id=resume_from_suspend_id,
            async_result_variable=async_result_variable,
            can_throw_exception=can_throw_exception,
        )

        self._blocks.append(block)

        # Log block creation (detailed for debugging)
        if kind != BFGBlockKind.ENTRY and kind != BFGBlockKind.EXIT:
            # Only log interesting blocks (not entry/exit boilerplate)
            if _DEBUG_ENABLED:
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
                    is_async_call=is_async_call,
                )

        return block

    def _is_generator_function(self, func_ast_node: TSNode) -> bool:
        """
        Check if function contains yield statements (is a generator)

        MULTI-LANGUAGE SUPPORT (Phase 1 - Python only):
        - Python: yield expr, yield from expr
        - JavaScript/TypeScript: yield expr, yield* expr (TODO: Phase 1.1)

        Args:
            func_ast_node: Function AST node

        Returns:
            True if function contains yield statement

        CRITICAL: This does NOT check yield from in Phase 1
        yield from will be treated as unsupported (warning only)

        Added: 2025-12-09 (Phase 1)
        """

        # DFS to find yield
        def has_yield(node: TSNode) -> bool:
            # Python yield
            if node.type == "yield":
                return True

            # JavaScript/TypeScript yield (Phase 1.1 - TODO)
            if node.type == "yield_expression":
                return True

            # Recurse to children
            for child in node.children:
                if has_yield(child):
                    return True

            return False

        return has_yield(func_ast_node)

    def _is_await_statement(self, stmt: TSNode) -> bool:
        """
        Check if statement contains await expression.

        MULTI-LANGUAGE SUPPORT (SOTA):
        - Python: await expr, result = await expr, return await expr
        - JavaScript/TypeScript: await expr, const result = await expr, return await expr
        - Kotlin: suspend function calls (via coroutine context)

        Args:
            stmt: AST statement node

        Returns:
            True if statement contains await expression

        Updated: 2025-12-09 (SOTA: Multi-language support)
        """
        # ========================================================================
        # PYTHON
        # ========================================================================

        # Direct await expression (Python: await log())
        if stmt.type == "await":
            return True

        # Assignment with await (Python: result = await fetch())
        if stmt.type == "assignment":
            for child in stmt.children:
                if child.type == "await":
                    return True

        # Return with await (Python: return await fetch())
        if stmt.type == "return_statement":
            for child in stmt.children:
                if child.is_named and child.type == "await":
                    return True

        # ========================================================================
        # JAVASCRIPT / TYPESCRIPT
        # ========================================================================

        # JS/TS uses "await_expression" instead of "await"
        if stmt.type == "await_expression":
            return True

        # Expression statement containing await (JS: await fetch();)
        if stmt.type == "expression_statement":
            for child in stmt.children:
                if child.type == "await_expression":
                    return True

        # Variable declaration with await (JS: const result = await fetch();)
        if stmt.type in ("lexical_declaration", "variable_declaration"):
            # Traverse: lexical_declaration -> variable_declarator -> await_expression
            for child in stmt.children:
                if child.type == "variable_declarator":
                    for grandchild in child.children:
                        if grandchild.type == "await_expression":
                            return True

        # Return with await (JS: return await fetch();)
        if stmt.type == "return_statement":
            for child in stmt.children:
                if child.is_named and child.type == "await_expression":
                    return True

        # ========================================================================
        # KOTLIN
        # ========================================================================

        # Kotlin suspend functions (detected via function call to suspend functions)
        # This requires type information - placeholder for future enhancement
        if stmt.type == "call_expression":
            # TODO: Check if callee is suspend function (requires symbol resolution)
            pass

        return False

    def _build_await_blocks(
        self,
        bfg_id: str,
        function_node_id: str,
        await_stmt: TSNode,
        ast: AstTree,
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Build SUSPEND and RESUME blocks for await expression.

        Structure:
        ```
        [ SUSPEND Block ]  (async call initiated)
            │      ↘ (Exception edge added by CFG)
            │       [ CATCH Block (if in try) ]
            ↓ (Success)
        [ RESUME Block ]  (async call completed, result available)
        ```

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            await_stmt: AST await statement node
            ast: AST tree

        Returns:
            (blocks, statement_count)

        Added: 2025-12-08 (SOTA async/await support)
        """
        blocks = []
        stmt_count = 0

        # Extract await expression details
        await_expr, result_var = self._extract_await_details(await_stmt, ast)

        # Create SUSPEND block (async call initiated)
        suspend_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=function_node_id,
            kind=BFGBlockKind.SUSPEND,
            span=ast.get_span(await_stmt),
            ast_node_type=await_stmt.type,
            statement_count=1,
            # Async metadata
            is_async_call=True,
            async_target_expression=await_expr,
            can_throw_exception=True,  # await can reject/throw
        )
        blocks.append(suspend_block)
        stmt_count += 1

        # Create RESUME block (async call completed)
        resume_block = self._create_block(
            bfg_id=bfg_id,
            function_node_id=function_node_id,
            kind=BFGBlockKind.RESUME,
            span=ast.get_span(await_stmt),
            ast_node_type="resume",
            statement_count=1,
            # Async metadata
            resume_from_suspend_id=suspend_block.id,
            async_result_variable=result_var,
        )
        blocks.append(resume_block)
        stmt_count += 1

        # Log await block creation
        if _DEBUG_ENABLED:
            self.logger.debug(
                "bfg_await_blocks_created",
                suspend_block_id=suspend_block.id,
                resume_block_id=resume_block.id,
                await_expression=await_expr,
                result_variable=result_var,
            )

        return blocks, stmt_count

    def _extract_await_details(self, await_stmt: TSNode, ast: AstTree) -> tuple[str, str | None]:
        """
        Extract await expression and result variable from statement.

        MULTI-LANGUAGE SUPPORT (SOTA):
        - Python: `result = await fetch(url)` → ("fetch(url)", "result")
        - Python: `await asyncio.sleep(1)` → ("asyncio.sleep(1)", None)
        - JS/TS: `const data = await fetch()` → ("fetch()", "data")
        - JS/TS: `await sleep(100);` → ("sleep(100)", None)

        Args:
            await_stmt: AST await statement node
            ast: AST tree

        Returns:
            (await_expression, result_variable)

        Updated: 2025-12-09 (SOTA: Multi-language support + deep search)
        """
        result_var = None
        await_expr = "unknown"

        # ========================================================================
        # Find await node (language-specific, deep search for JS/TS)
        # ========================================================================
        await_node = None

        # Direct await
        if await_stmt.type in ("await", "await_expression"):
            await_node = await_stmt
        else:
            # Search children for Python "await" or JS/TS "await_expression"
            for child in await_stmt.children:
                if child.type in ("await", "await_expression"):
                    await_node = child
                    break

            # JS/TS: await may be in grandchild (lexical_declaration -> variable_declarator -> await_expression)
            if not await_node:
                for child in await_stmt.children:
                    for grandchild in child.children:
                        if grandchild.type in ("await", "await_expression"):
                            await_node = grandchild
                            break
                    if await_node:
                        break

        # ========================================================================
        # Extract awaited expression
        # ========================================================================
        if await_node:
            # Python: await -> expression
            # JS/TS: await_expression -> argument field OR first named child

            # Try field name first (JS/TS uses "argument" field)
            argument = await_node.child_by_field_name("argument")
            if argument:
                await_expr = ast.get_text(argument)
            else:
                # Fallback: First named child (Python style)
                for child in await_node.children:
                    if child.is_named:  # Skip "await" keyword token
                        await_expr = ast.get_text(child)
                        break

        # ========================================================================
        # Extract result variable (if assignment)
        # ========================================================================

        # Python: assignment → left → identifier
        if await_stmt.type == "assignment":
            left = await_stmt.child_by_field_name("left")
            if left:
                result_var = ast.get_text(left)

        # JS/TS: lexical_declaration → variable_declarator → name
        elif await_stmt.type in ("lexical_declaration", "variable_declaration"):
            for child in await_stmt.children:
                if child.type == "variable_declarator":
                    # Use field name "name" or "pattern"
                    name = child.child_by_field_name("name") or child.child_by_field_name("pattern")
                    if name:
                        result_var = ast.get_text(name)
                        break

        # Return statement: no result variable
        elif await_stmt.type == "return_statement":
            result_var = None

        return await_expr, result_var
