"""
Function Analyzer for Python IR

Handles function/method definition processing including parameters, body, and decorators.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

from codegraph_engine.code_foundation.infrastructure.generators.python.builders.edge_builder import EdgeBuilder
from codegraph_engine.code_foundation.infrastructure.generators.python.call_analyzer import PythonCallAnalyzer
from codegraph_engine.code_foundation.infrastructure.generators.python.lambda_analyzer import PythonLambdaAnalyzer
from codegraph_engine.code_foundation.infrastructure.generators.python.signature_builder import PythonSignatureBuilder
from codegraph_engine.code_foundation.infrastructure.generators.python.variable_analyzer import PythonVariableAnalyzer
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.generators.python._id_helper import generate_python_node_id

# RFC-031: Removed - using _id_helper instead
from codegraph_engine.code_foundation.infrastructure.ir.models import ControlFlowSummary, Node, NodeKind
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile
from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver


@dataclass
class FunctionAnalyzerContext:
    """
    Context for FunctionAnalyzer initialization.

    Groups related parameters to reduce __init__ complexity.

    Usage:
        ctx = FunctionAnalyzerContext(
            repo_id="repo1",
            nodes=nodes,
            edges=edges,
            scope=scope,
            edge_builder=edge_builder,
            source=source,
            source_bytes=source_bytes,
            ast=ast,
            timings=timings,
        )
        analyzer = FunctionAnalyzer(ctx, analyzers, type_system)
    """

    repo_id: str
    nodes: list[Node]
    edges: list
    scope: ScopeStack
    edge_builder: EdgeBuilder
    source: SourceFile
    source_bytes: bytes
    ast: AstTree
    timings: dict


@dataclass
class FunctionAnalyzerServices:
    """Service dependencies for FunctionAnalyzer."""

    type_resolver: TypeResolver
    signature_builder: PythonSignatureBuilder
    variable_analyzer: PythonVariableAnalyzer
    call_analyzer: PythonCallAnalyzer
    lambda_analyzer: PythonLambdaAnalyzer


@dataclass
class FunctionAnalyzerCollections:
    """Shared collections for type/signature tracking."""

    types: dict
    signatures: dict


# Constants for parameter skipping
SKIP_PARAMS = frozenset(["self", "cls"])

# Control flow node types (for cyclomatic complexity)
PYTHON_BRANCH_TYPES = frozenset(
    [
        "if_statement",
        "elif_clause",
        "else_clause",
        "conditional_expression",
    ]
)

PYTHON_LOOP_TYPES = frozenset(
    [
        "for_statement",
        "while_statement",
    ]
)

PYTHON_TRY_TYPES = frozenset(
    [
        "try_statement",
        "except_clause",
    ]
)


class FunctionAnalyzer:
    """
    Handles function/method definition processing.

    Responsibilities:
    - Process function/method definitions
    - Extract docstrings and control flow summaries
    - Process parameters (with type resolution)
    - Create FUNCTION/METHOD nodes
    - Create CONTAINS edges (parent → function, function → params)
    - Process function body (via analyzers)
    - Build function signatures
    - Handle decorators
    - Register functions in scope
    - Track detailed timing breakdown

    This analyzer coordinates with specialized analyzers for:
    - Variables (VariableAnalyzer)
    - Calls (CallAnalyzer)
    - Lambdas (LambdaAnalyzer)
    - Signatures (SignatureBuilder)

    Example:
        >>> nodes = []
        >>> edges = []
        >>> scope = ScopeStack("main")
        >>> edge_builder = EdgeBuilder(edges)
        >>> analyzer = FunctionAnalyzer(
        ...     "repo1", nodes, edges, scope, edge_builder,
        ...     type_resolver, signature_builder, variable_analyzer,
        ...     call_analyzer, lambda_analyzer, types, signatures,
        ...     source, source_bytes, ast, timings
        ... )
        >>> # Process: def my_func(x: int) -> str: ...
        >>> analyzer.process_function(func_ast_node)
        >>> assert len(nodes) >= 2  # FUNCTION node + VARIABLE node (param)
    """

    def __init__(
        self,
        # Grouped parameters (recommended)
        context: FunctionAnalyzerContext | None = None,
        services: FunctionAnalyzerServices | None = None,
        collections: FunctionAnalyzerCollections | None = None,
        # Legacy individual parameters (backward compatible)
        repo_id: str | None = None,
        nodes: list[Node] | None = None,
        edges: list | None = None,
        scope: ScopeStack | None = None,
        edge_builder: EdgeBuilder | None = None,
        type_resolver: TypeResolver | None = None,
        signature_builder: PythonSignatureBuilder | None = None,
        variable_analyzer: PythonVariableAnalyzer | None = None,
        call_analyzer: PythonCallAnalyzer | None = None,
        lambda_analyzer: PythonLambdaAnalyzer | None = None,
        dataflow_analyzer=None,
        exception_analyzer=None,
        types: dict | None = None,
        signatures: dict | None = None,
        source: SourceFile | None = None,
        source_bytes: bytes | None = None,
        ast: AstTree | None = None,
        timings: dict | None = None,
    ):
        """
        Initialize function analyzer.

        Supports two initialization styles:
        1. Grouped (recommended): Pass context, services, collections
        2. Legacy (backward compatible): Pass individual parameters

        Args:
            context: FunctionAnalyzerContext with core parameters
            services: FunctionAnalyzerServices with analyzer dependencies
            collections: FunctionAnalyzerCollections with shared collections

            # Legacy parameters (deprecated):
            repo_id, nodes, edges, scope, edge_builder, type_resolver,
            signature_builder, variable_analyzer, call_analyzer,
            lambda_analyzer, types, signatures, source, source_bytes,
            ast, timings
        """
        self._repo_id: str | None = None
        self._nodes: list[Node] | None = None
        self._edges: list | None = None
        self._scope: ScopeStack | None = None
        self._edge_builder: EdgeBuilder | None = None
        self._type_resolver: TypeResolver | None = None
        self._signature_builder: PythonSignatureBuilder | None = None
        self._variable_analyzer: PythonVariableAnalyzer | None = None
        self._call_analyzer: PythonCallAnalyzer | None = None
        self._lambda_analyzer: PythonLambdaAnalyzer | None = None
        self._types: dict | None = None
        self._signatures: dict | None = None
        self._source: SourceFile | None = None
        self._source_bytes: bytes | None = None
        self._ast: AstTree | None = None
        self._timings: dict | None = None

        # Handle grouped vs legacy initialization
        if context and services and collections:
            # Grouped initialization (recommended)
            self._repo_id = context.repo_id
            self._nodes = context.nodes
            self._edges = context.edges
            self._scope = context.scope
            self._edge_builder = context.edge_builder
            self._source = context.source
            self._source_bytes = context.source_bytes
            self._ast = context.ast
            self._timings = context.timings

            self._type_resolver = services.type_resolver
            self._signature_builder = services.signature_builder
            self._variable_analyzer = services.variable_analyzer
            self._call_analyzer = services.call_analyzer
            self._lambda_analyzer = services.lambda_analyzer
            self._dataflow_analyzer = None
            self._exception_analyzer = None

            self._types = collections.types
            self._signatures = collections.signatures
        else:
            # Legacy initialization (backward compatible)
            self._repo_id = repo_id
            self._nodes = nodes
            self._edges = edges
            self._scope = scope
            self._edge_builder = edge_builder
            self._type_resolver = type_resolver
            self._signature_builder = signature_builder
            self._variable_analyzer = variable_analyzer
            self._call_analyzer = call_analyzer
            self._lambda_analyzer = lambda_analyzer
            self._dataflow_analyzer = dataflow_analyzer
            self._exception_analyzer = exception_analyzer
            self._types = types
            self._signatures = signatures
            self._source = source
            self._source_bytes = source_bytes
            self._ast = ast
            self._timings = timings

        self._temp_decorators = None

    def process_function(self, node: TSNode, is_method: bool = False, field_processor=None):
        """
        Process function_definition node.

        Args:
            node: function_definition AST node
            is_method: True if this is a class method
            field_processor: Optional callback for processing instance fields in __init__
                           Signature: field_processor(body_node)

        Example:
            >>> # def my_func(x: int) -> str: ...
            >>> analyzer.process_function(func_ast)
            >>> # class method: def method(self, x: int): ...
            >>> analyzer.process_function(method_ast, is_method=True)
        """
        start = time.perf_counter()

        # PHASE 1: Extract metadata (name, FQN, span, docstring)
        metadata_start = time.perf_counter()

        # Get function name
        name_node = self._find_child_by_type(node, "identifier")
        if not name_node:
            return

        func_name = self._get_node_text(name_node)

        # Build FQN
        func_fqn = self._scope.build_fqn(func_name)

        # Determine kind
        kind = NodeKind.METHOD if is_method else NodeKind.FUNCTION

        # Generate node ID
        span = self._ast.get_span(node)
        # RFC-031 Phase B: Use Hash ID
        node_id = generate_python_node_id(
            repo_id=self._repo_id,
            kind=kind,
            file_path=self._source.file_path,
            fqn=func_fqn,
            language=self._source.language,
        )

        # Extract docstring
        docstring = self.extract_docstring(node)

        # Get function body
        body_node = self._find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        self._record_time("func_metadata_ms", (time.perf_counter() - metadata_start) * 1000)

        # PHASE 2: Calculate control flow summary
        cf_start = time.perf_counter()
        cf_summary = self.calculate_cf_summary(body_node) if body_node else None
        self._record_time("func_cf_summary_ms", (time.perf_counter() - cf_start) * 1000)

        # PHASE 3: Create node object
        node_start = time.perf_counter()

        # Build attrs dict with decorators if present
        attrs = {}
        if self._temp_decorators:
            attrs["decorators"] = self._temp_decorators

        # RFC-19: Extract type_info for null analysis
        params_node_for_type = self._find_child_by_type(node, "parameters")
        type_info = self._extract_type_info(node, params_node_for_type)
        if type_info:
            attrs["type_info"] = type_info
            # Copy parameters to attrs root (for MethodSummaryBuilder)
            if "parameters" in type_info:
                attrs["parameters"] = type_info["parameters"]

        # RFC-19: Extract body statements for null analysis
        if body_node:
            body_statements = self._extract_body_statements(body_node)
            if body_statements:
                attrs["body_statements"] = body_statements

        # Extract exception handling information
        if body_node:
            exception_info = self.extract_exception_info(body_node)
            if exception_info:
                attrs["exception_handling"] = exception_info

        # Generate content hash
        content_hash = self._generate_content_hash(self._get_node_text(node))

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
            content_hash=content_hash,
            control_flow_summary=cf_summary,
            attrs=attrs,
        )
        self._nodes.append(func_node)
        self._record_time("func_node_creation_ms", (time.perf_counter() - node_start) * 1000)

        # PHASE 4: Edge creation and scope management
        edge_scope_start = time.perf_counter()

        # Add CONTAINS edge from parent
        parent_node_id = self._scope.current.node_id
        assert parent_node_id is not None, "Parent scope must have node_id set"
        self._edge_builder.add_contains_edge(parent_node_id, node_id, span)

        # Register in scope
        self._scope.register_symbol(func_name, node_id)

        # Push function scope
        self._scope.push("function", func_name, func_fqn)
        self._scope.current.node_id = node_id

        self._record_time("func_edge_scope_ms", (time.perf_counter() - edge_scope_start) * 1000)

        # PHASE 5: Process parameters
        param_start = time.perf_counter()
        params_node = self._find_child_by_type(node, "parameters")
        param_type_ids = []
        if params_node:
            param_type_ids = self.process_parameters(params_node, node_id)
        self._record_time("func_param_ms", (time.perf_counter() - param_start) * 1000)

        # Process function body
        if body_node:
            # Variables
            var_start = time.perf_counter()
            self._variable_analyzer.process_variables_in_block(
                body_node,
                node_id,
                self._repo_id,
                self._source.file_path,
                self._source.language,
                self._scope.module.fqn,
                self._ast.get_span,
                self._get_node_text,
                self._source_bytes,
                self._find_child_by_type,
            )
            self._record_time("variable_analysis_ms", (time.perf_counter() - var_start) * 1000)

            # Process instance fields if this is __init__ method
            if is_method and func_name == "__init__" and field_processor:
                field_start = time.perf_counter()
                field_processor(body_node)
                self._record_time("instance_field_ms", (time.perf_counter() - field_start) * 1000)

            # Calls
            call_start = time.perf_counter()
            self._call_analyzer.process_calls_in_block(
                body_node,
                node_id,
                self._repo_id,
                self._ast.get_span,
                self._get_node_text,
                self._source_bytes,
            )
            self._record_time("call_analysis_ms", (time.perf_counter() - call_start) * 1000)

            # SOTA FIX: Dataflow (READS/WRITES)
            if self._dataflow_analyzer:
                dataflow_start = time.perf_counter()
                self._dataflow_analyzer.process_dataflow_in_block(
                    body_node,
                    node_id,
                    self._ast.get_span,
                    self._get_node_text,
                    self._source_bytes,
                )
                self._record_time("dataflow_analysis_ms", (time.perf_counter() - dataflow_start) * 1000)

            # SOTA FIX: Exception handling
            if self._exception_analyzer:
                exc_start = time.perf_counter()
                exc_info = self._exception_analyzer.analyze_function_body(
                    body_node,
                    self._get_node_text,
                    self._source_bytes,
                )
                # Add exception info to function node attrs
                for node in self._nodes:
                    if node.id == node_id:
                        node.attrs["exception_handling"] = exc_info
                        break
                self._record_time("exception_analysis_ms", (time.perf_counter() - exc_start) * 1000)

            # Lambdas
            lambda_start = time.perf_counter()
            lambda_nodes = self._lambda_analyzer.process_lambdas_in_block(
                body_node,
                node_id,
                self._repo_id,
                self._source.file_path,
                self._source.language,
                self._scope.module.fqn,
                self._ast.get_span,
                self._get_node_text,
                self._source_bytes,
                func_fqn,
            )
            # Add lambda nodes and CONTAINS edges
            for lambda_node in lambda_nodes:
                self._nodes.append(lambda_node)
                self._edge_builder.add_contains_edge(node_id, lambda_node.id, lambda_node.span)
            self._record_time("lambda_analysis_ms", (time.perf_counter() - lambda_start) * 1000)

        # Pop function scope
        self._scope.pop()

        # Build signature after processing
        sig_start = time.perf_counter()
        signature = self._signature_builder.build_signature(
            node,  # AST node (TSNode)
            node_id,
            func_name,
            param_type_ids,
            self._get_node_text,
            self._source_bytes,
        )
        self._record_time("signature_build_ms", (time.perf_counter() - sig_start) * 1000)

        if signature:
            self._signatures[signature.id] = signature
            # Link signature to function node
            func_node.signature_id = signature.id

        # Record total function processing time
        duration_ms = (time.perf_counter() - start) * 1000
        self._record_time("function_process_ms", duration_ms)

    def process_function_with_decorators(
        self, node: TSNode, decorators: list[str], is_method: bool = False, field_processor=None
    ):
        """
        Process function with decorators.

        Args:
            node: function_definition AST node
            decorators: List of decorator strings
            is_method: True if this is a class method
            field_processor: Optional callback for processing instance fields

        Example:
            >>> # @staticmethod
            >>> # def my_func(): ...
            >>> analyzer.process_function_with_decorators(ast, ["staticmethod"])
        """
        # Store decorators for later use
        self._temp_decorators = decorators
        # Process function normally
        self.process_function(node, is_method, field_processor)
        # Clear temp decorators
        self._temp_decorators = None

    def process_parameters(self, params_node: TSNode, function_id: str) -> list[str]:
        """
        Process function parameters.

        Args:
            params_node: parameters AST node
            function_id: Parent function node ID

        Returns:
            List of type IDs for parameters (for signature building)

        Example:
            >>> # def func(x: int, y: str = "default"): ...
            >>> type_ids = analyzer.process_parameters(params_ast, "func:id")
            >>> assert len(type_ids) == 2
        """
        param_type_ids = []

        file_path = self._source.file_path
        language = self._source.language
        module_path = self._scope.module.fqn

        # Find all identifiers in parameters
        for child in params_node.children:
            if child.type == "identifier":
                param_name = self._get_node_text(child)

                # Skip 'self' and 'cls'
                if param_name in SKIP_PARAMS:
                    continue

                # Build FQN
                param_fqn = self._scope.build_fqn(param_name)

                # Generate node ID
                span = self._ast.get_span(child)
                # RFC-031 Phase B: Use Hash ID
                node_id = generate_python_node_id(
                    repo_id=self._repo_id,
                    kind=NodeKind.VARIABLE,
                    file_path=file_path,
                    fqn=param_fqn,
                    language=language,
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
                self._edge_builder.add_contains_edge(function_id, node_id, span)
                self._scope.register_symbol(param_name, node_id)

            elif child.type == "typed_parameter":
                # Handle typed parameters: name: type
                name_node = self._find_child_by_type(child, "identifier")
                if name_node:
                    param_name = self._get_node_text(name_node)

                    if param_name in SKIP_PARAMS:
                        continue

                    param_fqn = self._scope.build_fqn(param_name)
                    span = self._ast.get_span(name_node)

                    node_id = generate_python_node_id(
                        repo_id=self._repo_id,
                        kind=NodeKind.VARIABLE,
                        file_path=file_path,
                        fqn=param_fqn,
                    )

                    # Extract and resolve type annotation
                    type_node = child.child_by_field_name("type")
                    declared_type_id = None
                    if type_node:
                        raw_type = self._get_node_text(type_node)
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
                    self._edge_builder.add_contains_edge(function_id, node_id, span)
                    self._scope.register_symbol(param_name, node_id)

                    # Collect type ID for signature
                    if declared_type_id:
                        param_type_ids.append(declared_type_id)

        return param_type_ids

    def extract_docstring(self, node: TSNode) -> str | None:
        """
        Extract docstring from function/class node.

        Args:
            node: function_definition or class_definition

        Returns:
            Docstring text or None

        Example:
            >>> # def func():
            >>> #     '''This is a docstring'''
            >>> #     pass
            >>> docstring = analyzer.extract_docstring(func_ast)
            >>> assert docstring == "This is a docstring"
        """
        # Find body/block
        body = self._find_child_by_type(node, "block")
        if not body:
            return None

        # First statement in body might be a string (docstring)
        for child in body.children:
            # Check for direct string node
            if child.type == "string":
                text = self._get_node_text(child)
                return self._clean_docstring(text)
            # Fallback: check for expression_statement containing string
            elif child.type == "expression_statement":
                string_node = self._find_child_by_type(child, "string")
                if string_node:
                    text = self._get_node_text(string_node)
                    return self._clean_docstring(text)
            elif child.type not in ("comment", "newline"):
                # Non-docstring statement found
                break

        return None

    def calculate_cf_summary(self, body_node: TSNode) -> ControlFlowSummary:
        """
        Calculate control flow summary for function body.

        Args:
            body_node: Function body block

        Returns:
            Control flow summary

        Example:
            >>> # def func():
            >>> #     if condition:
            >>> #         for i in range(10):
            >>> #             pass
            >>> summary = analyzer.calculate_cf_summary(body_ast)
            >>> assert summary.has_loop is True
            >>> assert summary.branch_count >= 1
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

    def extract_exception_info(self, body_node: TSNode) -> dict | None:
        """
        Extract detailed exception handling information from function body.

        Args:
            body_node: Function body block

        Returns:
            Dictionary with exception handling details or None

        Example:
            >>> # def func():
            >>> #     try:
            >>> #         ...
            >>> #     except ValueError:
            >>> #         ...
            >>> info = analyzer.extract_exception_info(body_ast)
            >>> assert "has_try" in info
        """
        try_statements = []

        def find_try_statements(node: TSNode):
            """Recursively find try statements"""
            if node.type == "try_statement":
                try_info = {
                    "has_except": False,
                    "has_finally": False,
                    "exception_types": [],
                }

                for child in node.children:
                    if child.type == "except_clause":
                        try_info["has_except"] = True
                        # Try to extract exception type
                        for exc_child in child.children:
                            if exc_child.type == "identifier":
                                exc_type = self._get_node_text(exc_child)
                                if exc_type not in try_info["exception_types"]:
                                    try_info["exception_types"].append(exc_type)
                    elif child.type == "finally_clause":
                        try_info["has_finally"] = True

                try_statements.append(try_info)

            # Recursively process children
            if node.children:
                for child in node.children:
                    find_try_statements(child)

        find_try_statements(body_node)

        if not try_statements:
            return None

        return {
            "has_try": True,
            "try_count": len(try_statements),
            "try_statements": try_statements,
        }

    def _extract_type_info(self, func_node: TSNode, params_node: TSNode | None) -> dict:
        """
        Extract type information from function (RFC-19 support).

        Parses:
        - Parameters with Optional[T] annotations
        - Return type annotations

        Args:
            func_node: Function definition AST node
            params_node: Parameters node (if available)

        Returns:
            Dictionary with 'parameters' and 'return_type' keys
        """
        type_info = {}

        # Extract parameters
        if params_node is None:
            params_node = self._find_child_by_type(func_node, "parameters")

        if params_node:
            parameters = []

            for child in params_node.children:
                if child.type in ("identifier", "typed_parameter"):
                    param_info = self._parse_parameter(child)
                    if param_info:
                        parameters.append(param_info)

            if parameters:
                type_info["parameters"] = parameters

        # Extract return type
        # Python: def func() -> Optional[str]:
        for child in func_node.children:
            if child.type == "type":
                return_type_text = self._get_node_text(child)
                type_info["return_type"] = return_type_text

                # Check if nullable (Optional[T], T | None)
                if "Optional[" in return_type_text or " | None" in return_type_text or "|None" in return_type_text:
                    type_info["return_nullable"] = True
                else:
                    type_info["return_nullable"] = False
                break

        return type_info

    def _parse_parameter(self, param_node: TSNode) -> dict | None:
        """
        Parse parameter with type annotation.

        Examples:
        - user_id: str → {"name": "user_id", "type": "str", "nullable": False}
        - user_id: Optional[str] → {"name": "user_id", "type": "Optional[str]", "nullable": True}
        - user_id: str | None → {"name": "user_id", "type": "str | None", "nullable": True}

        Args:
            param_node: Parameter AST node

        Returns:
            Parameter info dict or None
        """
        param_name = None
        param_type = None

        if param_node.type == "identifier":
            param_name = self._get_node_text(param_node)
        elif param_node.type == "typed_parameter":
            # Find identifier and type
            for child in param_node.children:
                if child.type == "identifier":
                    param_name = self._get_node_text(child)
                elif child.type == "type":
                    param_type = self._get_node_text(child)

        if not param_name or param_name in ("self", "cls"):
            return None

        param_info = {"name": param_name}

        if param_type:
            param_info["type"] = param_type

            # Check if nullable
            if "Optional[" in param_type or " | None" in param_type or "|None" in param_type:
                param_info["nullable"] = True
            else:
                param_info["nullable"] = False

        return param_info

    def _extract_body_statements(self, body_node: TSNode) -> list[dict]:
        """
        Extract body statements for null analysis (RFC-19 support).

        Extracts:
        - Method calls (x.method())
        - Attribute access (x.attr)
        - Return statements

        Args:
            body_node: Function body block node

        Returns:
            List of statement dictionaries
        """
        statements = []

        def visit_node(node: TSNode):
            # Method call: x.method()
            if node.type == "call":
                func_node = node.child_by_field_name("function")
                if func_node and func_node.type == "attribute":
                    obj_node = func_node.child_by_field_name("object")
                    attr_node = func_node.child_by_field_name("attribute")
                    if obj_node and attr_node:
                        statements.append(
                            {
                                "type": "method_call",
                                "object": self._get_node_text(obj_node),
                                "method": self._get_node_text(attr_node),
                            }
                        )

            # Attribute access: x.attr
            elif node.type == "attribute":
                obj_node = node.child_by_field_name("object")
                attr_node = node.child_by_field_name("attribute")
                if obj_node and attr_node:
                    statements.append(
                        {
                            "type": "field_access",
                            "object": self._get_node_text(obj_node),
                            "field": self._get_node_text(attr_node),
                        }
                    )

            # Return statement
            elif node.type == "return_statement":
                for child in node.children:
                    if child.type != "return":
                        statements.append(
                            {
                                "type": "return",
                                "value": self._get_node_text(child),
                            }
                        )

            # Yield statement (for fixture/generator analysis)
            elif node.type == "expression_statement":
                for child in node.children:
                    if child.type == "yield":
                        # yield can have optional value
                        value_text = ""
                        for yield_child in child.children:
                            if yield_child.type not in ("yield", "from"):
                                value_text = self._get_node_text(yield_child)
                                break
                        statements.append(
                            {
                                "type": "yield",
                                "value": value_text,
                            }
                        )

            # Recurse
            for child in node.children:
                visit_node(child)

        visit_node(body_node)
        return statements

    # ============================================================
    # Private Helper Methods
    # ============================================================

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

    def _record_time(self, key: str, duration_ms: float):
        """Record timing metric."""
        if key in self._timings:
            self._timings[key] += duration_ms
        else:
            self._timings[key] = duration_ms

    def _generate_content_hash(self, content: str) -> str:
        """Generate content hash for node."""
        import hashlib

        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # ============================================================
    # Helper Methods (from IRGenerator)
    # ============================================================

    def _get_node_text(self, node: TSNode, source_bytes: bytes = None) -> str:
        """Get text content of AST node."""
        bytes_to_use = source_bytes if source_bytes is not None else self._source_bytes
        if bytes_to_use is None:
            return ""
        return bytes_to_use[node.start_byte : node.end_byte].decode("utf-8")

    def _find_child_by_type(self, node: TSNode, child_type: str) -> TSNode | None:
        """Find first child node of specific type."""
        for child in node.children:
            if child.type == child_type:
                return child
        return None
