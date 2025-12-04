"""
Expression Builder

Extracts expression entities from AST with Pyright type information.
"""

from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.models import Span
from src.contexts.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

logger = get_logger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from src.contexts.code_foundation.infrastructure.ir.external_analyzers import ExternalAnalyzer
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
    from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache implementation.

    When cache is full, evicts the least recently used item.
    Includes memory monitoring for safety.
    """

    def __init__(self, max_size: int = 100):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to cache

        Note:
            Each AST tree is typically 5-15MB in memory.
            max_size=100 could consume ~500MB-1.5GB.
            Aligned with BfgBuilder cache size for consistency.
        """
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._eviction_count = 0
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key):
        """
        Get value from cache and mark as recently used.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if key not in self._cache:
            self._miss_count += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hit_count += 1
        return self._cache[key]

    def put(self, key, value):
        """
        Put value in cache, evicting LRU item if needed.

        Args:
            key: Cache key
            value: Value to cache
        """
        if key in self._cache:
            # Update existing, move to end
            self._cache.move_to_end(key)
        else:
            # Add new item
            self._cache[key] = value

            # Evict LRU if over capacity
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)  # Remove oldest (first) item
                self._eviction_count += 1

    def __contains__(self, key):
        """Check if key exists in cache"""
        return key in self._cache

    def __setitem__(self, key, value):
        """Set item using [] syntax"""
        self.put(key, value)

    def __getitem__(self, key):
        """Get item using [] syntax"""
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0.0,
            "hits": self._hit_count,
            "misses": self._miss_count,
            "evictions": self._eviction_count,
            "hit_rate": hit_rate,
        }

    def clear(self):
        """Clear the cache and reset stats"""
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0


class ExpressionBuilder:
    """
    Builds expression entities from AST.

    Extracts expression-level nodes and optionally enriches with Pyright type info.

    Memory Safety:
    - AST cache limited to 100 trees
    - Each tree ~5-15MB, total ~500MB-1.5GB
    - Cache stats available via get_cache_stats()
    - Aligned with BfgBuilder cache size for consistency
    """

    def __init__(self, external_analyzer: "ExternalAnalyzer | None" = None, max_ast_cache_size: int = 100):
        """
        Initialize expression builder.

        Args:
            external_analyzer: Optional Pyright/LSP client for type inference
            max_ast_cache_size: Maximum number of AST trees to cache (default: 100, ~500MB-1.5GB)
                               Aligned with BfgBuilder for consistency
        """
        self.pyright = external_analyzer
        self._expr_counter = 0
        self._ast_cache = LRUCache(max_size=max_ast_cache_size)  # LRU cache for AST by file path

    def get_cache_stats(self) -> dict:
        """
        Get AST cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics
        """
        return self._ast_cache.get_stats()

    def _get_cache_key(self, file_path: str) -> tuple[str, float]:
        """
        Generate cache key with file path and modification time.

        FIX: High #5 - Include file mtime to invalidate cache when file changes

        Args:
            file_path: Path to source file

        Returns:
            Tuple of (file_path, mtime)
        """
        import os

        try:
            mtime = os.path.getmtime(file_path)
        except (OSError, FileNotFoundError):
            # If file doesn't exist or can't get mtime, use 0
            # This ensures we don't cache non-existent files
            mtime = 0.0

        return (file_path, mtime)

    def build_from_block(
        self,
        block: "BasicFlowBlock",
        source_file: "SourceFile",
        ast_tree: "AstTree" = None,
    ) -> list[Expression]:
        """
        Extract all expressions from a BFG block.

        Args:
            block: BFG block
            source_file: Source file
            ast_tree: Optional pre-parsed AST tree (avoids re-parsing, 60-70% improvement)

        Returns:
            List of expression entities
        """
        from src.contexts.code_foundation.infrastructure.parsing import AstTree

        if block.span is None:
            logger.debug(f"[ExprBuilder] Block {block.id} has no span, returning empty")
            return []

        try:
            # Get or parse AST (with caching)
            # FIX: High #5 - Include file mtime in cache key for proper invalidation
            file_path = source_file.file_path
            logger.debug(f"[ExprBuilder] Processing block {block.id}, span={block.span}")

            # Use pre-parsed AST if provided, otherwise parse/cache
            if ast_tree is not None:
                logger.debug(f"[ExprBuilder] Using pre-parsed AST for {file_path} (avoid re-parsing)")
            else:
                # Create cache key with file path and modification time
                cache_key = self._get_cache_key(file_path)

                if cache_key not in self._ast_cache:
                    logger.debug(f"[ExprBuilder] Parsing AST for {file_path}")
                    self._ast_cache[cache_key] = AstTree.parse(source_file)
                ast_tree = self._ast_cache[cache_key]

            # Find statements in block's span
            statements = self._find_statements_in_span(ast_tree, block.span.start_line, block.span.end_line)
            logger.debug(f"[ExprBuilder] Found {len(statements)} statements in span")

            # Extract expressions from each statement (without Pyright)
            expressions: list[Expression] = []
            for stmt_node in statements:
                stmt_exprs = self.build_from_statement(
                    stmt_node=stmt_node,
                    block_id=block.id,
                    function_fqn=block.function_node_id,  # Use function_node_id as FQN
                    ctx_repo_id=source_file.file_path.split("/")[0] if "/" in source_file.file_path else "unknown",
                    ctx_file_path=source_file.file_path,
                    source_file=None,  # Defer Pyright enrichment
                )
                logger.debug(f"[ExprBuilder] Statement {stmt_node.type} generated {len(stmt_exprs)} expressions")
                expressions.extend(stmt_exprs)

            logger.debug(f"[ExprBuilder] Total expressions extracted: {len(expressions)}")

            # Batch enrich with Pyright (one pass over all expressions)
            if self.pyright and expressions:
                self._batch_enrich_with_pyright(expressions, source_file)

            return expressions

        except Exception as e:
            # FIX: Medium #7 - Add detailed error context for debugging
            logger.error(
                f"[ExprBuilder] FAILED to build expressions from block {block.id}: {e}\n"
                f"  Context:\n"
                f"    - File: {source_file.file_path}\n"
                f"    - Block span: {block.span}\n"
                f"    - Function: {block.function_node_id}\n"
                f"    - Block kind: {block.kind if hasattr(block, 'kind') else 'unknown'}\n"
                f"  Stack trace follows:",
                exc_info=True,
            )
            return []

    def _batch_enrich_with_pyright(
        self,
        expressions: list[Expression],
        source_file: "SourceFile",
    ):
        """
        Enrich multiple expressions with Pyright in batch.

        This reduces redundant Pyright calls by leveraging caching.
        Enhanced with:
        - Better type parsing from hover results
        - Definition location tracking for cross-file linking
        - Generic type parameter extraction

        Args:
            expressions: List of expressions to enrich
            source_file: Source file
        """
        if not self.pyright:
            return

        # Group expressions by unique (line, col) to avoid duplicate queries
        unique_positions: dict[tuple[int, int], list[Expression]] = {}
        for expr in expressions:
            if expr.span:
                pos = (expr.span.start_line, expr.span.start_col)
                if pos not in unique_positions:
                    unique_positions[pos] = []
                unique_positions[pos].append(expr)

        enriched_count = 0
        definition_linked = 0

        # Query Pyright for each unique position
        for (line, col), exprs_at_pos in unique_positions.items():
            try:
                hover_info = self.pyright.hover(
                    Path(exprs_at_pos[0].file_path),
                    line,
                    col,
                )

                if hover_info:
                    inferred_type = hover_info.get("type")
                    if inferred_type:
                        # Parse and normalize the type string
                        normalized_type = self._normalize_pyright_type(inferred_type)

                        # Apply to all expressions at this position
                        for expr in exprs_at_pos:
                            expr.inferred_type = normalized_type
                            enriched_count += 1

                            # Extract generic parameters if present
                            if "[" in normalized_type:
                                expr.attrs["generic_params"] = self._extract_generic_params(normalized_type)

                # Try to get definition location for cross-file linking
                try:
                    definition = self.pyright.definition(
                        Path(exprs_at_pos[0].file_path),
                        line,
                        col,
                    )
                    if definition:
                        for expr in exprs_at_pos:
                            expr.attrs["definition_file"] = definition.get("file")
                            expr.attrs["definition_line"] = definition.get("line")
                            expr.attrs["definition_fqn"] = definition.get("fqn")
                            definition_linked += 1
                except Exception:
                    # Definition lookup is optional, don't log as error
                    pass

            except Exception as e:
                # Pyright enrichment is optional, so we don't fail the entire process
                logger.debug(f"Pyright enrichment failed at {line}:{col}: {e}")

        logger.debug(
            f"[ExprBuilder] Pyright enrichment: {enriched_count} types, {definition_linked} definitions linked"
        )

    def _normalize_pyright_type(self, type_str: str) -> str:
        """
        Normalize Pyright type string for consistent matching.

        Handles:
        - Module prefix removal (e.g., "builtins.str" -> "str")
        - Literal type simplification
        - Union type formatting

        Args:
            type_str: Raw type string from Pyright

        Returns:
            Normalized type string
        """
        import re

        if not type_str:
            return ""

        normalized = type_str.strip()

        # Remove builtins prefix
        normalized = re.sub(r"\bbuiltins\.", "", normalized)

        # Remove typing module prefix for common types
        normalized = re.sub(r"\btyping\.(List|Dict|Set|Tuple|Optional|Union|Callable)\b", r"\1", normalized)

        # Simplify Literal types: Literal["foo"] -> str (for matching purposes)
        # But preserve the full type for attrs
        if normalized.startswith("Literal["):
            # Keep original for precise matching
            pass

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"\s*\[\s*", "[", normalized)
        normalized = re.sub(r"\s*\]\s*", "]", normalized)
        normalized = re.sub(r"\s*,\s*", ", ", normalized)
        normalized = re.sub(r"\s*\|\s*", " | ", normalized)

        return normalized

    def _extract_generic_params(self, type_str: str) -> list[str]:
        """
        Extract generic type parameters from type string.

        Args:
            type_str: Type string (e.g., "List[str]", "Dict[str, int]")

        Returns:
            List of parameter type strings
        """
        if "[" not in type_str:
            return []

        # Extract content between brackets
        start = type_str.index("[")
        end = type_str.rindex("]")
        params_str = type_str[start + 1 : end]

        # Split respecting nested brackets
        params = []
        current = []
        depth = 0

        for char in params_str:
            if char == "[":
                depth += 1
                current.append(char)
            elif char == "]":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                param = "".join(current).strip()
                if param:
                    params.append(param)
                current = []
            else:
                current.append(char)

        # Add last parameter
        param = "".join(current).strip()
        if param:
            params.append(param)

        return params

    def build_from_statement(
        self,
        stmt_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None" = None,
    ) -> list[Expression]:
        """
        Extract all expressions from a statement.

        Args:
            stmt_node: Statement AST node
            block_id: CFG block ID
            function_fqn: Function FQN (None for module-level)
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file (for Pyright queries)

        Returns:
            List of expression entities
        """
        expressions: list[Expression] = []

        # Special handling for assignment statements
        # Python tree-sitter wraps assignments in "expression_statement", so check both
        if stmt_node.type == "assignment":
            return self._handle_assignment(stmt_node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)

        # Check if this is an expression_statement containing an assignment
        if stmt_node.type == "expression_statement":
            for child in stmt_node.children:
                if child.type == "assignment":
                    return self._handle_assignment(
                        child, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
                    )

        # Special handling for return statements
        if stmt_node.type == "return_statement":
            return self._handle_return_statement(
                stmt_node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
            )

        def traverse(node: "TSNode", parent_expr_id: str | None = None):
            """Recursively traverse AST and extract expressions"""
            expr = self._create_expression(node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)

            if expr:
                # Link parent-child relationship
                if parent_expr_id:
                    expr.parent_expr_id = parent_expr_id

                expressions.append(expr)
                current_expr_id = expr.id
            else:
                current_expr_id = parent_expr_id

            # Recurse to children
            for child in node.children:
                traverse(child, current_expr_id)

        traverse(stmt_node, None)
        return expressions

    def _handle_assignment(
        self,
        assignment_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None" = None,
    ) -> list[Expression]:
        """
        Handle assignment statement specially to set defines_var.

        Refactored to use helper methods for better maintainability.
        Reduced from 161 lines → ~50 lines (69% reduction).

        Strategy:
        1. Find left and right children
        2. Process right side (reads)
        3. Process left side by type:
           - Simple identifier assignment
           - Tuple unpacking assignment
           - Complex assignment (attribute, subscript)

        Args:
            assignment_node: Assignment AST node
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file

        Returns:
            List of expression entities
        """
        expressions: list[Expression] = []

        # Step 1: Find left and right children
        left_node = None
        right_node = None

        for child in assignment_node.children:
            if child.type == "=":
                continue
            elif left_node is None:
                left_node = child
            else:
                right_node = child
                break

        # Step 2: Process right side first (reads)
        if right_node:
            right_expressions = self._process_right_side_expressions(
                right_node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
            )
            expressions.extend(right_expressions)

        # Step 3: Process left side (defines_var) by type
        if left_node:
            if left_node.type == "identifier":
                # Simple assignment: result = x
                expr = self._create_simple_assignment(
                    left_node, expressions, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
                )
                if expr:
                    expressions.append(expr)

            elif left_node.type in ("pattern_list", "tuple_pattern", "list_pattern"):
                # Tuple unpacking assignment: x, y = a, b
                tuple_expressions = self._create_tuple_unpacking_assignments(
                    left_node, expressions, block_id, function_fqn, ctx_repo_id, ctx_file_path
                )
                expressions.extend(tuple_expressions)

            else:
                # Complex assignment (attribute, subscript, etc.)
                complex_expressions = self._create_complex_assignment(
                    left_node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
                )
                expressions.extend(complex_expressions)

        return expressions

    def _handle_return_statement(
        self,
        return_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None" = None,
    ) -> list[Expression]:
        """
        Handle return statement specially to mark expressions with is_return.

        Return statement structure:
        - return_statement
          - "return" (keyword)
          - expression (the returned value)

        Args:
            return_node: Return statement AST node
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file

        Returns:
            List of expressions with is_return marking
        """
        expressions: list[Expression] = []

        # Find the returned expression (skip "return" keyword)
        return_expr_node = None
        for child in return_node.children:
            if child.type != "return":
                return_expr_node = child
                break

        if return_expr_node is None:
            # Empty return statement
            return expressions

        # Extract expressions from the returned value
        def traverse(node: "TSNode", parent_expr_id: str | None = None):
            expr = self._create_expression(node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)
            if expr:
                # Mark as return expression
                expr.attrs["is_return"] = True

                if parent_expr_id:
                    expr.parent_expr_id = parent_expr_id
                expressions.append(expr)
                current_expr_id = expr.id
            else:
                current_expr_id = parent_expr_id

            for child in node.children:
                traverse(child, current_expr_id)

        traverse(return_expr_node, None)

        return expressions

    def _find_statements_in_span(self, ast_tree: "AstTree", start_line: int, end_line: int) -> list["TSNode"]:
        """
        Find all statement nodes within a line span.

        Args:
            ast_tree: Parsed AST tree
            start_line: Start line (1-indexed)
            end_line: End line (1-indexed)

        Returns:
            List of statement nodes
        """
        statements = []

        def traverse(node):
            if node is None:
                return

            node_start = node.start_point[0] + 1  # Convert to 1-indexed

            # Check if node is a statement type
            if self._is_statement_node(node):
                # Check if node starts within span
                if start_line <= node_start <= end_line:
                    statements.append(node)

            # Always recurse to children (statements may be nested)
            for child in node.children:
                traverse(child)

        # Start from root
        if hasattr(ast_tree, "root"):
            traverse(ast_tree.root)

        return statements

    def _is_statement_node(self, node) -> bool:
        """Check if node is a statement"""
        statement_types = {
            "expression_statement",
            "assignment",
            "return_statement",
            "if_statement",
            "for_statement",
            "while_statement",
            "with_statement",
            "try_statement",
            "raise_statement",
            "assert_statement",
            "delete_statement",
            "pass_statement",
            "break_statement",
            "continue_statement",
            "import_statement",
            "import_from_statement",
        }
        return node.type in statement_types

    def _create_expression(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
        source_file: "SourceFile | None",
    ) -> Expression | None:
        """
        Create expression entity from AST node.

        Args:
            node: AST node
            block_id: CFG block ID
            function_fqn: Function FQN
            repo_id: Repository ID
            file_path: File path
            source_file: Source file

        Returns:
            Expression entity or None if not an expression
        """
        # Map node type to ExprKind
        expr_kind = self._map_node_to_expr_kind(node.type)
        if not expr_kind:
            return None

        # Generate expression ID
        self._expr_counter += 1
        expr_id = f"expr:{repo_id}:{file_path}:{node.start_point[0] + 1}:{node.start_point[1]}:{self._expr_counter}"

        # Create span
        span = Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

        # Extract expression-specific attributes
        attrs = self._extract_attributes(node, expr_kind)

        # Extract DFG information (reads_vars, defines_var)
        reads_vars, defines_var = self._extract_dfg_info(node, expr_kind, attrs)

        # Create expression
        expr = Expression(
            id=expr_id,
            kind=expr_kind,
            repo_id=repo_id,
            file_path=file_path,
            function_fqn=function_fqn,
            span=span,
            block_id=block_id,
            attrs=attrs,
            reads_vars=reads_vars,
            defines_var=defines_var,
        )

        # Enrich with Pyright type information
        if self.pyright and source_file:
            self._enrich_with_pyright(expr, source_file)

        return expr

    def _map_node_to_expr_kind(self, node_type: str) -> ExprKind | None:
        """
        Map tree-sitter node type to ExprKind.

        Args:
            node_type: Tree-sitter node type

        Returns:
            ExprKind or None if not an expression
        """
        mapping = {
            # Value access
            "identifier": ExprKind.NAME_LOAD,
            "attribute": ExprKind.ATTRIBUTE,
            "subscript": ExprKind.SUBSCRIPT,
            # Operations
            "binary_expression": ExprKind.BIN_OP,
            "unary_expression": ExprKind.UNARY_OP,
            "comparison_operator": ExprKind.COMPARE,
            "boolean_operator": ExprKind.BOOL_OP,
            # Calls
            "call": ExprKind.CALL,
            # Literals
            "integer": ExprKind.LITERAL,
            "float": ExprKind.LITERAL,
            "string": ExprKind.LITERAL,
            "true": ExprKind.LITERAL,
            "false": ExprKind.LITERAL,
            "none": ExprKind.LITERAL,
            # Collections
            "list": ExprKind.COLLECTION,
            "dictionary": ExprKind.COLLECTION,
            "set": ExprKind.COLLECTION,
            "tuple": ExprKind.COLLECTION,
            # Special
            "lambda": ExprKind.LAMBDA,
            "list_comprehension": ExprKind.COMPREHENSION,
            "dictionary_comprehension": ExprKind.COMPREHENSION,
            "set_comprehension": ExprKind.COMPREHENSION,
        }

        return mapping.get(node_type)

    # =========================================================================
    # Attribute Extraction - Operator Sets (class-level for fast lookup)
    # =========================================================================
    _BIN_OP_OPERATORS = frozenset({"+", "-", "*", "/", "//", "%", "**", "<<", ">>", "&", "|", "^"})
    _UNARY_OP_OPERATORS = frozenset({"-", "+", "not", "~"})
    _COMPARE_OPERATORS = frozenset({"<", ">", "<=", ">=", "==", "!=", "in", "not in", "is", "is not"})
    _BOOL_OP_OPERATORS = frozenset({"and", "or"})

    def _extract_bin_op_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract binary operation attributes."""
        for child in node.children:
            if child.type in self._BIN_OP_OPERATORS:
                attrs["operator"] = child.type
                break

    def _extract_unary_op_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract unary operation attributes."""
        for child in node.children:
            if child.type in self._UNARY_OP_OPERATORS:
                attrs["operator"] = child.type
                break

    def _extract_compare_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract comparison attributes."""
        operators = [child.type for child in node.children if child.type in self._COMPARE_OPERATORS]
        if operators:
            attrs["operators"] = operators

    def _extract_bool_op_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract boolean operation attributes."""
        for child in node.children:
            if child.type in self._BOOL_OP_OPERATORS:
                attrs["operator"] = child.type
                break

    def _extract_call_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract function call attributes."""
        # Extract callee name
        if node.child_count > 0:
            callee_node = node.children[0]
            if callee_node.type in ("identifier", "attribute"):
                attrs["callee_name"] = callee_node.text.decode("utf-8") if callee_node.text else ""

        # Extract call arguments (for DFG param_to_arg edges)
        call_args = self._extract_call_arguments(node)
        if call_args:
            attrs["call_args"] = call_args

    def _extract_call_arguments(self, node: "TSNode") -> list[str]:
        """Extract argument variable names from function call."""
        call_args: list[str] = []

        for child in node.children:
            if child.type != "argument_list":
                continue

            for arg_child in child.children:
                if arg_child.type == "identifier":
                    arg_name = arg_child.text.decode("utf-8") if arg_child.text else ""
                    if arg_name:
                        call_args.append(arg_name)
                elif arg_child.type == "keyword_argument":
                    kw_arg = self._extract_keyword_arg_value(arg_child)
                    if kw_arg:
                        call_args.append(kw_arg)

        return call_args

    def _extract_keyword_arg_value(self, arg_child: "TSNode") -> str | None:
        """Extract value variable from keyword argument (e.g., y=x returns 'x')."""
        if arg_child.child_count == 0:
            return None

        first_child = arg_child.children[0]
        for kw_child in arg_child.children:
            if kw_child.type == "identifier" and kw_child != first_child:
                return kw_child.text.decode("utf-8") if kw_child.text else None
        return None

    def _extract_attribute_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract attribute access attributes."""
        if node.child_count == 0:
            return

        first_child_end = node.children[0].end_point[1]
        for child in node.children:
            if child.type == "identifier" and child.start_point[1] > first_child_end:
                attrs["attr_name"] = child.text.decode("utf-8") if child.text else ""
                break

    def _extract_name_load_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract variable name attributes."""
        attrs["var_name"] = node.text.decode("utf-8") if node.text else ""

    def _extract_literal_attrs(self, node: "TSNode", attrs: dict) -> None:
        """Extract literal value attributes."""
        attrs["value"] = node.text.decode("utf-8") if node.text else ""
        attrs["value_type"] = node.type

    def _extract_attributes(self, node: "TSNode", expr_kind: ExprKind) -> dict:
        """
        Extract expression-specific attributes from AST node.

        Uses dispatch table pattern for cleaner code and better maintainability.

        Args:
            node: AST node
            expr_kind: Expression kind

        Returns:
            Attributes dictionary
        """
        attrs: dict = {}

        # Dispatch table for attribute extraction
        extractors = {
            ExprKind.BIN_OP: self._extract_bin_op_attrs,
            ExprKind.UNARY_OP: self._extract_unary_op_attrs,
            ExprKind.COMPARE: self._extract_compare_attrs,
            ExprKind.BOOL_OP: self._extract_bool_op_attrs,
            ExprKind.CALL: self._extract_call_attrs,
            ExprKind.ATTRIBUTE: self._extract_attribute_attrs,
            ExprKind.NAME_LOAD: self._extract_name_load_attrs,
            ExprKind.LITERAL: self._extract_literal_attrs,
        }

        extractor = extractors.get(expr_kind)
        if extractor:
            extractor(node, attrs)

        return attrs

    # =========================================================================
    # DFG Extraction Methods (dispatch table pattern)
    # =========================================================================

    def _extract_dfg_name_load(self, node: "TSNode", attrs: dict, reads_vars: list[str]) -> None:
        """Extract DFG info for variable read."""
        var_name = attrs.get("var_name")
        if var_name:
            reads_vars.append(var_name)

    def _extract_dfg_call(self, node: "TSNode", attrs: dict, reads_vars: list[str]) -> None:
        """Extract DFG info for function call."""
        callee_name = attrs.get("callee_name")
        if callee_name:
            reads_vars.append(callee_name)
        reads_vars.extend(attrs.get("call_args", []))

    def _extract_dfg_attribute(self, node: "TSNode", attrs: dict, reads_vars: list[str]) -> None:
        """Extract DFG info for attribute access (obj.field reads obj)."""
        if node.child_count > 0:
            obj_node = node.children[0]
            if obj_node.type == "identifier":
                obj_name = obj_node.text.decode("utf-8") if obj_node.text else ""
                if obj_name:
                    reads_vars.append(obj_name)

    def _extract_dfg_subscript(self, node: "TSNode", attrs: dict, reads_vars: list[str]) -> None:
        """Extract DFG info for subscript access (arr[i] reads both arr and i)."""
        for child in node.children:
            if child.type == "identifier":
                var_name = child.text.decode("utf-8") if child.text else ""
                if var_name:
                    reads_vars.append(var_name)

    def _extract_dfg_comprehension(self, node: "TSNode", attrs: dict, reads_vars: list[str]) -> None:
        """Extract DFG info for comprehension (reads iterable, condition, expression vars)."""
        all_vars = self._extract_identifiers_recursive(node)

        # Deduplicate while preserving order
        seen = set()
        for var in all_vars:
            if var not in seen:
                reads_vars.append(var)
                seen.add(var)

    def _extract_identifiers_recursive(self, ast_node: "TSNode") -> list[str]:
        """Recursively extract all identifier names from AST node."""
        identifiers: list[str] = []
        if ast_node.type == "identifier":
            name = ast_node.text.decode("utf-8") if ast_node.text else ""
            if name:
                identifiers.append(name)
        for child in ast_node.children:
            identifiers.extend(self._extract_identifiers_recursive(child))
        return identifiers

    def _extract_dfg_info(self, node: "TSNode", expr_kind: ExprKind, attrs: dict) -> tuple[list[str], str | None]:
        """
        Extract DFG information (reads_vars, defines_var) from AST node.

        Uses dispatch table pattern for cleaner code structure.

        Args:
            node: AST node
            expr_kind: Expression kind
            attrs: Extracted attributes

        Returns:
            (reads_vars, defines_var)
        """
        reads_vars: list[str] = []
        defines_var: str | None = None

        # Dispatch table for DFG extraction
        dfg_extractors = {
            ExprKind.NAME_LOAD: self._extract_dfg_name_load,
            ExprKind.CALL: self._extract_dfg_call,
            ExprKind.ATTRIBUTE: self._extract_dfg_attribute,
            ExprKind.SUBSCRIPT: self._extract_dfg_subscript,
            ExprKind.COMPREHENSION: self._extract_dfg_comprehension,
        }

        extractor = dfg_extractors.get(expr_kind)
        if extractor:
            extractor(node, attrs, reads_vars)

        # Note: defines_var is set at the parent level (assignment statement)
        return reads_vars, defines_var

    def _enrich_with_pyright(self, expr: Expression, source_file: "SourceFile"):
        """
        Enrich expression with Pyright type information.

        Args:
            expr: Expression entity
            source_file: Source file
        """
        if not self.pyright:
            return

        try:
            # Query Pyright hover
            hover_info = self.pyright.hover(
                Path(expr.file_path),
                expr.span.start_line,
                expr.span.start_col,
            )

            if hover_info:
                inferred_type = hover_info.get("type")
                if inferred_type:
                    expr.inferred_type = inferred_type
                    # Note: Type linking happens in post-processing (TypeLinker)

        except Exception as e:
            # FIX: High - Add logging for better debuggability
            # Pyright enrichment is optional, so we don't fail the entire process
            logger.debug(f"Pyright enrichment failed for expression {expr.id}: {e}")

    # ============================================================
    # Helper methods (refactored from _handle_assignment)
    # ============================================================

    def _process_right_side_expressions(
        self,
        right_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None",
    ) -> list[Expression]:
        """
        Process right side of assignment (reads).

        Recursively traverses right side AST and creates expressions.

        Args:
            right_node: Right side AST node
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file

        Returns:
            List of expressions from right side
        """
        expressions: list[Expression] = []

        def traverse_right(node: "TSNode", parent_expr_id: str | None = None):
            expr = self._create_expression(node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)
            if expr:
                if parent_expr_id:
                    expr.parent_expr_id = parent_expr_id
                expressions.append(expr)
                current_expr_id = expr.id
            else:
                current_expr_id = parent_expr_id

            for child in node.children:
                traverse_right(child, current_expr_id)

        traverse_right(right_node, None)
        return expressions

    def _create_simple_assignment(
        self,
        left_node: "TSNode",
        right_expressions: list[Expression],
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None",
    ) -> Expression | None:
        """
        Create expression for simple assignment (e.g., result = x).

        Args:
            left_node: Left side identifier node
            right_expressions: Expressions from right side
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file

        Returns:
            Expression with defines_var set, or None
        """
        from src.contexts.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        var_name = left_node.text.decode("utf-8") if left_node.text else ""
        if not var_name:
            return None

        # Create expression for left side with defines_var
        expr = self._create_expression(left_node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)
        if not expr:
            return None

        expr.defines_var = var_name

        # Collect reads_vars from right side expressions
        right_reads = [var for expr in right_expressions for var in expr.reads_vars]
        has_call = any(expr.kind == ExprKind.CALL for expr in right_expressions)
        expr.reads_vars = right_reads

        # Mark if right side contains a function call (for DFG edge kind)
        if has_call:
            expr.attrs["has_call_rhs"] = True

        return expr

    def _create_tuple_unpacking_assignments(
        self,
        left_node: "TSNode",
        right_expressions: list[Expression],
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
    ) -> list[Expression]:
        """
        Create expressions for tuple unpacking assignment (e.g., x, y = a, b).

        Args:
            left_node: Left side pattern node
            right_expressions: Expressions from right side
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path

        Returns:
            List of expressions (one per variable in pattern)
        """
        from src.contexts.code_foundation.infrastructure.ir.models import Span
        from src.contexts.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        # Extract all variable names from the pattern
        var_names = []

        def extract_identifiers(node: "TSNode"):
            """Recursively extract identifier names from pattern"""
            if node.type == "identifier":
                name = node.text.decode("utf-8") if node.text else ""
                if name:
                    var_names.append(name)
            else:
                for child in node.children:
                    extract_identifiers(child)

        extract_identifiers(left_node)

        # Collect reads_vars from right side expressions (shared across all targets)
        right_reads = []
        has_call = False
        for right_expr in right_expressions:
            right_reads.extend(right_expr.reads_vars)
            if right_expr.kind == ExprKind.CALL:
                has_call = True

        # Create an expression for each variable in the tuple
        expressions: list[Expression] = []
        for var_name in var_names:
            # Create a minimal expression manually (since _create_expression doesn't handle pattern_list)
            expr_id = f"expr:{ctx_repo_id}:{ctx_file_path}:{left_node.start_point[0] + 1}:{left_node.start_point[1]}"
            expr = Expression(
                id=expr_id,
                kind=ExprKind.NAME_LOAD,  # Treat as name reference
                repo_id=ctx_repo_id,
                file_path=ctx_file_path,
                function_fqn=function_fqn,
                span=Span(
                    start_line=left_node.start_point[0] + 1,
                    start_col=left_node.start_point[1],
                    end_line=left_node.end_point[0] + 1,
                    end_col=left_node.end_point[1],
                ),
                block_id=block_id,
            )

            expr.defines_var = var_name
            expr.reads_vars = right_reads

            # Mark if right side contains a function call
            if has_call:
                expr.attrs["has_call_rhs"] = True

            # Mark as tuple unpacking for tracking
            expr.attrs["is_tuple_unpacking"] = True

            expressions.append(expr)

        return expressions

    def _create_complex_assignment(
        self,
        left_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        ctx_repo_id: str,
        ctx_file_path: str,
        source_file: "SourceFile | None",
    ) -> list[Expression]:
        """
        Create expressions for complex assignment (attribute, subscript, etc.).

        Args:
            left_node: Left side node
            block_id: CFG block ID
            function_fqn: Function FQN
            ctx_repo_id: Repository ID
            ctx_file_path: File path
            source_file: Source file

        Returns:
            List of expressions from left side traversal
        """
        expressions: list[Expression] = []

        def traverse_left(node: "TSNode", parent_expr_id: str | None = None):
            expr = self._create_expression(node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file)
            if expr:
                if parent_expr_id:
                    expr.parent_expr_id = parent_expr_id
                expressions.append(expr)
                current_expr_id = expr.id
            else:
                current_expr_id = parent_expr_id

            for child in node.children:
                traverse_left(child, current_expr_id)

        traverse_left(left_node, None)
        return expressions
