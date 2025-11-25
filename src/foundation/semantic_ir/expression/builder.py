"""
Expression Builder

Extracts expression entities from AST with Pyright type information.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ...ir.models import Span
from .models import Expression, ExprKind

if TYPE_CHECKING:
    try:
        from tree_sitter import Node as TSNode
    except ImportError:
        TSNode = None  # type: ignore

    from ...ir.external_analyzers import ExternalAnalyzer
    from ...parsing import AstTree, SourceFile


class ExpressionBuilder:
    """
    Builds expression entities from AST.

    Extracts expression-level nodes and optionally enriches with Pyright type info.
    """

    def __init__(self, external_analyzer: "ExternalAnalyzer | None" = None):
        """
        Initialize expression builder.

        Args:
            external_analyzer: Optional Pyright/LSP client for type inference
        """
        self.pyright = external_analyzer
        self._expr_counter = 0
        self._ast_cache: dict[str, AstTree] = {}  # Cache AST by file path

    def build_from_block(
        self,
        block: "BasicFlowBlock",
        source_file: "SourceFile",
    ) -> list[Expression]:
        """
        Extract all expressions from a BFG block.

        Args:
            block: BFG block
            source_file: Source file

        Returns:
            List of expression entities
        """
        from ...parsing import AstTree

        if block.span is None:
            return []

        try:
            # Get or parse AST (with caching)
            file_path = source_file.path
            if file_path not in self._ast_cache:
                self._ast_cache[file_path] = AstTree.parse(source_file)
            ast_tree = self._ast_cache[file_path]

            # Find statements in block's span
            statements = self._find_statements_in_span(
                ast_tree, block.span.start_line, block.span.end_line
            )

            # Extract expressions from each statement (without Pyright)
            expressions: list[Expression] = []
            for stmt_node in statements:
                stmt_exprs = self.build_from_statement(
                    stmt_node=stmt_node,
                    block_id=block.id,
                    function_fqn=block.function_node_id,  # Use function_node_id as FQN
                    ctx_repo_id=source_file.path.split("/")[0] if "/" in source_file.path else "unknown",
                    ctx_file_path=source_file.path,
                    source_file=None,  # Defer Pyright enrichment
                )
                expressions.extend(stmt_exprs)

            # Batch enrich with Pyright (one pass over all expressions)
            if self.pyright and expressions:
                self._batch_enrich_with_pyright(expressions, source_file)

            return expressions

        except Exception:
            # Silently fail on error
            return []

    def _batch_enrich_with_pyright(
        self,
        expressions: list[Expression],
        source_file: "SourceFile",
    ):
        """
        Enrich multiple expressions with Pyright in batch.

        This reduces redundant Pyright calls by leveraging caching.

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
                        # Apply to all expressions at this position
                        for expr in exprs_at_pos:
                            expr.inferred_type = inferred_type
                            # TODO: Resolve type_id from TypeEntity
                            expr.inferred_type_id = f"type:{inferred_type}"

            except Exception:
                # Silently skip on error
                pass

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

        def traverse(node: "TSNode", parent_expr_id: str | None = None):
            """Recursively traverse AST and extract expressions"""
            expr = self._create_expression(
                node, block_id, function_fqn, ctx_repo_id, ctx_file_path, source_file
            )

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

    def _find_statements_in_span(
        self, ast_tree: "AstTree", start_line: int, end_line: int
    ) -> list["TSNode"]:
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
        expr_id = f"expr:{repo_id}:{file_path}:{node.start_point[0]+1}:{node.start_point[1]}:{self._expr_counter}"

        # Create span
        span = Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )

        # Extract expression-specific attributes
        attrs = self._extract_attributes(node, expr_kind)

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

    def _extract_attributes(
        self, node: "TSNode", expr_kind: ExprKind
    ) -> dict:
        """
        Extract expression-specific attributes from AST node.

        Args:
            node: AST node
            expr_kind: Expression kind

        Returns:
            Attributes dictionary
        """
        attrs: dict = {}

        if expr_kind == ExprKind.BIN_OP:
            # Binary operation: extract operator
            for child in node.children:
                if child.type in ("+", "-", "*", "/", "//", "%", "**", "<<", ">>", "&", "|", "^"):
                    attrs["operator"] = child.type
                    break

        elif expr_kind == ExprKind.UNARY_OP:
            # Unary operation: extract operator
            for child in node.children:
                if child.type in ("-", "+", "not", "~"):
                    attrs["operator"] = child.type
                    break

        elif expr_kind == ExprKind.COMPARE:
            # Comparison: extract operators
            operators = []
            for child in node.children:
                if child.type in ("<", ">", "<=", ">=", "==", "!=", "in", "not in", "is", "is not"):
                    operators.append(child.type)
            if operators:
                attrs["operators"] = operators

        elif expr_kind == ExprKind.BOOL_OP:
            # Boolean operation: extract operator
            for child in node.children:
                if child.type in ("and", "or"):
                    attrs["operator"] = child.type
                    break

        elif expr_kind == ExprKind.CALL:
            # Function call: extract callee name
            if node.child_count > 0:
                callee_node = node.children[0]
                if callee_node.type == "identifier":
                    callee_text = callee_node.text.decode("utf-8") if callee_node.text else ""
                    attrs["callee_name"] = callee_text
                elif callee_node.type == "attribute":
                    # Handle method calls
                    callee_text = callee_node.text.decode("utf-8") if callee_node.text else ""
                    attrs["callee_name"] = callee_text

        elif expr_kind == ExprKind.ATTRIBUTE:
            # Attribute access: extract attribute name
            for child in node.children:
                if child.type == "identifier" and child.start_point[1] > node.children[0].end_point[1]:
                    attr_name = child.text.decode("utf-8") if child.text else ""
                    attrs["attr_name"] = attr_name
                    break

        elif expr_kind == ExprKind.NAME_LOAD:
            # Variable name
            var_name = node.text.decode("utf-8") if node.text else ""
            attrs["var_name"] = var_name

        elif expr_kind == ExprKind.LITERAL:
            # Literal value
            literal_text = node.text.decode("utf-8") if node.text else ""
            attrs["value"] = literal_text
            attrs["value_type"] = node.type

        return attrs

    def _enrich_with_pyright(
        self, expr: Expression, source_file: "SourceFile"
    ):
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
                    # TODO: Convert to TypeEntity and link inferred_type_id

        except Exception:
            # Silently skip on error (Pyright may not be available)
            pass
