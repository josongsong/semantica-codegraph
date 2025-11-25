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

from ..ir.id_strategy import (
    generate_content_hash,
    generate_edge_id,
    generate_logical_id,
)
from ..ir.models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from ..parsing import AstTree, SourceFile
from ..semantic_ir.signature.models import SignatureEntity
from ..semantic_ir.typing.models import TypeEntity
from ..semantic_ir.typing.resolver import TypeResolver
from .base import IRGenerator
from .python import PythonCallAnalyzer, PythonSignatureBuilder, PythonVariableAnalyzer
from .scope_stack import ScopeStack

if TYPE_CHECKING:
    from ..ir.external_analyzers import ExternalAnalyzer

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

        # Generate IR
        gen_start = time.perf_counter()
        self._generate_file_node()
        self._traverse_ast(self._ast.root)
        gen_time = (time.perf_counter() - gen_start) * 1000

        # Calculate "other" time (AST traversal overhead + misc)
        # Note: function_process_ms includes call_analysis, variable_analysis, signature_build
        # So we only count top-level function/class processing times
        measured_time = self._timings["function_process_ms"] + self._timings["class_process_ms"]
        self._timings["other_ms"] = max(0.0, gen_time - measured_time)

        # Build IR document
        doc = IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="4.1.0",
            nodes=self._nodes,
            edges=self._edges,
            types=list(self._types.values()),
            signatures=list(self._signatures.values()),
            meta={
                "file_path": source.file_path,
                "language": source.language,
                "line_count": source.line_count,
            },
        )

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
    # Node Generation
    # ============================================================

    def _generate_file_node(self):
        """Generate File node for the entire source file"""
        span = Span(
            start_line=1,
            start_col=0,
            end_line=self._source.line_count,
            end_col=0,
        )

        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.FILE,
            file_path=self._source.file_path,
            fqn=self._scope.module.fqn,
        )

        content_hash = generate_content_hash(self._source.content)

        node = Node(
            id=node_id,
            kind=NodeKind.FILE,
            fqn=self._scope.module.fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            content_hash=content_hash,
            name=self._source.file_path.split("/")[-1],
            module_path=self._scope.module.fqn,
            is_test_file=self._is_test_file(self._source.file_path),
        )

        self._nodes.append(node)
        self._scope.module.node_id = node_id

    def _process_class(self, node: TSNode):
        """
        Process class_definition node.

        Args:
            node: class_definition AST node
        """
        import time

        start = time.perf_counter()

        # Get class name
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        class_name = self.get_node_text(name_node, self._source_bytes)

        # Build FQN
        class_fqn = self._scope.build_fqn(class_name)

        # Generate node ID
        span = self._ast.get_span(node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.CLASS,
            file_path=self._source.file_path,
            fqn=class_fqn,
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Get class body
        body_node = self.find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        # Create class node
        class_node = Node(
            id=node_id,
            kind=NodeKind.CLASS,
            fqn=class_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=class_name,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.current.node_id,
            body_span=body_span,
            docstring=docstring,
            content_hash=self.generate_content_hash(self.get_node_text(node, self._source_bytes)),
        )

        self._nodes.append(class_node)

        # Add CONTAINS edge from parent
        parent_node_id = self._scope.current.node_id
        assert parent_node_id is not None, "Parent scope must have node_id set"
        self._add_contains_edge(parent_node_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(class_name, node_id)

        # Register class with type resolver (for LOCAL type resolution)
        self._type_resolver.register_local_class(class_name, node_id)

        # Push class scope
        self._scope.push("class", class_name, class_fqn)
        self._scope.current.node_id = node_id

        # Process class body
        method_time_before = self._timings.get("function_process_ms", 0)
        if body_node:
            for child in body_node.children:
                if child.type == "function_definition":
                    self._process_function(child, is_method=True)
                elif child.type == "expression_statement":
                    # Could be class-level assignment (field)
                    self._process_potential_field(child)
        method_time_after = self._timings.get("function_process_ms", 0)
        method_time_in_class = method_time_after - method_time_before

        # Pop class scope
        self._scope.pop()

        # Record class overhead only (exclude method processing time)
        duration_ms = (time.perf_counter() - start) * 1000
        class_overhead = duration_ms - method_time_in_class
        self._record_time("class_process_ms", class_overhead)

    def _process_function(self, node: TSNode, is_method: bool = False):
        """
        Process function_definition node.

        Args:
            node: function_definition AST node
            is_method: True if this is a class method
        """
        import time

        start = time.perf_counter()

        # PHASE 1: Extract metadata (name, FQN, span, docstring)
        metadata_start = time.perf_counter()

        # Get function name
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        func_name = self.get_node_text(name_node, self._source_bytes)

        # Build FQN
        func_fqn = self._scope.build_fqn(func_name)

        # Determine kind
        kind = NodeKind.METHOD if is_method else NodeKind.FUNCTION

        # Generate node ID
        span = self._ast.get_span(node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=kind,
            file_path=self._source.file_path,
            fqn=func_fqn,
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Get function body
        body_node = self.find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        self._record_time("func_metadata_ms", (time.perf_counter() - metadata_start) * 1000)

        # PHASE 2: Calculate control flow summary
        cf_start = time.perf_counter()
        cf_summary = self._calculate_cf_summary(body_node) if body_node else None
        self._record_time("func_cf_summary_ms", (time.perf_counter() - cf_start) * 1000)

        # PHASE 3: Create node object
        node_start = time.perf_counter()
        func_node = Node(
            id=node_id,
            kind=kind,
            fqn=func_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=func_name,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.current.node_id,
            body_span=body_span,
            docstring=docstring,
            content_hash=self.generate_content_hash(self.get_node_text(node, self._source_bytes)),
            control_flow_summary=cf_summary,
        )
        self._nodes.append(func_node)
        self._record_time("func_node_creation_ms", (time.perf_counter() - node_start) * 1000)

        # PHASE 4: Edge creation and scope management
        edge_scope_start = time.perf_counter()

        # Add CONTAINS edge from parent
        parent_node_id = self._scope.current.node_id
        assert parent_node_id is not None, "Parent scope must have node_id set"
        self._add_contains_edge(parent_node_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(func_name, node_id)

        # Push function scope
        self._scope.push("function", func_name, func_fqn)
        self._scope.current.node_id = node_id

        self._record_time("func_edge_scope_ms", (time.perf_counter() - edge_scope_start) * 1000)

        # PHASE 5: Process parameters
        param_start = time.perf_counter()
        params_node = self.find_child_by_type(node, "parameters")
        param_type_ids = []
        if params_node:
            param_type_ids = self._process_parameters(params_node, node_id)
        self._record_time("func_param_ms", (time.perf_counter() - param_start) * 1000)

        # Process function body for variables (using builder)
        if body_node:
            var_start = time.perf_counter()
            self._variable_analyzer.process_variables_in_block(
                body_node,
                node_id,
                self.repo_id,
                self._source.file_path,
                self._source.language,
                self._scope.module.fqn,
                self._ast.get_span,
                self.get_node_text,
                self._source_bytes,
                self.find_child_by_type,
            )
            self._record_time("variable_analysis_ms", (time.perf_counter() - var_start) * 1000)

            # Process function calls (using builder)
            call_start = time.perf_counter()
            self._call_analyzer.process_calls_in_block(
                body_node,
                node_id,
                self.repo_id,
                self._ast.get_span,
                self.get_node_text,
                self._source_bytes,
            )
            self._record_time("call_analysis_ms", (time.perf_counter() - call_start) * 1000)

        # Pop function scope
        self._scope.pop()

        # Build signature after processing (using builder)
        sig_start = time.perf_counter()
        signature = self._signature_builder.build_signature(
            node,
            node_id,
            func_name,
            param_type_ids,
            self.get_node_text,
            self._source_bytes,
        )
        self._record_time("signature_build_ms", (time.perf_counter() - sig_start) * 1000)

        if signature:
            self._signatures[signature.id] = signature
            # Link signature to function node
            func_node.signature_id = signature.id

        # Record total function processing time
        # Note: We don't separately track core overhead because
        # call/variable/signature timings are cumulative
        duration_ms = (time.perf_counter() - start) * 1000
        self._record_time("function_process_ms", duration_ms)

    def _process_import(self, node: TSNode):
        """
        Process import_statement or import_from_statement.

        Args:
            node: import AST node
        """
        if node.type == "import_statement":
            self._process_import_statement(node)
        elif node.type == "import_from_statement":
            self._process_import_from_statement(node)

    def _process_import_statement(self, node: TSNode):
        """
        Process: import module [as alias]

        Args:
            node: import_statement AST node
        """
        # import_statement contains dotted_name or aliased_import
        for child in node.children:
            if child.type == "dotted_name":
                # Simple import: import numpy
                module_name = self.get_node_text(child, self._source_bytes)
                self._create_import_node(node, module_name, module_name)

            elif child.type == "aliased_import":
                # Aliased import: import numpy as np
                name_node = self.find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    module_name = self.get_node_text(name_node, self._source_bytes)
                    alias = self.get_node_text(alias_node, self._source_bytes)
                    self._create_import_node(node, module_name, alias)

    def _process_import_from_statement(self, node: TSNode):
        """
        Process: from module import name [as alias]

        Args:
            node: import_from_statement AST node
        """
        # Get module name (from XXX import ...)
        module_node = child = node.child_by_field_name("module_name")
        if not module_node:
            return

        module_name = self.get_node_text(module_node, self._source_bytes)

        # Get imported names
        for child in node.children:
            if child.type == "dotted_name" and child != module_node:
                # from module import name
                symbol_name = self.get_node_text(child, self._source_bytes)
                full_symbol = f"{module_name}.{symbol_name}"
                self._create_import_node(node, full_symbol, symbol_name)

            elif child.type == "aliased_import":
                # from module import name as alias
                name_node = self.find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    symbol_name = self.get_node_text(name_node, self._source_bytes)
                    alias = self.get_node_text(alias_node, self._source_bytes)
                    full_symbol = f"{module_name}.{symbol_name}"
                    self._create_import_node(node, full_symbol, alias)

            elif child.type == "wildcard_import":
                # from module import *
                self._create_import_node(node, f"{module_name}.*", "*")

    def _create_import_node(self, import_node: TSNode, full_symbol: str, alias: str):
        """
        Create Import node and IMPORTS edge.

        Args:
            import_node: import AST node
            full_symbol: Full symbol name (e.g., "numpy" or "os.path.join")
            alias: Import alias (same as full_symbol if no alias)
        """
        # Build FQN for import node
        import_fqn = f"{self._scope.module.fqn}.__import__.{full_symbol}"

        # Generate node ID
        span = self._ast.get_span(import_node)
        node_id = generate_logical_id(
            repo_id=self.repo_id,
            kind=NodeKind.IMPORT,
            file_path=self._source.file_path,
            fqn=import_fqn,
        )

        # Create Import node
        import_ir_node = Node(
            id=node_id,
            kind=NodeKind.IMPORT,
            fqn=import_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=full_symbol,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.module.node_id,
            attrs={
                "full_symbol": full_symbol,
                "alias": alias,
                "is_wildcard": alias == "*",
            },
        )

        self._nodes.append(import_ir_node)

        # Add CONTAINS edge from file
        module_node_id = self._scope.module.node_id
        assert module_node_id is not None, "Module scope must have node_id set"
        self._add_contains_edge(module_node_id, node_id, span)

        # Register import alias in scope
        self._scope.register_import(alias, full_symbol)

    def _process_potential_field(self, node: TSNode):
        """
        Process potential class field (class-level assignment).

        Args:
            node: expression_statement node
        """
        # TODO: Check if this is an assignment at class level
        pass

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
