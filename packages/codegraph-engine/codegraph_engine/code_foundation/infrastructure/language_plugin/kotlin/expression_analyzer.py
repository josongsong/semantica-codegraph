"""
Kotlin Expression Analyzer

BaseExpressionAnalyzer implementation for Kotlin.

AST Type Mappings (tree-sitter-kotlin):
- Assignment: "assignment", "directly_assignable_expression"
- Call: "call_expression"
- Control Flow: "if_expression", "when_expression", "for_statement", "while_statement"
- Return: "return_at", "jump_expression"

Kotlin-specific features:
- Null safety: T vs T?
- Extension functions: fun T.method()
- Lambda with receivers: { ... }
- Coroutines: suspend fun
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.language_plugin.base_expression import (
    BaseExpressionAnalyzer,
)

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode


class KotlinExpressionAnalyzer(BaseExpressionAnalyzer):
    """
    Kotlin expression analyzer.

    Implements Kotlin-specific AST node type checking and attribute extraction.

    AST Node Types (tree-sitter-kotlin):
    - assignment: a = b
    - directly_assignable_expression: property delegation
    - call_expression: func(args)
    - navigation_expression: obj.method()
    - return_at: return@label expr
    - jump_expression: return/break/continue
    - for_statement: for (item in source)
    - while_statement: while (condition)
    - do_while_statement: do { } while (condition)
    - if_expression: if (condition) a else b
    - when_expression: when (x) { ... }
    - try_expression: try { } catch { }
    """

    # AST type constants
    ASSIGNMENT_TYPES = frozenset(
        {
            "assignment",
            "directly_assignable_expression",
        }
    )

    CALL_TYPES = frozenset(
        {
            "call_expression",
            "navigation_expression",  # obj.method() 포함
        }
    )

    CONTROL_FLOW_TYPES = frozenset(
        {
            "if_expression",
            "when_expression",
            "for_statement",
            "while_statement",
            "do_while_statement",
            "try_expression",
        }
    )

    RETURN_TYPES = frozenset(
        {
            "return_at",
            "jump_expression",
        }
    )

    EXPRESSION_STATEMENT = "expression"

    # ================================================================
    # Language Identity
    # ================================================================

    def get_language_name(self) -> str:
        """Return 'kotlin'."""
        return "kotlin"

    # ================================================================
    # AST Node Type Checking
    # ================================================================

    def is_assignment(self, node: "TSNode", source_bytes: bytes) -> bool:
        """
        Check if node is an assignment.

        Kotlin assignments:
        - assignment: a = b
        - directly_assignable_expression: property delegation by lazy { }

        Args:
            node: Tree-sitter node
            source_bytes: Source code bytes

        Returns:
            True if assignment
        """
        return node.type in self.ASSIGNMENT_TYPES

    def is_call(self, node: "TSNode", source_bytes: bytes) -> bool:
        """
        Check if node is a call.

        Kotlin calls:
        - call_expression: func(args)
        - navigation_expression: obj.method()

        Args:
            node: Tree-sitter node
            source_bytes: Source code bytes

        Returns:
            True if call
        """
        if node.type in self.CALL_TYPES:
            return True

        # navigation_expression may contain call_expression
        if node.type == "navigation_expression":
            for child in node.children:
                if child.type == "call_suffix":
                    return True

        return False

    def is_control_flow(self, node: "TSNode", source_bytes: bytes) -> bool:
        """Check if node is control flow."""
        return node.type in self.CONTROL_FLOW_TYPES

    # ================================================================
    # Assignment Extraction
    # ================================================================

    def get_assignment_target(self, node: "TSNode", source_bytes: bytes) -> str | None:
        """
        Extract assignment target (left-hand side).

        Kotlin:
        - assignment: left = right
        - directly_assignable_expression: val prop by lazy { expr }

        Args:
            node: Assignment node
            source_bytes: Source code bytes

        Returns:
            Target name or None
        """
        if node.type == "assignment":
            # Find left child
            for child in node.children:
                if child.type == "directly_assignable_expression":
                    return self._node_text(child, source_bytes)
                if child.type == "simple_identifier":
                    return self._node_text(child, source_bytes)

        return None

    def get_assignment_value(self, node: "TSNode", source_bytes: bytes) -> str | None:
        """
        Extract assignment value (right-hand side).

        Args:
            node: Assignment node
            source_bytes: Source code bytes

        Returns:
            Value expression or None
        """
        if node.type == "assignment":
            # Find right child (after "=")
            found_eq = False
            for child in node.children:
                if child.type == "assignment_and_operator" or self._node_text(child, source_bytes) == "=":
                    found_eq = True
                    continue
                if found_eq:
                    return self._node_text(child, source_bytes)

        return None

    # ================================================================
    # Call Extraction
    # ================================================================

    def get_call_name(self, node: "TSNode", source_bytes: bytes) -> str | None:
        """
        Extract call name.

        Kotlin:
        - call_expression: func(args) → "func"
        - navigation_expression: obj.method() → "obj.method"

        Args:
            node: Call node
            source_bytes: Source code bytes

        Returns:
            Call name or None
        """
        if node.type == "call_expression":
            # First child is usually the function name
            for child in node.children:
                if child.type == "simple_identifier":
                    return self._node_text(child, source_bytes)
                if child.type == "navigation_expression":
                    return self._node_text(child, source_bytes)

        if node.type == "navigation_expression":
            # obj.method() → return full text
            return self._node_text(node, source_bytes)

        return None

    def get_call_args(self, node: "TSNode", source_bytes: bytes) -> list[str]:
        """
        Extract call arguments.

        Args:
            node: Call node
            source_bytes: Source code bytes

        Returns:
            List of argument expressions
        """
        args = []

        # Find value_arguments node
        for child in node.children:
            if child.type == "value_arguments":
                for arg_child in child.children:
                    if arg_child.type == "value_argument":
                        # Extract expression
                        for expr_child in arg_child.children:
                            if expr_child.type not in {",", "(", ")"}:
                                args.append(self._node_text(expr_child, source_bytes))

        return args
