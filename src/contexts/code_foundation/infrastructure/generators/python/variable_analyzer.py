"""
Python Variable Analyzer

Responsible for analyzing variable declarations and assignments in Python code.
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_logical_id
from src.contexts.code_foundation.infrastructure.ir.models import Node, NodeKind


class PythonVariableAnalyzer:
    """
    Analyzes variables in Python code.

    Responsibilities:
    - Variable declarations from assignments
    - Local variable node creation
    - Scope registration
    """

    def __init__(
        self,
        nodes: list[Node],
        scope: ScopeStack,
        add_contains_edge_fn,
    ):
        """
        Initialize variable analyzer.

        Args:
            nodes: Shared nodes list
            scope: Current scope stack
            add_contains_edge_fn: Function to add CONTAINS edges
        """
        self._nodes = nodes
        self._scope = scope
        self._add_contains_edge = add_contains_edge_fn

    def process_variables_in_block(
        self,
        block_node: TSNode,
        function_id: str,
        repo_id: str,
        file_path: str,
        language: str,
        module_fqn: str,
        get_span_fn,
        get_node_text_fn,
        source_bytes: bytes,
        find_child_by_type_fn,
    ):
        """
        Process variable assignments in function body.

        Args:
            block_node: Function body block AST node
            function_id: Parent function node ID
            repo_id: Repository identifier
            file_path: Source file path
            language: Programming language
            module_fqn: Module FQN
            get_span_fn: Function to extract span from AST node
            get_node_text_fn: Function to extract text from AST node
            source_bytes: Source file bytes
            find_child_by_type_fn: Function to find child by type
        """
        # Find all assignments in the block
        for child in block_node.children:
            if child.type == "expression_statement":
                # Check if it contains an assignment
                assignment = find_child_by_type_fn(child, "assignment")
                if assignment:
                    self._process_assignment(
                        assignment,
                        function_id,
                        repo_id,
                        file_path,
                        language,
                        module_fqn,
                        get_span_fn,
                        get_node_text_fn,
                        source_bytes,
                    )
            elif child.type == "assignment":
                self._process_assignment(
                    child,
                    function_id,
                    repo_id,
                    file_path,
                    language,
                    module_fqn,
                    get_span_fn,
                    get_node_text_fn,
                    source_bytes,
                )

            # Recursively process nested blocks (if, for, while, etc.)
            for nested in child.children:
                if nested.type == "block":
                    self.process_variables_in_block(
                        nested,
                        function_id,
                        repo_id,
                        file_path,
                        language,
                        module_fqn,
                        get_span_fn,
                        get_node_text_fn,
                        source_bytes,
                        find_child_by_type_fn,
                    )

    def _process_assignment(
        self,
        assignment_node: TSNode,
        function_id: str,
        repo_id: str,
        file_path: str,
        language: str,
        module_fqn: str,
        get_span_fn,
        get_node_text_fn,
        source_bytes: bytes,
    ):
        """
        Process single assignment and create Variable node.

        Args:
            assignment_node: assignment AST node
            function_id: Parent function node ID
            repo_id: Repository identifier
            file_path: Source file path
            language: Programming language
            module_fqn: Module FQN
            get_span_fn: Function to extract span
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes
        """
        # Get left side (variable name)
        left_node = assignment_node.child_by_field_name("left")
        if not left_node:
            return

        # Only handle simple identifier assignments for now
        if left_node.type != "identifier":
            return

        var_name = get_node_text_fn(left_node, source_bytes)

        # Check if already defined in this scope
        existing_var_id = self._scope.lookup_symbol(var_name)
        if existing_var_id:
            # Already defined - this is a reassignment
            # Track the reassignment location in the existing variable node's attrs
            span = get_span_fn(left_node)
            for node in self._nodes:
                if node.id == existing_var_id:
                    # Add reassignment location to attrs
                    if "reassignments" not in node.attrs:
                        node.attrs["reassignments"] = []
                    node.attrs["reassignments"].append(
                        {
                            "line": span.start_line,
                            "column": span.start_col,
                        }
                    )
                    break
            return

        # Build FQN
        var_fqn = self._scope.build_fqn(var_name)

        # Generate node ID
        span = get_span_fn(left_node)
        node_id = generate_logical_id(
            repo_id=repo_id,
            kind=NodeKind.VARIABLE,
            file_path=file_path,
            fqn=var_fqn,
        )

        # Create Variable node
        var_node = Node(
            id=node_id,
            kind=NodeKind.VARIABLE,
            fqn=var_fqn,
            file_path=file_path,
            span=span,
            language=language,
            name=var_name,
            module_path=module_fqn,
            parent_id=function_id,
            attrs={"var_kind": "local"},
        )

        self._nodes.append(var_node)

        # Add CONTAINS edge
        self._add_contains_edge(function_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(var_name, node_id)
