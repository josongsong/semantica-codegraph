from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

"""
SOTA Exception Analyzer for Python

Tracks exception handling and propagation:
- try/except blocks
- raise statements
- Exception types
"""


class ExceptionAnalyzer:
    """
    SOTA-grade exception analyzer.

    Tracks:
    - raise statements (exception sources)
    - try/except blocks (exception handlers)
    - Exception types
    """

    def __init__(self):
        self._raises = []
        self._catches = []

    def analyze_function_body(
        self,
        body_node: TSNode,
        get_text_func,
        source_bytes: bytes,
    ) -> dict:
        """
        Analyze exception handling in function body.

        Returns:
            {
                "raises_types": ["ValueError", "CustomError", ...],
                "catches_types": ["Exception", "IOError", ...],
                "has_try": bool,
                "has_raise": bool,
            }
        """
        self._raises = []
        self._catches = []

        self._traverse(body_node, get_text_func, source_bytes)

        return {
            "raises_types": list(set(self._raises)),
            "catches_types": list(set(self._catches)),
            "has_try": len(self._catches) > 0,
            "has_raise": len(self._raises) > 0,
        }

    def _traverse(self, node: TSNode, get_text_func, source_bytes: bytes):
        """Traverse AST to find exception handling."""
        if not node:
            return

        # try/except
        if node.type == "try_statement":
            self._process_try_statement(node, get_text_func, source_bytes)

        # raise
        elif node.type == "raise_statement":
            self._process_raise_statement(node, get_text_func, source_bytes)

        # Recurse
        for child in node.children:
            self._traverse(child, get_text_func, source_bytes)

    def _process_try_statement(self, try_node: TSNode, get_text_func, source_bytes: bytes):
        """Process try/except block."""
        # Find except clauses
        for child in try_node.children:
            if child.type == "except_clause":
                # Get exception type - iterate children to find identifier
                for exc_child in child.children:
                    if exc_child.type == "identifier" or exc_child.type == "dotted_name":
                        exc_name = get_text_func(exc_child, source_bytes)
                        if exc_name and exc_name not in ["except", "as"]:
                            self._catches.append(exc_name)
                            break

    def _process_raise_statement(self, raise_node: TSNode, get_text_func, source_bytes: bytes):
        """Process raise statement."""
        # Get raised exception type
        # raise CustomError("message")
        # First child after 'raise' keyword is typically the exception
        for child in raise_node.children:
            if child.type == "call":
                # CustomError(...)
                # Find function being called (first child of call)
                for call_child in child.children:
                    if call_child.type == "identifier" or call_child.type == "attribute":
                        exc_name = get_text_func(call_child, source_bytes)
                        if exc_name:
                            self._raises.append(exc_name)
                            break
                break
            elif child.type == "identifier":
                # raise existing_exception
                exc_name = get_text_func(child, source_bytes)
                if exc_name and exc_name != "raise":
                    self._raises.append(exc_name)
                    break
