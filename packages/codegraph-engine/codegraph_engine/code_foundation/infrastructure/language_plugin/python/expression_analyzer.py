"""
Python Expression Analyzer

BaseExpressionAnalyzer implementation for Python.

AST Type Mappings:
- Assignment: "assignment", "augmented_assignment"
- Call: "call"
- Control Flow: "if_statement", "while_statement", "for_statement", "with_statement"
- Return: "return_statement"
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.language_plugin.base_expression import (
    BaseExpressionAnalyzer,
)

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode


class PythonExpressionAnalyzer(BaseExpressionAnalyzer):
    """
    Python expression analyzer.

    Implements Python-specific AST node type checking and attribute extraction.

    AST Node Types (tree-sitter-python):
    - assignment: a = b
    - augmented_assignment: a += b
    - call: func(args)
    - expression_statement: wrapper for expressions
    - return_statement: return expr
    - for_statement: for item in source:
    - with_statement: with source() as f:
    - if_statement: if condition:
    - while_statement: while condition:
    """

    # AST type constants
    ASSIGNMENT_TYPES = frozenset({"assignment", "augmented_assignment"})
    CALL_TYPES = frozenset({"call"})
    CONTROL_FLOW_TYPES = frozenset(
        {
            "if_statement",
            "while_statement",
            "for_statement",
            "with_statement",
            "try_statement",
        }
    )
    RETURN_TYPES = frozenset({"return_statement"})
    EXPRESSION_STATEMENT = "expression_statement"

    # ================================================================
    # Language Identity
    # ================================================================

    def get_language_name(self) -> str:
        """Return 'python'."""
        return "python"

    # ================================================================
    # AST Node Type Checking
    # ================================================================

    def is_assignment(self, node: "TSNode") -> bool:
        """
        Check if node is assignment.

        Handles:
        - Direct: assignment, augmented_assignment
        - Wrapped: expression_statement > assignment
        """
        if node.type in self.ASSIGNMENT_TYPES:
            return True

        # Check expression_statement wrapper
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    return True

        return False

    def is_call(self, node: "TSNode") -> bool:
        """
        Check if node is function call.

        Handles:
        - Direct: call
        - Wrapped: expression_statement > call
        """
        if node.type in self.CALL_TYPES:
            return True

        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.CALL_TYPES:
                    return True

        return False

    def is_control_flow(self, node: "TSNode") -> bool:
        """Check if node is control flow statement."""
        return node.type in self.CONTROL_FLOW_TYPES

    # ================================================================
    # AST Attribute Extraction
    # ================================================================

    def get_assignment_target(self, node: "TSNode") -> "TSNode | None":
        """
        Extract LHS of assignment.

        Unwraps expression_statement if needed.
        """
        # Unwrap expression_statement
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    node = child
                    break

        return node.child_by_field_name("left")

    def get_assignment_value(self, node: "TSNode") -> "TSNode | None":
        """
        Extract RHS of assignment.

        Unwraps expression_statement if needed.
        """
        # Unwrap expression_statement
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    node = child
                    break

        return node.child_by_field_name("right")

    def get_call_name(self, node: "TSNode") -> str:
        """
        Extract function name from call.

        Handles:
        - Simple: func()
        - Attribute: obj.method()
        """
        # Unwrap expression_statement
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.CALL_TYPES:
                    node = child
                    break

        func_node = node.child_by_field_name("function")
        if func_node:
            return self._node_text(func_node)
        return ""

    def get_call_args(self, node: "TSNode") -> list["TSNode"]:
        """
        Extract arguments from call.

        Returns list of argument nodes.
        """
        # Unwrap expression_statement
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.CALL_TYPES:
                    node = child
                    break

        args_node = node.child_by_field_name("arguments")
        if not args_node:
            return []

        # Filter out punctuation (parentheses, commas)
        return [child for child in args_node.children if child.type != ","]
