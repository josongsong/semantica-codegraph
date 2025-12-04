"""
Python Call Analyzer

Responsible for analyzing function calls and resolving callees in Python code.
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_edge_id, generate_logical_id
from src.contexts.code_foundation.infrastructure.ir.models import Edge, EdgeKind, Node, NodeKind, Span


class PythonCallAnalyzer:
    """
    Analyzes function calls in Python code.

    Responsibilities:
    - Finding call expressions in AST
    - Resolving callee symbols (local, imported, external)
    - Creating CALLS edges
    - Managing external function stubs
    """

    def __init__(
        self,
        nodes: list[Node],
        edges: list[Edge],
        external_functions: dict[str, Node],
        scope: ScopeStack,
    ):
        """
        Initialize call analyzer.

        Args:
            nodes: Shared nodes list
            edges: Shared edges list
            external_functions: Cache of external function nodes
            scope: Current scope stack
        """
        self._nodes = nodes
        self._edges = edges
        self._external_functions = external_functions
        self._scope = scope

    def process_calls_in_block(
        self,
        block_node: TSNode,
        caller_id: str,
        repo_id: str,
        get_span_fn,
        get_node_text_fn,
        source_bytes: bytes,
    ):
        """
        Process function calls in a block and create CALLS edges.

        Args:
            block_node: Block AST node
            caller_id: Caller function/method node ID
            repo_id: Repository identifier
            get_span_fn: Function to extract span from AST node
            get_node_text_fn: Function to extract text from AST node
            source_bytes: Source file bytes
        """
        # Find all call nodes recursively
        calls = self._find_calls_recursive(block_node)

        for call_node in calls:
            self._process_single_call(
                call_node,
                caller_id,
                repo_id,
                get_span_fn,
                get_node_text_fn,
                source_bytes,
            )

    def _find_calls_recursive(self, node: TSNode) -> list[TSNode]:
        """
        Find all call nodes recursively in AST.

        Args:
            node: Starting AST node

        Returns:
            List of call nodes
        """
        calls = []

        if node.type == "call":
            calls.append(node)

        # Recursively search children
        for child in node.children:
            calls.extend(self._find_calls_recursive(child))

        return calls

    def _process_single_call(
        self,
        call_node: TSNode,
        caller_id: str,
        repo_id: str,
        get_span_fn,
        get_node_text_fn,
        source_bytes: bytes,
    ):
        """
        Process a single function call and create CALLS edge.

        Args:
            call_node: call AST node
            caller_id: Caller node ID
            repo_id: Repository identifier
            get_span_fn: Function to extract span
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes
        """
        # Get the function being called
        func_node = call_node.child_by_field_name("function")
        if not func_node:
            return

        # Resolve callee based on function type
        callee_id = None
        callee_name = None

        if func_node.type == "identifier":
            # Simple call: foo()
            callee_name = get_node_text_fn(func_node, source_bytes)
            callee_id = self._resolve_callee(callee_name, repo_id)

        elif func_node.type == "attribute":
            # Attribute call: obj.method() or module.function()
            callee_name = self._get_attribute_name(func_node, get_node_text_fn, source_bytes)
            callee_id = self._resolve_attribute_callee(func_node, callee_name, repo_id, get_node_text_fn, source_bytes)

        # If we resolved a callee, create CALLS edge
        if callee_id and callee_name:
            span = get_span_fn(call_node)
            self._add_calls_edge(caller_id, callee_id, callee_name, span)

    def _resolve_callee(self, name: str, repo_id: str) -> str | None:
        """
        Resolve simple function call to node ID.

        Args:
            name: Function name
            repo_id: Repository identifier

        Returns:
            Callee node ID or None
        """
        # Try to find in current scope
        callee_id = self._scope.lookup_symbol(name)
        if callee_id:
            return callee_id

        # Try to find in imports
        full_symbol = self._scope.resolve_import(name)
        if full_symbol:
            # External function
            return self._get_or_create_external_function(full_symbol, repo_id)

        # Unknown - create external function
        return self._get_or_create_external_function(name, repo_id)

    def _resolve_attribute_callee(
        self,
        attr_node: TSNode,
        full_name: str,
        repo_id: str,
        get_node_text_fn,
        source_bytes: bytes,
    ) -> str | None:
        """
        Resolve attribute call (obj.method or module.func).

        Args:
            attr_node: attribute AST node
            full_name: Full attribute name (e.g., "self.helper" or "os.path.join")
            repo_id: Repository identifier
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes

        Returns:
            Callee node ID or None
        """
        # Get the object part (left side of dot)
        obj_node = attr_node.child_by_field_name("object")
        if not obj_node:
            return None

        obj_name = get_node_text_fn(obj_node, source_bytes)

        # Check if it's 'self' or 'cls' - method call on current class
        if obj_name in ("self", "cls"):
            # Try to find method in current class
            method_node = attr_node.child_by_field_name("attribute")
            if method_node:
                method_name = get_node_text_fn(method_node, source_bytes)
                # Look up in class scope
                class_scope = self._scope.class_scope
                if class_scope:
                    # Try to find in symbols
                    for symbol_name, symbol_id in class_scope.symbols.items():
                        if symbol_name == method_name:
                            return symbol_id

        # Check if it's an imported module
        full_symbol = self._scope.resolve_import(obj_name)
        if full_symbol:
            # It's an import, e.g., np.array() where np = numpy
            attr_name = attr_node.child_by_field_name("attribute")
            if attr_name:
                func_name = get_node_text_fn(attr_name, source_bytes)
                external_name = f"{full_symbol}.{func_name}"
                return self._get_or_create_external_function(external_name, repo_id)

        # Default: external function
        return self._get_or_create_external_function(full_name, repo_id)

    def _get_attribute_name(self, attr_node: TSNode, get_node_text_fn, source_bytes: bytes) -> str:
        """
        Get full attribute name from attribute node.

        Args:
            attr_node: attribute AST node
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes

        Returns:
            Full attribute name (e.g., "obj.method")
        """
        # Recursively build attribute name
        parts: list[str] = []

        def collect_parts(node: TSNode):
            if node.type == "identifier":
                parts.insert(0, get_node_text_fn(node, source_bytes))
            elif node.type == "attribute":
                attr = node.child_by_field_name("attribute")
                if attr:
                    parts.insert(0, get_node_text_fn(attr, source_bytes))
                obj = node.child_by_field_name("object")
                if obj:
                    collect_parts(obj)

        collect_parts(attr_node)
        return ".".join(parts)

    def _get_or_create_external_function(self, name: str, repo_id: str) -> str:
        """
        Get or create external function node.

        IMPORTANT: External functions are repo-scoped to prevent ID conflicts.
        Cache key is (repo_id, name) to ensure different repos get different nodes.

        Args:
            name: External function name
            repo_id: Repository identifier

        Returns:
            External function node ID
        """
        # FIX: HIGH #2 - Use (repo_id, name) as cache key to prevent cross-repo conflicts
        # Each repo should have its own external function nodes
        cache_key = f"{repo_id}:{name}"

        # Check cache
        if cache_key in self._external_functions:
            return self._external_functions[cache_key].id

        # Create new external function node
        external_fqn = f"external.{name}"
        node_id = generate_logical_id(
            repo_id=repo_id,
            kind=NodeKind.FUNCTION,
            file_path="<external>",
            fqn=external_fqn,
        )

        external_node = Node(
            id=node_id,
            kind=NodeKind.FUNCTION,
            fqn=external_fqn,
            file_path="<external>",
            span=Span(0, 0, 0, 0),
            language="python",
            name=name,
            attrs={"is_external": True},
        )

        self._nodes.append(external_node)
        self._external_functions[cache_key] = external_node

        return node_id

    def _add_calls_edge(self, caller_id: str, callee_id: str, callee_name: str, span: Span):
        """
        Add CALLS edge from caller to callee.

        Args:
            caller_id: Caller function/method node ID
            callee_id: Callee function/method node ID
            callee_name: Callee name (for debugging)
            span: Call location
        """
        # Count existing calls from this caller to same callee
        occurrence = sum(
            1 for e in self._edges if e.kind == EdgeKind.CALLS and e.source_id == caller_id and e.target_id == callee_id
        )

        edge_id = generate_edge_id("calls", caller_id, callee_id, occurrence)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CALLS,
            source_id=caller_id,
            target_id=callee_id,
            span=span,
            attrs={"callee_name": callee_name},
        )

        self._edges.append(edge)
