"""
Python IR Generator

Converts Python AST (tree-sitter) to IR.

Enhanced with:
- Pyright integration for advanced type resolution (optional)
"""

from typing import TYPE_CHECKING

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.contexts.code_foundation.infrastructure.generators.base import IRGenerator
from src.contexts.code_foundation.infrastructure.generators.python import (
    PythonCallAnalyzer,
    PythonLambdaAnalyzer,
    PythonSignatureBuilder,
    PythonVariableAnalyzer,
)
from src.contexts.code_foundation.infrastructure.generators.python.analyzers import (
    ClassAnalyzer,
    FunctionAnalyzer,
    ImportAnalyzer,
    ModuleAnalyzer,
)
from src.contexts.code_foundation.infrastructure.generators.python.builders.edge_builder import EdgeBuilder
from src.contexts.code_foundation.infrastructure.generators.python.dataflow_analyzer import DataflowAnalyzer
from src.contexts.code_foundation.infrastructure.generators.python.exception_analyzer import ExceptionAnalyzer
from src.contexts.code_foundation.infrastructure.generators.python.override_analyzer import analyze_method_overrides
from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.ir.id_strategy import (
    generate_edge_id,
    generate_logical_id,
)
from src.contexts.code_foundation.infrastructure.ir.models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
from src.contexts.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.models import TypeEntity
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.external_analyzers import ExternalAnalyzer

# Python-specific Tree-sitter node types
PYTHON_BRANCH_TYPES = {
    "if_statement",
    "elif_clause",
    "match_statement",
    "case_clause",
}

PYTHON_LOOP_TYPES = {
    "for_statement",
    "while_statement",
}

PYTHON_TRY_TYPES = {
    "try_statement",
}

# Parameters to skip during processing
SKIP_PARAMS = frozenset({"self", "cls"})


