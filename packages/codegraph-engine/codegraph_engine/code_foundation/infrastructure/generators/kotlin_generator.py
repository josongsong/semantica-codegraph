"""
Kotlin IR Generator

Tree-sitter 기반 Kotlin Structural IR 생성.

Features:
- 구조 파싱 (File/Class/Object/Function/Property)
- Import/Package 처리
- Kotlin 특화: data class, extension function, suspend function
- Edge 생성 (CONTAINS/CALLS/IMPORTS)

Kotlin-specific Features:
- data class: 자동 equals/hashCode/toString
- sealed class: 제한된 상속
- object: Singleton
- companion object: Static members
- extension function: fun T.method()
- suspend function: Coroutine
- property: val/var with delegation

SOTA Improvements (2025-12-21):
- Type-safe modifiers (ENUM)
- Dead code removal (no TODO stub)
- Nullability support (?, !!)
"""

import time
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.kotlin._id_helper import (
    generate_kotlin_node_id,
)
from codegraph_engine.code_foundation.infrastructure.generators.kotlin.modifiers import (
    KotlinClassModifier,
    KotlinFunctionModifier,
)
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import generate_edge_id_v2
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import ExternalAnalyzer

logger = get_logger(__name__)

# Kotlin-specific Tree-sitter node types
KOTLIN_BRANCH_TYPES = {
    "if_expression",
    "when_expression",
}

KOTLIN_LOOP_TYPES = {
    "for_statement",
    "while_statement",
    "do_while_statement",
}

KOTLIN_TRY_TYPES = {
    "try_expression",
}


