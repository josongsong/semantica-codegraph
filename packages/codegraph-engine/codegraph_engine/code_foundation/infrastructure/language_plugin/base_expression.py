"""
Base Expression Analyzer

Template Method Pattern for language-agnostic expression analysis.

Architecture:
- BaseExpressionAnalyzer: Common DFG logic (Template Method)
- PythonExpressionAnalyzer: Python AST mappings
- TypeScriptExpressionAnalyzer: TypeScript AST mappings

Design:
1. Common logic: Expression tree building, DFG linking, type enrichment
2. Language-specific: AST node type checking, attribute extraction

Usage:
    class PythonExpressionAnalyzer(BaseExpressionAnalyzer):
        def is_assignment(self, node):
            return node.type in {"assignment", "augmented_assignment"}

        def get_assignment_target(self, node):
            return node.child_by_field_name("left")
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class BaseExpressionAnalyzer(ABC):
    """
    Base class for expression analysis.

    Template Method Pattern:
    - Provides common DFG construction logic
    - Delegates AST-specific operations to subclasses

    Responsibilities:
    - Expression tree building (parent/child links)
    - Variable read/write tracking
    - Type enrichment integration

    Subclass Responsibilities:
    - AST node type checking (is_assignment, is_call, etc.)
    - AST attribute extraction (get_assignment_target, get_call_name, etc.)

    Example:
        class PythonExpressionAnalyzer(BaseExpressionAnalyzer):
            def is_assignment(self, node):
                return node.type == "assignment"

            def get_assignment_target(self, node):
                return node.child_by_field_name("left")
    """

    def __init__(self, lsp_adapter: Any = None):
        """
        Initialize analyzer.

        Args:
            lsp_adapter: LSP adapter for type enrichment (optional)
        """
        self._lsp = lsp_adapter
        self._expr_cache: dict[str, Expression] = {}

    # ================================================================
    # Template Method (Common Logic)
    # ================================================================

    def process_statement(
        self,
        stmt_node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """
        Process single statement and extract expressions.

        Template Method Implementation.

        Args:
            stmt_node: Statement AST node
            block_id: CFG block ID
            function_fqn: Function FQN (None for module-level)
            repo_id: Repository ID
            file_path: File path

        Returns:
            List of Expression entities
        """
        # Assignment (language-specific check)
        if self.is_assignment(stmt_node):
            return self._handle_assignment(stmt_node, block_id, function_fqn, repo_id, file_path)

        # Call (language-specific check)
        if self.is_call(stmt_node):
            return self._handle_call(stmt_node, block_id, function_fqn, repo_id, file_path)

        # Control flow (language-specific check)
        if self.is_control_flow(stmt_node):
            return self._handle_control_flow(stmt_node, block_id, function_fqn, repo_id, file_path)

        # Fallback: traverse generically
        return self._traverse_generic(stmt_node, block_id, function_fqn, repo_id, file_path)

    # ================================================================
    # Template Method Handlers (Common Logic)
    # ================================================================

    def _handle_assignment(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """
        Handle assignment statement.

        Common logic using abstract methods for AST access.
        """
        expressions = []

        # Extract LHS and RHS (language-specific)
        lhs = self.get_assignment_target(node)
        rhs = self.get_assignment_value(node)

        # Process RHS first (reads)
        rhs_start_idx = len(expressions)
        if rhs:
            # Check if RHS is a call - handle specially
            if self.is_call(rhs):
                rhs_exprs = self._handle_call(rhs, block_id, function_fqn, repo_id, file_path)
            else:
                rhs_exprs = self._traverse_generic(rhs, block_id, function_fqn, repo_id, file_path)
            expressions.extend(rhs_exprs)

        # Process LHS (defines_var)
        if lhs and lhs.type == "identifier":
            var_name = self._node_text(lhs)

            # Set defines_var on all RHS expressions (especially CALL)
            if var_name:
                for i in range(rhs_start_idx, len(expressions)):
                    if expressions[i].kind == ExprKind.CALL:
                        expressions[i].defines_var = var_name

            # Create ASSIGN expression
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

    def _handle_call(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle function call."""
        expressions = []

        # Extract call name (language-specific)
        call_name = self.get_call_name(node)

        # Extract arguments (language-specific)
        args = self.get_call_args(node)

        # Process each argument
        arg_expr_ids = []
        for arg in args:
            arg_exprs = self._traverse_generic(arg, block_id, function_fqn, repo_id, file_path)
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

    def _handle_control_flow(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> list[Expression]:
        """Handle control flow statements."""
        # For now, traverse children generically
        return self._traverse_generic(node, block_id, function_fqn, repo_id, file_path)

    def _traverse_generic(
        self,
        node: "TSNode",
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
        parent_expr_id: str | None = None,
    ) -> list[Expression]:
        """Generic AST traversal."""
        expressions = []

        # Try to create expression for this node
        expr = self._create_expression(
            node=node,
            kind=self._infer_expr_kind(node),
            block_id=block_id,
            function_fqn=function_fqn,
            repo_id=repo_id,
            file_path=file_path,
        )

        if expr:
            if parent_expr_id:
                expr.parent_expr_id = parent_expr_id
            expressions.append(expr)
            current_id = expr.id
        else:
            current_id = parent_expr_id

        # Recurse children
        for child in node.children:
            child_exprs = self._traverse_generic(child, block_id, function_fqn, repo_id, file_path, current_id)
            expressions.extend(child_exprs)

        return expressions

    def _create_expression(
        self,
        node: "TSNode",
        kind: ExprKind,
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
    ) -> Expression | None:
        """Create Expression entity from node."""
        if node is None:
            return None

        expr_id = f"expr:{repo_id}:{file_path}:{node.start_point[0] + 1}:{node.start_point[1]}"

        return Expression(
            id=expr_id,
            kind=kind,
            repo_id=repo_id,
            file_path=file_path,
            function_fqn=function_fqn,
            span=self._node_to_span(node),
            block_id=block_id,
        )

    def _infer_expr_kind(self, node: "TSNode") -> ExprKind:
        """Infer ExprKind from node type."""
        # Language-specific checks
        if self.is_call(node):
            return ExprKind.CALL
        if self.is_assignment(node):
            return ExprKind.ASSIGN

        # Generic mapping
        node_type = node.type

        # Binary operations
        if "binary" in node_type or node_type in {"+", "-", "*", "/", "%", "==", "!=", "<", ">"}:
            return ExprKind.BIN_OP

        # Literals
        if node_type in {"integer", "float", "string", "true", "false", "null", "none"}:
            return ExprKind.LITERAL

        # Default
        return ExprKind.NAME_LOAD

    # ================================================================
    # Abstract Methods (Language-Specific)
    # ================================================================

    @abstractmethod
    def get_language_name(self) -> str:
        """
        Get language name.

        Returns:
            Language identifier (e.g., "python", "typescript")
        """
        ...

    @abstractmethod
    def is_assignment(self, node: "TSNode") -> bool:
        """
        Check if node is an assignment statement.

        Args:
            node: Tree-sitter AST node

        Returns:
            True if assignment

        Examples:
            Python: node.type == "assignment"
            TypeScript: node.type == "assignment_expression"
            Java: node.type == "assignment_expression"
        """
        ...

    @abstractmethod
    def is_call(self, node: "TSNode") -> bool:
        """
        Check if node is a function/method call.

        Args:
            node: Tree-sitter AST node

        Returns:
            True if call

        Examples:
            Python: node.type == "call"
            TypeScript: node.type == "call_expression"
            Java: node.type == "method_invocation"
        """
        ...

    @abstractmethod
    def is_control_flow(self, node: "TSNode") -> bool:
        """
        Check if node is a control flow statement.

        Args:
            node: Tree-sitter AST node

        Returns:
            True if control flow (if, while, for, with, try, etc.)
        """
        ...

    @abstractmethod
    def get_assignment_target(self, node: "TSNode") -> "TSNode | None":
        """
        Extract LHS of assignment.

        Args:
            node: Assignment node

        Returns:
            LHS node or None

        Examples:
            Python: node.child_by_field_name("left")
            TypeScript: node.child_by_field_name("left")
        """
        ...

    @abstractmethod
    def get_assignment_value(self, node: "TSNode") -> "TSNode | None":
        """
        Extract RHS of assignment.

        Args:
            node: Assignment node

        Returns:
            RHS node or None

        Examples:
            Python: node.child_by_field_name("right")
            TypeScript: node.child_by_field_name("right")
        """
        ...

    @abstractmethod
    def get_call_name(self, node: "TSNode") -> str:
        """
        Extract function/method name from call.

        Args:
            node: Call node

        Returns:
            Function name

        Examples:
            Python: node.child_by_field_name("function").text
            TypeScript: node.child_by_field_name("function").text
        """
        ...

    @abstractmethod
    def get_call_args(self, node: "TSNode") -> list["TSNode"]:
        """
        Extract arguments from call.

        Args:
            node: Call node

        Returns:
            List of argument nodes

        Examples:
            Python: node.child_by_field_name("arguments").children
            TypeScript: node.child_by_field_name("arguments").children
        """
        ...

    # ================================================================
    # Common Helper Methods (Reusable)
    # ================================================================

    def _node_text(self, node: "TSNode") -> str:
        """Get text content of node."""
        if node is None:
            return ""
        return node.text.decode("utf-8") if isinstance(node.text, bytes) else str(node.text)

    def _node_to_span(self, node: "TSNode") -> "Span":
        """Convert tree-sitter node to Span."""
        from codegraph_engine.code_foundation.infrastructure.ir.models import Span

        return Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )
