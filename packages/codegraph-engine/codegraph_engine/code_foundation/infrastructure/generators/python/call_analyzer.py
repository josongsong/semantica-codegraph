"""
Python Call Analyzer

Responsible for analyzing function calls and resolving callees in Python code.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.generators.python._id_helper import generate_python_node_id
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import generate_edge_id_v2
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, Node, NodeKind, Span


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
        # O(1) occurrence counter for CALLS edges (optimization from O(n²) to O(1))
        self._call_counts: dict[tuple[str, str], int] = {}

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
            # Extract call arguments and kwargs for security analysis
            args, kwargs = self._extract_call_arguments(call_node, get_node_text_fn, source_bytes)
            self._add_calls_edge(caller_id, callee_id, callee_name, span, args, kwargs)

    def _extract_call_arguments(
        self,
        call_node: TSNode,
        get_node_text_fn,
        source_bytes: bytes,
    ) -> tuple[list[str], dict[str, str]]:
        """
        Extract positional and keyword arguments from a call.

        Args:
            call_node: call AST node
            get_node_text_fn: Function to extract text
            source_bytes: Source bytes

        Returns:
            (args, kwargs) tuple where:
            - args: List of positional argument texts
            - kwargs: Dict of keyword argument name → value text

        Example:
            subprocess.run(cmd, shell=True, check=False)
            → args=["cmd"], kwargs={"shell": "True", "check": "False"}
        """
        args: list[str] = []
        kwargs: dict[str, str] = {}

        # Find arguments node
        args_node = call_node.child_by_field_name("arguments")
        if not args_node:
            return args, kwargs

        for child in args_node.children:
            if child.type == "keyword_argument":
                # keyword_argument: name = value
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node:
                    key = get_node_text_fn(name_node, source_bytes)
                    value = get_node_text_fn(value_node, source_bytes)
                    kwargs[key] = value
            elif child.type not in ("(", ")", ","):
                # Positional argument
                arg_text = get_node_text_fn(child, source_bytes)
                args.append(arg_text)

        return args, kwargs

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
            name: External function name (e.g., "dict", "os.path.join", "numpy.array")
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

        # FIX #3: Generate proper FQN and module_path for external nodes
        # This prevents dict/list collision issues (1933x FP)
        external_fqn, module_path = self._generate_external_fqn(name)

        # RFC-031 Phase B
        node_id = generate_python_node_id(
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
            name=name.split(".")[-1],  # Last part is the function name
            module_path=module_path,
            attrs={"is_external": True, "original_name": name},
        )

        self._nodes.append(external_node)
        self._external_functions[cache_key] = external_node

        return node_id

    def _generate_external_fqn(self, name: str) -> tuple[str, str]:
        """
        Generate proper FQN and module_path for external functions.

        Handles:
        - Builtins: dict → builtins.dict, list → builtins.list
        - Stdlib: os.path.join → os.path.join
        - Third-party: numpy.array → numpy.array

        Args:
            name: External function name

        Returns:
            (fqn, module_path) tuple

        Examples:
            "dict" → ("builtins.dict", "builtins")
            "len" → ("builtins.len", "builtins")
            "os.path.join" → ("os.path.join", "os.path")
            "numpy.array" → ("numpy.array", "numpy")
        """
        # Python builtins that don't have a module prefix
        BUILTINS = {
            # Types
            "dict",
            "list",
            "set",
            "tuple",
            "frozenset",
            "str",
            "int",
            "float",
            "bool",
            "bytes",
            "bytearray",
            "object",
            "type",
            "super",
            # Functions
            "len",
            "range",
            "enumerate",
            "zip",
            "map",
            "filter",
            "sorted",
            "reversed",
            "min",
            "max",
            "sum",
            "abs",
            "all",
            "any",
            "iter",
            "next",
            "repr",
            "hash",
            "print",
            "input",
            "open",
            "format",
            "getattr",
            "setattr",
            "hasattr",
            "delattr",
            "isinstance",
            "issubclass",
            "callable",
            "id",
            "vars",
            "dir",
            "globals",
            "locals",
            "eval",
            "exec",
            "compile",
            "chr",
            "ord",
            "bin",
            "hex",
            "oct",
            "round",
            "pow",
            "divmod",
            "complex",
            "staticmethod",
            "classmethod",
            "property",
            "memoryview",
            "slice",
            "Ellipsis",
            "NotImplemented",
            # Exception handling
            "Exception",
            "BaseException",
            "ValueError",
            "TypeError",
            "KeyError",
            "IndexError",
            "AttributeError",
            "RuntimeError",
            "StopIteration",
            "GeneratorExit",
            "AssertionError",
            "ImportError",
            "ModuleNotFoundError",
            "OSError",
            "IOError",
            "FileNotFoundError",
            "PermissionError",
            "TimeoutError",
        }

        # Check if it's a simple builtin (no dot)
        if "." not in name:
            if name in BUILTINS:
                return f"builtins.{name}", "builtins"
            else:
                # Unknown simple name - still prefix with external
                return f"external.{name}", "external"

        # Has module prefix (e.g., os.path.join, numpy.array)
        parts = name.split(".")
        func_name = parts[-1]
        module_path = ".".join(parts[:-1])

        return name, module_path

    def _add_calls_edge(
        self,
        caller_id: str,
        callee_id: str,
        callee_name: str,
        span: Span,
        args: list[str] | None = None,
        kwargs: dict[str, str] | None = None,
    ):
        """
        Add CALLS edge from caller to callee.

        Args:
            caller_id: Caller function/method node ID
            callee_id: Callee function/method node ID
            callee_name: Callee name (for debugging)
            span: Call location
            args: Positional arguments (optional)
            kwargs: Keyword arguments (optional)

        The args and kwargs are stored in Edge.attrs for security analysis:
        - Taint analysis can check if shell=True
        - SQL injection detection can check for parameterized queries
        """
        # Count existing calls from this caller to same callee
        # OPTIMIZATION: O(1) lookup instead of O(n) list scan
        key = (caller_id, callee_id)
        occurrence = self._call_counts.get(key, 0)
        self._call_counts[key] = occurrence + 1

        # RFC-031 Phase B: Use Hash ID
        edge_id = generate_edge_id_v2("CALLS", caller_id, callee_id, occurrence)

        # Build attrs with call context for security analysis
        attrs: dict = {"callee_name": callee_name}
        if args:
            attrs["call_args"] = args
        if kwargs:
            attrs["call_kwargs"] = kwargs
            # Mark security-relevant kwargs for quick filtering
            if "shell" in kwargs:
                attrs["has_shell_kwarg"] = True
                attrs["shell_value"] = kwargs["shell"]

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CALLS,
            source_id=caller_id,
            target_id=callee_id,
            span=span,
            attrs=attrs,
        )

        self._edges.append(edge)