class PythonIRGenerator(IRGenerator):
    """
    Python-specific IR generator using tree-sitter-python.

    Features:
    - Full node generation (File/Class/Function/Variable/Field/Import)
    - Edge generation (CONTAINS/CALLS/IMPORTS)
    - Type resolution (RAW/BUILTIN/LOCAL/EXTERNAL via Pyright)
    - Signature building
    - CFG generation
    - External function handling
    """

    def __init__(self, repo_id: str, external_analyzer: "ExternalAnalyzer | None" = None):
        """
        Initialize Python generator.

        Args:
            repo_id: Repository identifier
            external_analyzer: Optional external type checker (Pyright/Mypy)
        """
        super().__init__(repo_id)

        # Collections for IR entities
        self._nodes: list[Node] = []
        self._edges: list[Edge] = []
        self._types: dict[str, TypeEntity] = {}  # type_id -> TypeEntity
        self._signatures: dict[str, SignatureEntity] = {}  # sig_id -> SignatureEntity

        # External functions cache
        self._external_functions: dict[str, Node] = {}  # name -> Node

        # Type resolver (with optional external analyzer)
        self._type_resolver = TypeResolver(repo_id, external_analyzer)
        self._external_analyzer = external_analyzer

        # Scope tracking (initialized in generate())
        self._scope: ScopeStack

        # Source reference (initialized in generate())
        self._source: SourceFile
        self._source_bytes: bytes
        self._ast: AstTree

        # Specialized builders (initialized lazily in generate())
        self._signature_builder: PythonSignatureBuilder | None = None
        self._variable_analyzer: PythonVariableAnalyzer | None = None
        self._call_analyzer: PythonCallAnalyzer | None = None
        self._lambda_analyzer: PythonLambdaAnalyzer | None = None

        # New analyzers (initialized lazily in generate())
        self._edge_builder: EdgeBuilder | None = None
        self._module_analyzer: ModuleAnalyzer | None = None
        self._import_analyzer: ImportAnalyzer | None = None
        self._class_analyzer: ClassAnalyzer | None = None
        self._function_analyzer: FunctionAnalyzer | None = None

        # Performance timing (for profiling)
        self._timings: dict[str, float] = {}

    def generate(
        self,
        source: SourceFile,
        snapshot_id: str,
        old_content: str | None = None,
        diff_text: str | None = None,
        ast: AstTree | None = None,
    ) -> IRDocument:
        """
        Generate IR document from Python source file.

        OPTIMIZATION: Can accept pre-parsed AST to avoid duplicate parsing.

        Args:
            source: Python source file
            snapshot_id: Snapshot identifier
            old_content: Previous file content (for incremental parsing)
            diff_text: Unified diff text (for incremental parsing)
            ast: Pre-parsed AST tree (optional, avoids re-parsing)

        Returns:
            Complete IR document
        """
        import time

        # Reset state
        self._nodes = []
        self._edges = []
        self._types = {}
        self._signatures = {}
        self._external_functions = {}
        self._timings = {
            "parsing_ms": 0.0,
            "ast_traverse_ms": 0.0,
            "function_process_ms": 0.0,
            "class_process_ms": 0.0,
            "call_analysis_ms": 0.0,
            "variable_analysis_ms": 0.0,
            "signature_build_ms": 0.0,
            "type_resolve_ms": 0.0,
            # Function processing breakdown
            "func_metadata_ms": 0.0,  # Name, FQN, span, docstring
            "func_node_creation_ms": 0.0,  # Node object creation
            "func_edge_scope_ms": 0.0,  # Edge creation, scope ops
            "func_param_ms": 0.0,  # Parameter processing
            "func_cf_summary_ms": 0.0,  # CF summary calculation
            "other_ms": 0.0,
        }

        # Store source
        self._source = source
        self._source_bytes = source.content.encode(source.encoding)

        # Parse AST (or use provided AST)
        # OPTIMIZATION: Accept pre-parsed AST to avoid duplicate parsing
        parse_start = time.perf_counter()
        if ast is not None:
            # Use provided AST (avoids re-parsing)
            self._ast = ast
            self._timings["parsing_ms"] = 0.0  # No parsing needed
        elif old_content is not None and diff_text is not None:
            # Incremental parsing
            self._ast = AstTree.parse_incremental(source, old_content, diff_text)
            self._timings["parsing_ms"] = (time.perf_counter() - parse_start) * 1000
        else:
            # Full parsing
            self._ast = AstTree.parse(source)
            self._timings["parsing_ms"] = (time.perf_counter() - parse_start) * 1000

        # Initialize scope with module FQN
        module_fqn = self._get_module_fqn(source.file_path)
        self._scope = ScopeStack(module_fqn)

        # Initialize specialized builders
        self._signature_builder = PythonSignatureBuilder(self._type_resolver, self._types)
        self._variable_analyzer = PythonVariableAnalyzer(self._nodes, self._scope, self._add_contains_edge)
        self._call_analyzer = PythonCallAnalyzer(self._nodes, self._edges, self._external_functions, self._scope)
        self._lambda_analyzer = PythonLambdaAnalyzer()
        self._dataflow_analyzer = DataflowAnalyzer(self._nodes, self._edges, self._scope)
        self._exception_analyzer = ExceptionAnalyzer()

        # Initialize new analyzers
        self._edge_builder = EdgeBuilder(self._edges)
        self._module_analyzer = ModuleAnalyzer(self.repo_id, self._nodes)
        self._import_analyzer = ImportAnalyzer(
            self.repo_id, self._nodes, self._scope, self._edge_builder, source, self._source_bytes, self._ast
        )
        self._class_analyzer = ClassAnalyzer(
            self.repo_id,
            self._nodes,
            self._edges,
            self._scope,
            self._edge_builder,
            self._type_resolver,
            self._types,
            source,
            self._source_bytes,
            self._ast,
            self._timings,
        )
        self._function_analyzer = FunctionAnalyzer(
            repo_id=self.repo_id,
            nodes=self._nodes,
            edges=self._edges,
            scope=self._scope,
            edge_builder=self._edge_builder,
            type_resolver=self._type_resolver,
            signature_builder=self._signature_builder,
            variable_analyzer=self._variable_analyzer,
            call_analyzer=self._call_analyzer,
            lambda_analyzer=self._lambda_analyzer,
            dataflow_analyzer=self._dataflow_analyzer,
            exception_analyzer=self._exception_analyzer,
            types=self._types,
            signatures=self._signatures,
            source=source,
            source_bytes=self._source_bytes,
            ast=self._ast,
            timings=self._timings,
        )

        # Generate IR
        gen_start = time.perf_counter()
        # Generate FILE node using ModuleAnalyzer
        file_node = self._module_analyzer.generate_file_node(source, module_fqn)
        self._scope.module.node_id = file_node.id
        self._traverse_ast(self._ast.root)
        gen_time = (time.perf_counter() - gen_start) * 1000

        # Calculate "other" time (AST traversal overhead + misc)
        # Note: function_process_ms includes call_analysis, variable_analysis, signature_build
        # So we only count top-level function/class processing times
        measured_time = self._timings["function_process_ms"] + self._timings["class_process_ms"]
        self._timings["other_ms"] = max(0.0, gen_time - measured_time)

        # Generate UnifiedSymbols for cross-language resolution
        unified_symbols = []
        for node in self._nodes:
            # Only create UnifiedSymbols for definitions
            if node.kind.value in ["Class", "Function", "Method"]:
                try:
                    unified = self._create_unified_symbol(node, source)
                    unified_symbols.append(unified)
                except Exception as e:
                    # Debug: print exception
                    print(f"Failed to create UnifiedSymbol for {node.name}: {e}")
                    import traceback

                    traceback.print_exc()
                    pass

        # Build IR document
        doc = IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="4.1.0",
            nodes=self._nodes,
            edges=self._edges,
            types=list(self._types.values()),
            signatures=list(self._signatures.values()),
            unified_symbols=unified_symbols,  # ⭐ NEW
            meta={
                "file_path": source.file_path,
                "language": source.language,
                "line_count": source.line_count,
            },
        )

        # Analyze method overrides and add OVERRIDES edges
        override_edges = analyze_method_overrides(doc)
        if override_edges:
            doc.edges.extend(override_edges)

        return doc

    def get_timing_breakdown(self) -> dict[str, float]:
        """
        Get detailed timing breakdown of IR generation.

        Returns:
            Dictionary mapping phase names to milliseconds
        """
        return self._timings.copy()

    def _record_time(self, key: str, duration_ms: float):
        """
        Record timing for a specific phase.

        Args:
            key: Timing key (e.g., "function_process_ms")
            duration_ms: Duration in milliseconds
        """
        if key in self._timings:
            self._timings[key] += duration_ms
        else:
            self._timings[key] = duration_ms

    # ============================================================
    # AST Traversal
    # ============================================================

    def _traverse_ast(self, node: TSNode):
        """
        Traverse AST and generate IR nodes/edges.

        OPTIMIZED: Iterative traversal with stack + dictionary dispatch.

        Args:
            node: Current AST node
        """
        # OPTIMIZATION: Dictionary dispatch for node type handlers
        # This is faster than if/elif chains for many node types
        handlers = {
            "class_definition": self._process_class,
            "function_definition": self._process_function,
            "decorated_definition": self._process_decorated_definition,
            "import_statement": self._process_import,
            "import_from_statement": self._process_import,
        }

        # OPTIMIZATION: Iterative traversal with stack instead of recursion
        # This avoids function call overhead for deep AST trees
        stack = [node]

        while stack:
            current = stack.pop()

            # Get handler for this node type
            handler = handlers.get(current.type)

            if handler:
                # Process this node with specific handler
                handler(current)
                # Don't traverse children for handled nodes
                # (handlers manage their own child traversal)
            else:
                # Continue traversal for unhandled nodes
                # Add children to stack in reverse order to maintain left-to-right traversal
                if current.children:
                    stack.extend(reversed(current.children))

    # ============================================================
    # Node Processing (delegates to analyzers)
    # ============================================================

    def _process_class(self, node: TSNode):
        """
        Process class_definition node.

        Args:
            node: class_definition AST node
        """
        # Delegate to ClassAnalyzer with method_processor callback
        self._class_analyzer.process_class(node, method_processor=self._process_function)

    def _process_decorated_definition(self, node: TSNode):
        """
        Process decorated_definition node (function/class with decorators).

        Args:
            node: decorated_definition AST node
        """
        # Extract decorators
        decorators = []
        function_node = None
        class_node = None

        for child in node.children:
            if child.type == "decorator":
                # Extract decorator name/expression
                decorator_text = self.get_node_text(child, self._source_bytes)
                # Remove leading @ and whitespace
                decorator_text = decorator_text.lstrip("@").strip()
                decorators.append(decorator_text)
            elif child.type == "function_definition":
                function_node = child
            elif child.type == "class_definition":
                class_node = child

        # Process the decorated entity with decorator info
        if function_node:
            self._process_function_with_decorators(function_node, decorators)
        elif class_node:
            self._process_class_with_decorators(class_node, decorators)

    def _process_function_with_decorators(self, node: TSNode, decorators: list[str], is_method: bool = False):
        """
        Process function with decorators.

        Args:
            node: function_definition AST node
            decorators: List of decorator strings
            is_method: True if this is a class method
        """
        # Delegate to FunctionAnalyzer
        self._function_analyzer.process_function_with_decorators(
            node, decorators, is_method=is_method, field_processor=self._process_instance_fields_in_init
        )

    def _process_class_with_decorators(self, node: TSNode, decorators: list[str]):
        """
        Process class with decorators.

        Args:
            node: class_definition AST node
            decorators: List of decorator strings
        """
        # Delegate to ClassAnalyzer
        self._class_analyzer.process_class_with_decorators(node, decorators, method_processor=self._process_function)

    def _process_function(self, node: TSNode, is_method: bool = False):
        """
        Process function_definition node.

        Args:
            node: function_definition AST node
            is_method: True if this is a class method
        """
        # Delegate to FunctionAnalyzer with field_processor callback
        self._function_analyzer.process_function(
            node, is_method=is_method, field_processor=self._process_instance_fields_in_init
        )

    def _process_import(self, node: TSNode):
        """
        Process import_statement or import_from_statement.

        Args:
            node: import AST node
        """
        # Delegate to ImportAnalyzer
        self._import_analyzer.process_import(node)

    def _process_instance_fields_in_init(self, body_node: TSNode):
        """
        Process instance field assignments in __init__ method.

        Handles:
        - self.field = value
        - self.field: Type = value (with type annotation)

        Args:
            body_node: block node of __init__ method
        """

        def extract_instance_fields(node: TSNode):
            """Recursively extract instance field assignments"""
            # Check if this is an assignment statement
            if node.type == "assignment":
                # Check if left-hand side is self.attribute
                left_node = None
                for child in node.children:
                    if child.type == "attribute":
                        left_node = child
                        break
                    # Could also be a typed assignment: identifier : type = value
                    # but in __init__, we focus on self.field = value patterns

                if left_node:
                    # Check if it's self.something
                    obj_node = None
                    field_node = None
                    for child in left_node.children:
                        if child.type == "identifier" and obj_node is None:
                            obj_node = child
                        elif child.type == "identifier" and obj_node is not None:
                            field_node = child

                    if obj_node and field_node:
                        obj_name = self.get_node_text(obj_node, self._source_bytes)
                        if obj_name == "self":
                            field_name = self.get_node_text(field_node, self._source_bytes)

                            # Get the class scope (parent of current function scope)
                            # Current scope is the __init__ function, we need the class
                            if len(self._scope._stack) >= 2:
                                class_scope = self._scope._stack[-2]
                                class_fqn = class_scope.fqn

                                # Build field FQN as class.field
                                field_fqn = f"{class_fqn}.{field_name}"

                                # Generate node ID
                                span = self._ast.get_span(node)
                                node_id = generate_logical_id(
                                    repo_id=self.repo_id,
                                    kind=NodeKind.FIELD,
                                    file_path=self._source.file_path,
                                    fqn=field_fqn,
                                )

                                # Try to infer type from assignment value
                                # For now, we leave declared_type_id as None (could be enhanced later)
                                declared_type_id = None

                                # Build attrs
                                attrs = {
                                    "field_kind": "instance_field",  # instance field
                                }

                                # Create FIELD node
                                field_node_obj = Node(
                                    id=node_id,
                                    kind=NodeKind.FIELD,
                                    fqn=field_fqn,
                                    file_path=self._source.file_path,
                                    span=span,
                                    language=self._source.language,
                                    name=field_name,
                                    module_path=self._scope.module.fqn,
                                    parent_id=class_scope.node_id,  # Parent is the class, not __init__
                                    declared_type_id=declared_type_id,
                                    attrs=attrs,
                                )

                                self._nodes.append(field_node_obj)

                                # Add CONTAINS edge from class
                                if class_scope.node_id:
                                    self._add_contains_edge(class_scope.node_id, node_id, span)

            # Recursively process children
            for child in node.children:
                extract_instance_fields(child)

        # Start extraction from body
        extract_instance_fields(body_node)

    def _process_parameters(self, params_node: TSNode, function_id: str) -> list[str]:
        """
        OPTIMIZED: Process function parameters and create Variable nodes.

        Args:
            params_node: parameters AST node
            function_id: Parent function node ID

        Returns:
            List of parameter type IDs (in order)
        """
        param_type_ids = []

        # Cache commonly accessed attributes (reduces attribute lookups)
        file_path = self._source.file_path
        language = self._source.language
        module_path = self._scope.module.fqn
        repo_id = self.repo_id
        source_bytes = self._source_bytes

        # Find all identifiers in parameters
        for child in params_node.children:
            if child.type == "identifier":
                param_name = self.get_node_text(child, source_bytes)

                # Skip 'self' and 'cls' (using frozenset for O(1) lookup)
                if param_name in SKIP_PARAMS:
                    continue

                # Build FQN
                param_fqn = self._scope.build_fqn(param_name)

                # Generate node ID
                span = self._ast.get_span(child)
                node_id = generate_logical_id(
                    repo_id=repo_id,
                    kind=NodeKind.VARIABLE,
                    file_path=file_path,
                    fqn=param_fqn,
                )

                # Create Variable node
                var_node = Node(
                    id=node_id,
                    kind=NodeKind.VARIABLE,
                    fqn=param_fqn,
                    file_path=file_path,
                    span=span,
                    language=language,
                    name=param_name,
                    module_path=module_path,
                    parent_id=function_id,
                    attrs={"var_kind": "parameter"},
                )

                self._nodes.append(var_node)

                # Add CONTAINS edge and register in scope
                self._add_contains_edge(function_id, node_id, span)
                self._scope.register_symbol(param_name, node_id)

                # No type annotation, skip for signature
                # (Could add a placeholder type ID in future)

            elif child.type == "typed_parameter":
                # Handle typed parameters: name: type
                name_node = self.find_child_by_type(child, "identifier")
                if name_node:
                    param_name = self.get_node_text(name_node, source_bytes)

                    if param_name in SKIP_PARAMS:
                        continue

                    param_fqn = self._scope.build_fqn(param_name)
                    span = self._ast.get_span(name_node)

                    node_id = generate_logical_id(
                        repo_id=repo_id,
                        kind=NodeKind.VARIABLE,
                        file_path=file_path,
                        fqn=param_fqn,
                    )

                    # Extract and resolve type annotation
                    type_node = child.child_by_field_name("type")
                    declared_type_id = None
                    if type_node:
                        raw_type = self.get_node_text(type_node, source_bytes)
                        type_entity = self._type_resolver.resolve_type(raw_type)
                        if type_entity and self._types is not None:
                            self._types[type_entity.id] = type_entity
                            declared_type_id = type_entity.id

                    var_node = Node(
                        id=node_id,
                        kind=NodeKind.VARIABLE,
                        fqn=param_fqn,
                        file_path=file_path,
                        span=span,
                        language=language,
                        name=param_name,
                        module_path=module_path,
                        parent_id=function_id,
                        declared_type_id=declared_type_id,
                        attrs={"var_kind": "parameter"},
                    )

                    self._nodes.append(var_node)
                    self._add_contains_edge(function_id, node_id, span)
                    self._scope.register_symbol(param_name, node_id)

                    # Collect type ID for signature
                    if declared_type_id:
                        param_type_ids.append(declared_type_id)

        return param_type_ids

    # ============================================================
    # Edge Generation
    # ============================================================

    def _add_contains_edge(self, parent_id: str, child_id: str, span: Span):
        """
        Add CONTAINS edge from parent to child.

        Args:
            parent_id: Parent node ID
            child_id: Child node ID
            span: Edge location
        """
        edge_id = generate_edge_id("contains", parent_id, child_id, 0)

        edge = Edge(
            id=edge_id,
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=child_id,
            span=span,
        )

        self._edges.append(edge)

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

    # ============================================================
    # Utilities
    # ============================================================

    def _get_module_fqn(self, file_path: str) -> str:
        """
        Get module FQN from file path.

        Args:
            file_path: Relative file path

        Returns:
            Module FQN (e.g., "semantica.retriever.plan")
        """
        # Remove src/ prefix if present
        path = file_path
        if path.startswith("src/"):
            path = path[4:]

        # Remove .py extension
        if path.endswith(".py"):
            path = path[:-3]

        # Replace / with .
        fqn = path.replace("/", ".")

        # Remove __init__ suffix
        if fqn.endswith(".__init__"):
            fqn = fqn[:-9]

        return fqn

    def _create_unified_symbol(self, node: Node, source: SourceFile) -> "UnifiedSymbol":
        """
        Convert Node → UnifiedSymbol (SCIP-compatible)

        Args:
            node: IR Node
            source: Source file

        Returns:
            UnifiedSymbol for cross-language resolution
        """
        from src.contexts.code_foundation.domain.models import UnifiedSymbol
        from src.contexts.code_foundation.infrastructure.version_detector import VersionDetector
        from pathlib import Path

        # Extract package from module FQN
        # e.g., "myproject.utils.helpers" → package="myproject"
        module_fqn = self._get_module_fqn(source.file_path)
        package = module_fqn.split(".")[0] if "." in module_fqn else module_fqn

        # Get relative file path
        rel_path = source.file_path  # Use as-is for now

        # Create descriptor from node FQN
        # e.g., "MyClass.my_method" → "MyClass.my_method()."
        descriptor = node.attrs.get("fqn", node.name)
        if node.kind.value == "Function" or node.kind.value == "Method":
            descriptor += "()."
        elif node.kind.value == "Class":
            descriptor += "#"
        else:
            descriptor += "."

        # Extract generic parameters if available
        generic_params = None
        type_params = node.attrs.get("type_parameters")
        if type_params:
            generic_params = type_params if isinstance(type_params, list) else [type_params]

        # Detect version from project files
        # Use parent directory of source file as project root
        try:
            project_root = str(Path(source.file_path).parent.absolute())
            detector = VersionDetector(project_root)
            version = detector.detect_version("python", package)
        except Exception:
            version = "unknown"

        return UnifiedSymbol.from_simple(
            scheme="python",
            package=package,
            descriptor=descriptor,
            language_fqn=node.attrs.get("fqn", node.name),
            language_kind=node.kind.value,
            version=version,
            file_path=rel_path,
        )

    def _is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file"""
        return "test" in file_path.lower() or file_path.startswith("tests/") or "/tests/" in file_path

    def _extract_docstring(self, node: TSNode) -> str | None:
        """
        Extract docstring from function/class node.

        Args:
            node: function_definition or class_definition

        Returns:
            Docstring text or None
        """
        # Find body/block
        body = self.find_child_by_type(node, "block")
        if not body:
            return None

        # First statement in body might be a string (docstring)
        for child in body.children:
            # Check for direct string node (Python docstrings are direct children)
            if child.type == "string":
                text = self.get_node_text(child, self._source_bytes)
                return self._clean_docstring(text)
            # Fallback: check for expression_statement containing string
            elif child.type == "expression_statement":
                string_node = self.find_child_by_type(child, "string")
                if string_node:
                    text = self.get_node_text(string_node, self._source_bytes)
                    return self._clean_docstring(text)
            elif child.type not in ("comment", "newline"):
                # Non-docstring statement found
                break

        return None

    def _clean_docstring(self, text: str) -> str:
        """
        Remove quotes from docstring text.

        Args:
            text: Raw docstring text with quotes

        Returns:
            Cleaned docstring text
        """
        # Remove quotes (triple quotes first, then single/double)
        if text.startswith('"""') and text.endswith('"""'):
            text = text[3:-3]
        elif text.startswith("'''") and text.endswith("'''"):
            text = text[3:-3]
        elif text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        elif text.startswith("'") and text.endswith("'"):
            text = text[1:-1]
        return text.strip()

    def _calculate_cf_summary(self, body_node: TSNode) -> ControlFlowSummary:
        """
        Calculate control flow summary for function body.

        OPTIMIZED: Single-pass iterative traversal.

        Args:
            body_node: Function body block

        Returns:
            Control flow summary
        """
        if body_node is None or not body_node.children:
            return ControlFlowSummary(
                cyclomatic_complexity=1,
                has_loop=False,
                has_try=False,
                branch_count=0,
            )

        # Initialize metrics
        cyclomatic = 1
        branch_count = 0
        has_loop_flag = False
        has_try_flag = False

        # Single iterative pass
        stack = [body_node]

        while stack:
            node = stack.pop()
            node_type = node.type

            # frozenset membership is O(1)
            if node_type in PYTHON_BRANCH_TYPES:
                branch_count += 1
                cyclomatic += 1
            elif node_type in PYTHON_LOOP_TYPES:
                has_loop_flag = True
                cyclomatic += 1
            elif node_type in PYTHON_TRY_TYPES:
                has_try_flag = True

            if node.children:
                stack.extend(node.children)

        return ControlFlowSummary(
            cyclomatic_complexity=cyclomatic,
            has_loop=has_loop_flag,
            has_try=has_try_flag,
            branch_count=branch_count,
        )

    def _find_try_statements_recursive(self, node: TSNode, results: list[TSNode]) -> None:
        """Recursively find all try_statement nodes in AST."""
        if node.type == "try_statement":
            results.append(node)
        for child in node.children:
            self._find_try_statements_recursive(child, results)

    def _extract_as_pattern_info(self, as_pattern_node: TSNode) -> tuple[str | None, str | None]:
        """
        Extract exception type and variable from as_pattern node.

        Args:
            as_pattern_node: AST node of type "as_pattern"

        Returns:
            (exception_type, exception_var)
        """
        exc_type = None
        exc_var = None

        for as_child in as_pattern_node.children:
            if as_child.type == "identifier" and exc_type is None:
                exc_type = self.get_node_text(as_child, self._source_bytes)
            elif as_child.type == "as_pattern_target":
                for target_child in as_child.children:
                    if target_child.type == "identifier":
                        exc_var = self.get_node_text(target_child, self._source_bytes)
                        break  # Only need first identifier

        return exc_type, exc_var

    def _extract_except_clause_info(self, except_clause: TSNode, handler: dict) -> None:
        """
        Extract exception info from except_clause and update handler dict.

        Args:
            except_clause: AST node of type "except_clause"
            handler: Handler dict to update with types and vars
        """
        for except_child in except_clause.children:
            if except_child.type == "identifier":
                # Simple except: except ValueError:
                exc_type = self.get_node_text(except_child, self._source_bytes)
                handler["exception_types"].append(exc_type)

            elif except_child.type == "as_pattern":
                # Except with variable: except ValueError as e:
                exc_type, exc_var = self._extract_as_pattern_info(except_child)
                if exc_type:
                    handler["exception_types"].append(exc_type)
                if exc_var:
                    handler["exception_vars"].append(exc_var)

    def _extract_try_handler_info(self, try_stmt: TSNode) -> dict:
        """
        Extract handler info from a single try statement.

        Args:
            try_stmt: AST node of type "try_statement"

        Returns:
            Handler dict with exception_types, exception_vars, has_else, has_finally
        """
        handler = {
            "exception_types": [],
            "exception_vars": [],
            "has_else": False,
            "has_finally": False,
        }

        # Dispatch table for try statement children
        for child in try_stmt.children:
            if child.type == "except_clause":
                self._extract_except_clause_info(child, handler)
            elif child.type == "else_clause":
                handler["has_else"] = True
            elif child.type == "finally_clause":
                handler["has_finally"] = True

        return handler

    def _extract_exception_info(self, body_node: TSNode) -> dict | None:
        """
        Extract detailed exception handling information from function body.

        Args:
            body_node: Function body block

        Returns:
            Dictionary with exception handling details or None if no try-except
        """
        try_statements: list[TSNode] = []
        self._find_try_statements_recursive(body_node, try_statements)

        if not try_statements:
            return None

        return {
            "try_count": len(try_statements),
            "exception_handlers": [self._extract_try_handler_info(try_stmt) for try_stmt in try_statements],
        }
