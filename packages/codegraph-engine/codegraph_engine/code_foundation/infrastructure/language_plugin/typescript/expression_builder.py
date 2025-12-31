"""
TypeScript Expression Builder

TypeScript-specific expression extraction.

Differences from Python:
- lexical_declaration (const/let/var) vs assignment
- call_expression vs call
- Different AST structure for statements

Key TypeScript AST types:
- lexical_declaration: const/let x = ...
- variable_declaration: var x = ...
- expression_statement: wrapper
- call_expression: func()
- assignment_expression: x = y
- binary_expression: a + b
- return_statement: return x
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.models import Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock

logger = get_logger(__name__)


class TypeScriptExpressionBuilder:
    """
    TypeScript expression builder.

    Extracts expressions from TypeScript AST for DFG/Taint analysis.

    Features:
    - TypeScript-specific AST handling
    - const/let/var declarations
    - Arrow functions
    - Template literals
    - Spread operators
    """

    def __init__(self, lsp_adapter=None):
        """
        Initialize TypeScript expression builder.

        Args:
            lsp_adapter: Optional LSP adapter for type enrichment
        """
        self._lsp = lsp_adapter
        self._expr_counter = 0

    def clear_caches(self):
        """Clear caches (Port compliance)."""
        # RFC: Reset counter for each build session (like Python ExpressionBuilder)
        self._expr_counter = 0

    def build(
        self,
        ir_doc,
        bfg_blocks: list,
        source_map: dict,
    ) -> list[Expression]:
        """
        Build expressions from IR document (Port compliance).

        Args:
            ir_doc: IR document
            bfg_blocks: BFG blocks
            source_map: {file_path: (SourceFile, AstTree)}

        Returns:
            List of expressions
        """
        all_expressions = []

        # RFC-031: Build node lookup map for Hash ID
        node_lookup = {n.id: n for n in ir_doc.nodes} if ir_doc else {}

        for block in bfg_blocks:
            # Extract file_path from function_node_id
            func_id = getattr(block, "function_node_id", None)
            if not func_id:
                continue

            # RFC-031: For Hash ID, lookup Node's canonical fields
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.id_utils import extract_file_path

            extracted_path = extract_file_path(func_id)

            # RFC-031: If Hash ID, get file_path from Node
            if extracted_path == "<hash_id>" and func_id in node_lookup:
                node = node_lookup[func_id]
                extracted_path = node.file_path
                logger.debug(
                    "expression_build_hash_id_lookup",
                    func_id=func_id[:50],
                    file_path=extracted_path,
                )

            if not extracted_path or extracted_path == "<hash_id>":
                logger.debug(
                    "expression_build_skip_no_path",
                    block_id=block.id,
                    function_node_id=func_id,
                )
                continue

            # Match against source_map with exact and fuzzy strategies
            source_data = None

            # Strategy 1: Exact match (relative path)
            if extracted_path in source_map:
                source_data = source_map[extracted_path]

            # Strategy 2: Basename match (for absolute paths)
            if not source_data:
                from pathlib import Path

                extracted_basename = Path(extracted_path).name

                for source_key, source_val in source_map.items():
                    source_basename = Path(source_key).name
                    if source_basename == extracted_basename:
                        source_data = source_val
                        break

            if not source_data:
                logger.debug(
                    "expression_build_skip_no_source",
                    block_id=block.id,
                    function_node_id=func_id,
                    extracted_path=extracted_path,
                    source_map_keys=list(source_map.keys()),
                )
                continue

            source_file, ast_tree = source_data

            # Build from block
            block_exprs = self.build_from_block(block, source_file, ast_tree)
            all_expressions.extend(block_exprs)

        return all_expressions

    def build_from_block(
        self,
        block: "BasicFlowBlock",
        source_file: "SourceFile",
        ast_tree=None,
        _defer_pyright: bool = False,
    ) -> list[Expression]:
        """
        Extract expressions from BFG block.

        Args:
            block: BFG block
            source_file: Source file
            ast_tree: Pre-parsed AST tree
            _defer_pyright: Defer Pyright enrichment

        Returns:
            List of expressions
        """
        if block.span is None:
            return []

        from codegraph_engine.code_foundation.infrastructure.parsing import AstTree

        # Parse AST if not provided
        if ast_tree is None:
            ast_tree = AstTree.parse(source_file)

        # Get statements in block span
        statements = self._get_statements_in_span(
            ast_tree.root,
            block.span.start_line,
            block.span.end_line,
        )

        # Extract repo_id from function_node_id using parse_node_id()
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.id_utils import parse_node_id as parse_id

        parsed_func_id = parse_id(block.function_node_id)
        if not parsed_func_id or not parsed_func_id.is_valid:
            logger.warning(
                "expression_build_invalid_function_id",
                block_id=block.id,
                function_node_id=block.function_node_id,
            )
            # Fallback: extract from file path (last resort)
            repo_id = "unknown"
        else:
            repo_id = parsed_func_id.repo_id

        # Extract expressions from each statement
        expressions = []
        for stmt_node in statements:
            stmt_exprs = self._process_statement(
                stmt_node=stmt_node,
                block_id=block.id,
                function_fqn=block.function_node_id,
                repo_id=repo_id,
                file_path=source_file.file_path,
            )
            expressions.extend(stmt_exprs)

        return expressions

    def _get_statements_in_span(
        self,
        root: "TSNode",
        start_line: int,
        end_line: int,
    ) -> list["TSNode"]:
        """
        Get all statement nodes in line range.

        TypeScript statement types:
        - lexical_declaration (const/let)
        - variable_declaration (var)
        - expression_statement
        - return_statement
        - if_statement, while_statement, for_statement
        """
        statements = []

        STATEMENT_TYPES = {
            "lexical_declaration",
            "variable_declaration",
            "expression_statement",
            "return_statement",
            "if_statement",
            "while_statement",
            "for_statement",
            "for_in_statement",
            "try_statement",
        }

        def traverse(node: "TSNode"):
            # Check if statement in range
            node_start = node.start_point[0] + 1
            node_end = node.end_point[0] + 1

            if node.type in STATEMENT_TYPES:
                if start_line <= node_start <= end_line:
                    statements.append(node)
                    return  # Don't recurse into statement

            # Recurse children
            for child in node.children:
                traverse(child)

        traverse(root)
        return statements

    def _process_statement(
        self,
        stmt_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """
        Process TypeScript statement.

        Handles:
        - lexical_declaration: const x = foo()
        - expression_statement: foo()
        - return_statement: return x
        """
        expressions = []

        # lexical_declaration (const/let x = ...)
        if stmt_node.type in {"lexical_declaration", "variable_declaration"}:
            exprs = self._handle_variable_declaration(stmt_node, block_id, function_fqn, repo_id, file_path)
            expressions.extend(exprs)

        # expression_statement
        elif stmt_node.type == "expression_statement":
            # Process child expression
            for child in stmt_node.children:
                if child.type == "call_expression":
                    exprs = self._handle_call(child, block_id, function_fqn, repo_id, file_path)
                    expressions.extend(exprs)
                elif child.type == "assignment_expression":
                    exprs = self._handle_assignment(child, block_id, function_fqn, repo_id, file_path)
                    expressions.extend(exprs)

        # return_statement
        elif stmt_node.type == "return_statement":
            exprs = self._handle_return(stmt_node, block_id, function_fqn, repo_id, file_path)
            expressions.extend(exprs)

        return expressions

    def _handle_variable_declaration(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle const/let/var x = value."""
        expressions = []

        # Find variable_declarator
        for child in node.children:
            if child.type == "variable_declarator":
                # name
                name_node = child.child_by_field_name("name")
                var_name = self._node_text(name_node) if name_node else None

                # value
                value_node = child.child_by_field_name("value")
                if value_node:
                    # Process RHS
                    if value_node.type == "call_expression":
                        rhs_exprs = self._handle_call(value_node, block_id, function_fqn, repo_id, file_path)
                    else:
                        rhs_exprs = self._traverse_generic(value_node, block_id, function_fqn, repo_id, file_path)

                    # Set defines_var
                    if var_name:
                        for e in rhs_exprs:
                            if e.kind == ExprKind.CALL:
                                e.defines_var = var_name

                    expressions.extend(rhs_exprs)

                # Create ASSIGN expression
                if name_node and var_name:
                    expr = self._create_expression(
                        node=name_node,
                        kind=ExprKind.ASSIGN,
                        block_id=block_id,
                        function_fqn=function_fqn,
                        repo_id=repo_id,
                        file_path=file_path,
                    )
                    if expr:
                        expr.defines_var = var_name
                        expressions.append(expr)

        return expressions

    def _handle_call(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle call_expression."""
        expressions = []

        # Get function node
        func_node = node.child_by_field_name("function")
        call_name = self._node_text(func_node) if func_node else ""

        # Get arguments
        args_node = node.child_by_field_name("arguments")
        arg_expr_ids = []

        if args_node:
            for child in args_node.children:
                if child.type not in {",", "(", ")"}:
                    arg_exprs = self._traverse_generic(child, block_id, function_fqn, repo_id, file_path)
                    expressions.extend(arg_exprs)
                    if arg_exprs:
                        arg_expr_ids.append(arg_exprs[0].id)

        # Create CALL expression
        expr = self._create_expression(
            node=node,
            kind=ExprKind.CALL,
            block_id=block_id,
            function_fqn=function_fqn,
            repo_id=repo_id,
            file_path=file_path,
        )
        if expr:
            expr.attrs["callee_name"] = call_name
            expr.attrs["arg_expr_ids"] = arg_expr_ids
            expressions.append(expr)

        return expressions

    def _handle_assignment(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle assignment_expression."""
        expressions = []

        # LHS
        lhs = node.child_by_field_name("left")
        var_name = self._node_text(lhs) if lhs else None

        # RHS
        rhs = node.child_by_field_name("right")
        if rhs:
            if rhs.type == "call_expression":
                rhs_exprs = self._handle_call(rhs, block_id, function_fqn, repo_id, file_path)
            else:
                rhs_exprs = self._traverse_generic(rhs, block_id, function_fqn, repo_id, file_path)

            if var_name:
                for e in rhs_exprs:
                    if e.kind == ExprKind.CALL:
                        e.defines_var = var_name

            expressions.extend(rhs_exprs)

        # Create ASSIGN
        if lhs and var_name:
            expr = self._create_expression(
                node=lhs,
                kind=ExprKind.ASSIGN,
                block_id=block_id,
                function_fqn=function_fqn,
                repo_id=repo_id,
                file_path=file_path,
            )
            if expr:
                expr.defines_var = var_name
                expressions.append(expr)

        return expressions

    def _handle_return(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle return_statement."""
        # Process return value
        for child in node.children:
            if child.type != "return":
                return self._traverse_generic(child, block_id, function_fqn, repo_id, file_path)
        return []

    def _traverse_generic(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Generic traversal."""
        expressions = []

        # Try to create expression
        kind = self._infer_kind(node)
        expr = self._create_expression(node, kind, block_id, function_fqn, repo_id, file_path)
        if expr:
            expressions.append(expr)

        # Recurse
        for child in node.children:
            child_exprs = self._traverse_generic(child, block_id, function_fqn, repo_id, file_path)
            expressions.extend(child_exprs)

        return expressions

    def _infer_kind(self, node: "TSNode") -> ExprKind:
        """Infer ExprKind from TypeScript AST."""
        if node.type == "call_expression":
            return ExprKind.CALL
        if node.type == "identifier":
            return ExprKind.NAME_LOAD
        if node.type in {"number", "string", "true", "false", "null"}:
            return ExprKind.LITERAL
        if node.type == "binary_expression":
            return ExprKind.BIN_OP
        return ExprKind.NAME_LOAD

    def _create_expression(
        self,
        node: "TSNode",
        kind: ExprKind,
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> Expression | None:
        """Create Expression entity."""
        if node is None:
            return None

        self._expr_counter += 1
        # RFC: Expression ID 형식 통일 - Python과 동일하게 counter 포함
        expr_id = f"expr:{repo_id}:{file_path}:{node.start_point[0] + 1}:{node.start_point[1]}:{self._expr_counter}"

        return Expression(
            id=expr_id,
            kind=kind,
            repo_id=repo_id,
            file_path=file_path,
            function_fqn=function_fqn,
            span=Span(
                start_line=node.start_point[0] + 1,
                start_col=node.start_point[1],
                end_line=node.end_point[0] + 1,
                end_col=node.end_point[1],
            ),
            block_id=block_id,
        )

    def _node_text(self, node: "TSNode") -> str:
        """Get node text."""
        if node is None:
            return ""
        return node.text.decode("utf-8") if isinstance(node.text, bytes) else str(node.text)