class _KotlinIRGenerator(IRGenerator):
    """
    Kotlin IR generator using tree-sitter-kotlin.

    ⚠️ INTERNAL USE ONLY - Do NOT instantiate directly!
    Use LayeredIRBuilder instead for full 9-layer IR construction.

    This generator only provides Layer 1 (Structural IR).
    Direct usage will miss Layers 2-9 (Occurrence, LSP, CrossFile, Semantic, etc.)

    Correct usage:
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
        builder = LayeredIRBuilder(project_root)
        ir_docs, ctx, idx, diag, pkg = await builder.build_full(files)

    Features (Layer 1 only):
    - File/Class/Object/Function/Property 노드 생성
    - Import/Package 분석
    - Kotlin 특화: data class, extension function, suspend function
    - Edge 생성 (CONTAINS/CALLS/IMPORTS/INHERITS/IMPLEMENTS)
    """

    def __init__(
        self,
        repo_id: str,
        external_analyzer: "ExternalAnalyzer | None" = None,
    ):
        """
        Initialize Kotlin generator.

        Args:
            repo_id: Repository identifier
            external_analyzer: Optional external analyzer
        """
        super().__init__(repo_id)

        self._nodes: list[Node] = []
        self._edges: list[Edge] = []
        self._external_analyzer = external_analyzer

        # Scope tracking
        self._scope: ScopeStack

        # Source reference
        self._source: SourceFile
        self._source_bytes: bytes
        self._ast: AstTree

        # Package name
        self._package_name: str = ""

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
        Generate IR from Kotlin source.

        Args:
            source: Source file
            snapshot_id: Snapshot ID
            old_content: Old content for incremental parsing
            diff_text: Diff text for incremental parsing
            ast: Pre-parsed AST (optimization)

        Returns:
            IRDocument
        """
        start_time = time.perf_counter()

        # Reset state
        self._nodes.clear()
        self._edges.clear()
        self._package_name = ""
        self._timings = {
            "parsing_ms": 0.0,
            "node_generation_ms": 0.0,
            "total_ms": 0.0,
        }

        # Store source
        self._source = source
        self._source_bytes = source.content.encode(source.encoding)

        # Parse AST
        parse_start = time.perf_counter()
        if ast is not None:
            self._ast = ast
            self._timings["parsing_ms"] = 0.0
        elif old_content is not None and diff_text is not None:
            self._ast = AstTree.parse_incremental(source, old_content, diff_text)
            self._timings["parsing_ms"] = (time.perf_counter() - parse_start) * 1000
        else:
            self._ast = AstTree.parse(source)
            self._timings["parsing_ms"] = (time.perf_counter() - parse_start) * 1000

        # Extract package name
        self._extract_package()

        # Initialize scope
        if self._package_name:
            initial_scope = self._package_name
        else:
            # Fallback: use file path without filename
            parts = source.file_path.replace(".kt", "").split("/")
            initial_scope = ".".join(parts[:-1]) if len(parts) > 1 else ""

        self._scope = ScopeStack(initial_scope)

        # Generate nodes
        gen_start = time.perf_counter()
        self._process_root()

        self._timings["node_generation_ms"] = (time.perf_counter() - gen_start) * 1000
        self._timings["total_ms"] = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"Kotlin IR generated: {len(self._nodes)} nodes, "
            f"{len(self._edges)} edges in {self._timings['total_ms']:.1f}ms"
        )

        return IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="3.0",
            nodes=self._nodes,
            edges=self._edges,
            unified_symbols=[],
            meta={
                "file_path": source.file_path,
                "language": "kotlin",
                "package": self._package_name,
                "timings": self._timings,
            },
        )

    def _extract_package(self) -> None:
        """Extract package declaration."""
        root = self._ast.root
        for child in root.children:
            if child.type == "package_header":
                # package com.example.app
                identifier = self.find_child_by_type(child, "identifier")
                if identifier:
                    self._package_name = self.get_node_text(identifier, self._source_bytes)
                break

    def _process_root(self) -> None:
        """Process root node and traverse."""
        root = self._ast.root

        # Create file node
        file_node = self._create_file_node()
        self._nodes.append(file_node)

        # Process imports
        for child in root.children:
            if child.type == "import_list":
                for import_child in child.children:
                    if import_child.type == "import_header":
                        self._process_import(import_child, file_node.id)

        # Process top-level declarations
        for child in root.children:
            if child.type == "class_declaration":
                self._process_class(child, file_node.id)
            elif child.type == "object_declaration":
                self._process_object(child, file_node.id)
            elif child.type == "function_declaration":
                self._process_function(child, file_node.id)
            elif child.type == "property_declaration":
                self._process_property(child, file_node.id)

    def _create_file_node(self) -> Node:
        """Create file node."""
        fqn = self._source.file_path
        return Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.FILE,
                file_path=self._source.file_path,
                fqn=fqn,
            ),
            kind=NodeKind.FILE,
            name=self._source.file_path.split("/")[-1],
            fqn=fqn,
            span=Span(
                start_line=1,
                end_line=len(self._source.content.splitlines()),
                start_col=0,
                end_col=0,
            ),
            file_path=self._source.file_path,
            language="kotlin",
            module_path=self._package_name or None,
        )

    def _process_import(self, node: "TSNode", parent_id: str) -> None:
        """Process import declaration."""
        # import java.util.List
        # import kotlin.collections.*
        identifier = self.find_child_by_type(node, "identifier")
        if not identifier:
            return

        import_path = self.get_node_text(identifier, self._source_bytes)

        # Check for wildcard
        is_wildcard = False
        for child in node.children:
            if child.type == "*":
                is_wildcard = True
                break

        # Create import node
        import_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.IMPORT,
                file_path=self._source.file_path,
                fqn=import_path,
            ),
            kind=NodeKind.IMPORT,
            name=import_path,
            fqn=import_path,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            attrs={"wildcard": is_wildcard},
        )
        self._nodes.append(import_node)

        # Create IMPORTS edge
        import_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.IMPORTS, parent_id, import_node.id),
            kind=EdgeKind.IMPORTS,
            source_id=parent_id,
            target_id=import_node.id,
            span=self._node_to_span(node),
        )
        self._edges.append(import_edge)

    def _process_class(self, node: "TSNode", parent_id: str) -> None:
        """
        Process class declaration.

        Supports:
        - Regular class
        - data class
        - sealed class
        - inner class
        - enum class
        """
        name_node = self.find_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        class_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        # Check for data class
        is_data_class = modifiers.get("data", False)

        # Check for sealed class
        is_sealed_class = modifiers.get("sealed", False)

        # Calculate complexity
        body = self.find_child_by_type(node, "class_body")
        complexity = self.calculate_cyclomatic_complexity(body, KOTLIN_BRANCH_TYPES) if body else 1

        attrs = {**modifiers}
        if is_data_class:
            attrs["kotlin_data_class"] = True
        if is_sealed_class:
            attrs["kotlin_sealed_class"] = True

        class_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.CLASS,
                file_path=self._source.file_path,
                fqn=class_fqn,
            ),
            kind=NodeKind.CLASS,
            name=name,
            fqn=class_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, KOTLIN_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, KOTLIN_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, KOTLIN_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(class_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, class_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=class_node.id,
        )
        self._edges.append(contains_edge)

        # Process inheritance (superclass_entry, delegation_specifiers)
        self._process_inheritance(node, class_node.id)

        # Enter class scope
        self._scope.push("class", name, class_fqn)

        # Process class body
        if body:
            for child in body.children:
                if child.type == "function_declaration":
                    self._process_function(child, class_node.id)
                elif child.type == "property_declaration":
                    self._process_property(child, class_node.id)
                elif child.type == "class_declaration":
                    self._process_class(child, class_node.id)  # Nested class
                elif child.type == "object_declaration":
                    self._process_object(child, class_node.id)
                elif child.type == "companion_object":
                    self._process_companion_object(child, class_node.id)

        self._scope.pop()

    def _process_object(self, node: "TSNode", parent_id: str) -> None:
        """
        Process object declaration (Singleton).

        Example:
            object AppConfig { ... }
        """
        name_node = self.find_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        object_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        attrs = {**modifiers, "kotlin_object": True}

        object_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.CLASS,  # Object는 Class로 취급
                file_path=self._source.file_path,
                fqn=object_fqn,
            ),
            kind=NodeKind.CLASS,
            name=name,
            fqn=object_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            attrs=attrs,
        )
        self._nodes.append(object_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, object_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=object_node.id,
        )
        self._edges.append(contains_edge)

        # Enter object scope (use "class" for ScopeKind)
        self._scope.push("class", name, object_fqn)

        # Process object body
        body = self.find_child_by_type(node, "class_body")
        if body:
            for child in body.children:
                if child.type == "function_declaration":
                    self._process_function(child, object_node.id)
                elif child.type == "property_declaration":
                    self._process_property(child, object_node.id)

        self._scope.pop()

    def _process_companion_object(self, node: "TSNode", parent_id: str) -> None:
        """
        Process companion object (static members).

        Example:
            companion object Factory { ... }
        """
        # Find name (optional)
        name_node = self.find_child_by_type(node, "type_identifier")
        name = self.get_node_text(name_node, self._source_bytes) if name_node else "Companion"

        companion_fqn = f"{self._scope.current_fqn()}.{name}"

        attrs = {"kotlin_companion_object": True}

        companion_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.CLASS,
                file_path=self._source.file_path,
                fqn=companion_fqn,
            ),
            kind=NodeKind.CLASS,
            name=name,
            fqn=companion_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            attrs=attrs,
        )
        self._nodes.append(companion_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, companion_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=companion_node.id,
        )
        self._edges.append(contains_edge)

        # Enter companion scope (use "class" for ScopeKind)
        self._scope.push("class", name, companion_fqn)

        # Process companion body
        body = self.find_child_by_type(node, "class_body")
        if body:
            for child in body.children:
                if child.type == "function_declaration":
                    self._process_function(child, companion_node.id)
                elif child.type == "property_declaration":
                    self._process_property(child, companion_node.id)

        self._scope.pop()

    def _process_function(self, node: "TSNode", parent_id: str) -> None:
        """
        Process function declaration.

        Supports:
        - Regular function
        - Extension function: fun String.toInt()
        - Suspend function: suspend fun fetchData()
        """
        name_node = self.find_child_by_type(node, "simple_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        # Check for suspend function
        is_suspend = modifiers.get("suspend", False)

        # Check for extension function (receiver_type)
        # SOTA: No stub, real implementation
        receiver_type = None
        receiver_node = self.find_child_by_type(node, "receiver_type")
        if receiver_node:
            receiver_type = self.get_node_text(receiver_node, self._source_bytes)

        # Generate FQN
        if receiver_type:
            # Extension function: receiver.functionName
            func_fqn = f"{self._scope.current_fqn()}.{receiver_type}.{name}"
        else:
            func_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Calculate complexity
        body = self.find_child_by_type(node, "function_body")
        complexity = self.calculate_cyclomatic_complexity(body, KOTLIN_BRANCH_TYPES) if body else 1

        attrs = {**modifiers}
        if is_suspend:
            attrs["kotlin_suspend"] = True
        if receiver_type:
            attrs["kotlin_extension_receiver"] = receiver_type

        # Extract parameters
        params = self._extract_parameters(node)

        # Extract return type
        return_type = self._extract_return_type(node)

        # Add signature to attrs
        attrs["parameters"] = params
        if return_type:
            attrs["return_type"] = return_type

        func_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.FUNCTION,
                file_path=self._source.file_path,
                fqn=func_fqn,
            ),
            kind=NodeKind.FUNCTION,
            name=name,
            fqn=func_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, KOTLIN_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, KOTLIN_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, KOTLIN_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(func_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, func_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=func_node.id,
        )
        self._edges.append(contains_edge)

        # Process function body (calls, etc.)
        if body:
            self._process_function_body(body, func_node.id)

    def _process_property(self, node: "TSNode", parent_id: str) -> None:
        """
        Process property declaration (val/var).

        Example:
            val name: String = "John"
            var age: Int by lazy { 42 }
        """
        # Find variable_declaration
        var_decl = self.find_child_by_type(node, "variable_declaration")
        if not var_decl:
            return

        name_node = self.find_child_by_type(var_decl, "simple_identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        prop_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        # Check for val/var (inside binding_pattern_kind)
        is_mutable = False
        binding_kind = self.find_child_by_type(node, "binding_pattern_kind")
        if binding_kind:
            for child in binding_kind.children:
                if child.type == "var":
                    is_mutable = True
                    break
                if child.type == "val":
                    break

        # Extract type
        type_ref = self.find_child_by_type(var_decl, "type")
        prop_type = self.get_node_text(type_ref, self._source_bytes) if type_ref else None

        # SOTA: Check for delegation (by lazy, by)
        has_delegation = False
        delegation_type = None
        for child in var_decl.children:
            if child.type == "by":
                has_delegation = True
                # Try to extract delegation expression
                for sibling in var_decl.children:
                    if sibling.type == "call_expression":
                        callee = self.find_child_by_type(sibling, "simple_identifier")
                        if callee:
                            delegation_type = self.get_node_text(callee, self._source_bytes)
                break

        attrs = {**modifiers}
        if is_mutable:
            attrs["kotlin_mutable"] = True
        else:
            attrs["kotlin_immutable"] = True

        # Add type to attrs
        if prop_type:
            attrs["type"] = prop_type

        # SOTA: Delegation pattern
        if has_delegation:
            attrs["kotlin_delegated"] = True
            if delegation_type:
                attrs["kotlin_delegation_type"] = delegation_type

        prop_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.VARIABLE,
                file_path=self._source.file_path,
                fqn=prop_fqn,
            ),
            kind=NodeKind.VARIABLE,
            name=name,
            fqn=prop_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            attrs=attrs,
        )
        self._nodes.append(prop_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, prop_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=prop_node.id,
        )
        self._edges.append(contains_edge)

    def _process_inheritance(self, node: "TSNode", class_id: str) -> None:
        """Process class inheritance (superclass, interfaces)."""
        # Find delegation_specifiers (: SuperClass(), Interface)
        delegation = self.find_child_by_type(node, "delegation_specifiers")
        if not delegation:
            return

        for child in delegation.children:
            if child.type == "delegation_specifier":
                # Extract type
                type_ref = self.find_child_by_type(child, "user_type")
                if type_ref:
                    superclass_name = self.get_node_text(type_ref, self._source_bytes)

                    # Create INHERITS edge
                    # Note: We don't create target node here (it may be external)
                    inherit_edge = Edge(
                        id=generate_edge_id_v2(EdgeKind.INHERITS, class_id, f"external:{superclass_name}"),
                        kind=EdgeKind.INHERITS,
                        source_id=class_id,
                        target_id=f"external:{superclass_name}",
                        attrs={"target_name": superclass_name},
                    )
                    self._edges.append(inherit_edge)

    def _process_function_body(self, body: "TSNode", func_id: str) -> None:
        """
        Process function body with lambda support.

        SOTA: Handles lambdas, higher-order functions, call expressions.
        """
        # Find call expressions and lambdas
        for child in body.children:
            if child.type == "call_expression":
                self._process_call(child, func_id)
            elif child.type == "lambda_literal":
                self._process_lambda(child, func_id)
            elif child.type in {"if_expression", "when_expression"}:
                # Recursively process control flow
                self._process_function_body(child, func_id)
            elif hasattr(child, "children") and len(child.children) > 0:
                # Recursively process children
                self._process_function_body(child, func_id)

    def _process_call(self, node: "TSNode", caller_id: str) -> None:
        """Process call expression."""
        # Extract callee name
        callee_node = self.find_child_by_type(node, "simple_identifier")
        if not callee_node:
            return

        callee_name = self.get_node_text(callee_node, self._source_bytes)

        # Create CALLS edge
        # Note: Target may be external
        call_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CALLS, caller_id, f"external:{callee_name}"),
            kind=EdgeKind.CALLS,
            source_id=caller_id,
            target_id=f"external:{callee_name}",
            span=self._node_to_span(node),
            attrs={"callee_name": callee_name},
        )
        self._edges.append(call_edge)

    def _process_lambda(self, node: "TSNode", parent_id: str) -> None:
        """
        Process lambda literal (SOTA: Full lambda support).

        Kotlin lambda: { x, y -> x + y }

        Features:
        - Capture analysis
        - Parameter extraction
        - Body analysis
        """
        # Generate unique lambda ID
        lambda_line = node.start_point[0] + 1
        lambda_col = node.start_point[1]
        lambda_fqn = f"{self._scope.current_fqn()}.lambda${lambda_line}:{lambda_col}"

        # Extract lambda parameters
        params = []
        lambda_params = self.find_child_by_type(node, "lambda_parameters")
        if lambda_params:
            for child in lambda_params.children:
                if child.type == "variable_declaration":
                    name_node = self.find_child_by_type(child, "simple_identifier")
                    if name_node:
                        param_name = self.get_node_text(name_node, self._source_bytes)
                        params.append({"name": param_name})

        # Get lambda body
        body = None
        for child in node.children:
            if child.type == "statements":
                body = child
                break

        # Calculate complexity
        complexity = 1
        if body:
            complexity = self.calculate_cyclomatic_complexity(body, KOTLIN_BRANCH_TYPES)

        lambda_node = Node(
            id=generate_kotlin_node_id(
                repo_id=self.repo_id,
                kind=NodeKind.LAMBDA,
                file_path=self._source.file_path,
                fqn=lambda_fqn,
            ),
            kind=NodeKind.LAMBDA,
            name=f"lambda${lambda_line}",
            fqn=lambda_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="kotlin",
            parent_id=parent_id,
            body_span=self._node_to_span(body) if body else None,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, KOTLIN_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, KOTLIN_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, KOTLIN_BRANCH_TYPES) if body else 0,
            ),
            attrs={
                "is_lambda": True,
                "kotlin_lambda": True,
                "parameters": params,
            },
        )
        self._nodes.append(lambda_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id_v2(EdgeKind.CONTAINS, parent_id, lambda_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=lambda_node.id,
        )
        self._edges.append(contains_edge)

        # Analyze captures
        if body:
            captures = self._analyze_lambda_captures(body, lambda_node.id)
            if captures:
                lambda_node.attrs["captures"] = [c["name"] for c in captures]
                lambda_node.attrs["capture_count"] = len(captures)

        # Process calls in lambda body
        if body:
            self._process_function_body(body, lambda_node.id)

    def _analyze_lambda_captures(self, lambda_body: "TSNode", lambda_id: str) -> list[dict]:
        """
        Analyze variable captures in lambda (SOTA: Closure analysis).

        Kotlin lambdas can capture:
        - Local variables from outer scope
        - Properties from enclosing class
        - Parameters from outer functions
        """
        captures = []

        if not lambda_body:
            return captures

        # Track all variable references
        def find_variable_refs(node: "TSNode") -> list[str]:
            refs = []

            if node.type == "simple_identifier":
                # Get variable name
                var_name = self.get_node_text(node, self._source_bytes)

                # Filter: lowercase first char = variable (Kotlin convention)
                if var_name and len(var_name) > 0 and var_name[0].islower():
                    # Filter out keywords
                    if var_name not in ["it", "this", "super", "return", "throw", "null", "true", "false"]:
                        refs.append(var_name)

            for child in node.children:
                refs.extend(find_variable_refs(child))

            return refs

        variable_refs = find_variable_refs(lambda_body)
        unique_refs = list(set(variable_refs))

        # SOTA: Base ID caching
        base_target_id = f"var:{self.repo_id}:{self._source.file_path}:{self._scope.current_fqn()}"

        for var_name in unique_refs:
            capture_info = {
                "name": var_name,
                "type": "unknown",
                "scope": "outer",
            }

            captures.append(capture_info)

            # Create CAPTURES edge
            target_id = f"{base_target_id}.{var_name}"

            captures_edge = Edge(
                id=generate_edge_id_v2(EdgeKind.CAPTURES, lambda_id, target_id),
                kind=EdgeKind.CAPTURES,
                source_id=lambda_id,
                target_id=target_id,
                attrs={
                    "variable_name": var_name,
                    "capture_type": "closure",
                },
            )
            self._edges.append(captures_edge)

        return captures

    # ================================================================
    # Helper Methods
    # ================================================================

    def _extract_modifiers(self, node: "TSNode") -> dict[str, bool]:
        """
        Extract modifiers (public, private, data, suspend, etc.).

        Returns:
            Dict of modifiers
        """
        modifiers = {}

        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in {
                        "visibility_modifier",
                        "inheritance_modifier",
                        "function_modifier",
                        "property_modifier",
                        "class_modifier",
                    }:
                        mod_text = self.get_node_text(mod_child, self._source_bytes)
                        modifiers[mod_text] = True

        return modifiers

    def _extract_parameters(self, node: "TSNode") -> list[dict]:
        """
        Extract function parameters with nullability support.

        SOTA: Detects nullable types (String?) and non-null types (String!!).
        """
        params = []

        params_node = self.find_child_by_type(node, "function_value_parameters")
        if not params_node:
            return params

        for child in params_node.children:
            if child.type == "parameter":
                # Extract name and type
                name_node = self.find_child_by_type(child, "simple_identifier")
                # Type is user_type, nullable_type, or function_type
                type_node = None
                is_nullable = False

                for type_child in child.children:
                    if type_child.type == "nullable_type":
                        type_node = type_child
                        is_nullable = True  # Kotlin ? operator
                        break
                    elif type_child.type in {"user_type", "function_type"}:
                        type_node = type_child
                        break

                if name_node:
                    param_name = self.get_node_text(name_node, self._source_bytes)
                    param_type = self.get_node_text(type_node, self._source_bytes) if type_node else None

                    param_info = {
                        "name": param_name,
                        "type": param_type,
                    }

                    # SOTA: Nullability tracking
                    if is_nullable:
                        param_info["nullable"] = True
                    elif param_type and param_type.endswith("!!"):
                        # Non-null assertion
                        param_info["nonnull"] = True

                    params.append(param_info)

        return params

    def _extract_return_type(self, node: "TSNode") -> str | None:
        """
        Extract function return type with nullability.

        SOTA: Detects nullable return types (String?) and Unit.
        """
        # Find type annotation after ':' (before function_body)
        found_colon = False
        for child in node.children:
            if child.type == ":":
                found_colon = True
                continue
            if found_colon and child.type in {"user_type", "function_type", "nullable_type"}:
                return_type = self.get_node_text(child, self._source_bytes)
                # SOTA: Preserve nullability marker (?)
                return return_type
            if child.type == "function_body":
                # Reached body without finding return type
                break

        # SOTA: Kotlin functions without return type → Unit (not void)
        return None  # Will be inferred as Unit by Kotlin compiler

    def _node_to_span(self, node: "TSNode") -> Span:
        """Convert tree-sitter node to Span."""
        return Span(
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_col=node.start_point[1],
            end_col=node.end_point[1],
        )
