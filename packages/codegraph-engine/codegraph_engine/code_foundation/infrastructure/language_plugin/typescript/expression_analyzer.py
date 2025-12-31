"""
TypeScript Expression Analyzer

BaseExpressionAnalyzer implementation for TypeScript/JavaScript.

AST Type Mappings:
- Assignment: "assignment_expression", "augmented_assignment_expression"
- Call: "call_expression"
- Control Flow: "if_statement", "while_statement", "for_statement", "try_statement"
- Return: "return_statement"
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.language_plugin.base_expression import (
    BaseExpressionAnalyzer,
)

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode


class TypeScriptExpressionAnalyzer(BaseExpressionAnalyzer):
    """
    TypeScript/JavaScript expression analyzer.

    Implements TypeScript-specific AST node type checking.

    AST Node Types (tree-sitter-typescript):
    - assignment_expression: a = b
    - augmented_assignment_expression: a += b
    - call_expression: func(args)
    - expression_statement: wrapper for expressions
    - return_statement: return expr
    - for_statement: for (let i = 0; i < n; i++)
    - try_statement: try { } catch(e) { }
    - if_statement: if (condition) { }
    - while_statement: while (condition) { }
    """

    # AST type constants
    ASSIGNMENT_TYPES = frozenset(
        {
            "assignment_expression",
            "augmented_assignment_expression",
            "lexical_declaration",  # const/let/var x = ...
            "variable_declaration",  # var x = ...
        }
    )
    CALL_TYPES = frozenset({"call_expression"})
    CONTROL_FLOW_TYPES = frozenset(
        {
            "if_statement",
            "while_statement",
            "for_statement",
            "for_in_statement",
            "try_statement",
            "switch_statement",
        }
    )
    RETURN_TYPES = frozenset({"return_statement"})
    EXPRESSION_STATEMENT = "expression_statement"

    # ================================================================
    # Language Identity
    # ================================================================

    def get_language_name(self) -> str:
        """Return 'typescript'."""
        return "typescript"

    # ================================================================
    # AST Node Type Checking
    # ================================================================

    def is_assignment(self, node: "TSNode") -> bool:
        """Check if node is assignment."""
        if node.type in self.ASSIGNMENT_TYPES:
            return True

        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    return True

        return False

    def is_call(self, node: "TSNode") -> bool:
        """Check if node is function call."""
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
        """Extract LHS of assignment."""
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    node = child
                    break

        # Handle lexical_declaration (const/let x = ...)
        if node.type in {"lexical_declaration", "variable_declaration"}:
            # Find variable_declarator
            for child in node.children:
                if child.type == "variable_declarator":
                    # name is the first child
                    return child.child_by_field_name("name")
            return None

        return node.child_by_field_name("left")

    def get_assignment_value(self, node: "TSNode") -> "TSNode | None":
        """Extract RHS of assignment."""
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.ASSIGNMENT_TYPES:
                    node = child
                    break

        # Handle lexical_declaration (const/let x = ...)
        if node.type in {"lexical_declaration", "variable_declaration"}:
            # Find variable_declarator
            for child in node.children:
                if child.type == "variable_declarator":
                    # value is the "value" field
                    return child.child_by_field_name("value")
            return None

        return node.child_by_field_name("right")

    def get_call_name(self, node: "TSNode") -> str:
        """Extract function name from call."""
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
        """Extract arguments from call."""
        if node.type == self.EXPRESSION_STATEMENT:
            for child in node.children:
                if child.type in self.CALL_TYPES:
                    node = child
                    break

        args_node = node.child_by_field_name("arguments")
        if not args_node:
            return []

        return [child for child in args_node.children if child.type != ","]
