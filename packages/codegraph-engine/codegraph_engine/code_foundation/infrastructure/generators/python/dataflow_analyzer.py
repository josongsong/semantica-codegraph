"""
SOTA Dataflow Analyzer for Python

Tracks READS and WRITES edges for complete def-use chains.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import generate_edge_id_v2
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind


class DataflowAnalyzer:
    """
    SOTA-grade dataflow analyzer.

    Tracks:
    - READS: Variable reads (identifier usage)
    - WRITES: Variable writes (assignments)

    Creates edges from functions/methods to variables.
    """

    def __init__(self, nodes: list, edges: list, scope: ScopeStack):
        self._nodes = nodes
        self._edges = edges
        self._scope = scope

        # Track defined variables for this scope
        self._variables_in_scope = {}  # name → node_id

    def process_dataflow_in_block(
        self,
        body_node: TSNode,
        parent_id: str,
        get_span_func,
        get_text_func,
        source_bytes: bytes,
    ):
        """
        Process READS/WRITES in a function/method body.

        Args:
            body_node: Function body AST node
            parent_id: Parent function/method node ID
            get_span_func: Function to get span from AST node
            get_text_func: Function to get text from AST node
            source_bytes: Source code bytes
        """
        # First pass: collect all variable definitions in this scope
        self._collect_variable_definitions(body_node)

        # Second pass: track reads and writes
        self._track_reads_writes(body_node, parent_id, get_span_func, get_text_func, source_bytes)

    def _collect_variable_definitions(self, node: TSNode):
        """Collect all variable definitions in this block."""
        if not node:
            return

        # Check if this is an assignment
        if node.type == "assignment":
            # Left side is the variable being assigned
            left = node.child_by_field_name("left")
            if left and left.type == "identifier":
                var_name = left.text.decode("utf-8") if left.text else None
                if var_name:
                    # Look up variable in scope
                    var_id = self._scope.lookup_symbol(var_name)
                    if var_id:
                        self._variables_in_scope[var_name] = var_id

        # Recurse
        for child in node.children:
            self._collect_variable_definitions(child)

    def _track_reads_writes(
        self,
        node: TSNode,
        parent_id: str,
        get_span_func,
        get_text_func,
        source_bytes: bytes,
    ):
        """Track all reads and writes."""
        if not node:
            return

        # WRITES: Assignment statements
        if node.type == "assignment":
            self._process_write(node, parent_id, get_span_func)

        # READS: Identifier usage (but not in assignment left side)
        elif node.type == "identifier":
            # Check if this is a read (not a write)
            parent = node.parent

            # Skip if this is the left side of assignment
            if parent and parent.type == "assignment":
                left = parent.child_by_field_name("left")
                if left == node:
                    return  # This is a write, not a read

            # This is a read
            self._process_read(node, parent_id, get_span_func, get_text_func, source_bytes)

        # Recurse
        for child in node.children:
            self._track_reads_writes(child, parent_id, get_span_func, get_text_func, source_bytes)

    def _process_write(self, assignment_node: TSNode, parent_id: str, get_span_func):
        """Process a WRITE (assignment)."""
        left = assignment_node.child_by_field_name("left")
        if not left or left.type != "identifier":
            return

        var_name = left.text.decode("utf-8") if left.text else None
        if not var_name:
            return

        # Look up variable
        var_id = self._variables_in_scope.get(var_name)
        if not var_id:
            var_id = self._scope.lookup_symbol(var_name)

        if var_id:
            # Create WRITES edge
            span = get_span_func(left)
            # RFC-031 Phase B: Use Hash ID
            edge_id = generate_edge_id_v2(
                kind=EdgeKind.WRITES.value,
                source_id=parent_id,
                target_id=var_id,
            )

            write_edge = Edge(
                id=edge_id,
                kind=EdgeKind.WRITES,
                source_id=parent_id,
                target_id=var_id,
                span=span,
                attrs={"var_name": var_name},
            )
            self._edges.append(write_edge)

    def _process_read(
        self,
        identifier_node: TSNode,
        parent_id: str,
        get_span_func,
        get_text_func,
        source_bytes: bytes,
    ):
        """Process a READ (variable usage)."""
        var_name = identifier_node.text.decode("utf-8") if identifier_node.text else None
        if not var_name:
            return

        # Skip common keywords and builtins that aren't variables
        SKIP_NAMES = {
            "True",
            "False",
            "None",
            "self",
            "cls",
            "if",
            "else",
            "elif",
            "for",
            "while",
            "def",
            "class",
            "return",
            "yield",
            "pass",
            "break",
            "continue",
            "import",
            "from",
            "as",
            "with",
            "try",
            "except",
            "finally",
            "raise",
            "assert",
            "del",
            "global",
            "nonlocal",
            "lambda",
        }

        if var_name in SKIP_NAMES:
            return

        # Look up variable
        var_id = self._variables_in_scope.get(var_name)
        if not var_id:
            var_id = self._scope.lookup_symbol(var_name)

        if var_id:
            # Create READS edge
            span = get_span_func(identifier_node)
            # RFC-031 Phase B: Use Hash ID
            edge_id = generate_edge_id_v2(
                kind=EdgeKind.READS.value,
                source_id=parent_id,
                target_id=var_id,
            )

            read_edge = Edge(
                id=edge_id,
                kind=EdgeKind.READS,
                source_id=parent_id,
                target_id=var_id,
                span=span,
                attrs={"var_name": var_name},
            )
            self._edges.append(read_edge)
