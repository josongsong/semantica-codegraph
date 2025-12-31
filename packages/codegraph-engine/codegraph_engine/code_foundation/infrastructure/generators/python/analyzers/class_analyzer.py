"""
Class Analyzer for Python IR

Handles class definition processing including inheritance, fields, and decorators.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

from codegraph_engine.code_foundation.infrastructure.generators.python._id_helper import generate_python_node_id
from codegraph_engine.code_foundation.infrastructure.generators.python.builders.edge_builder import EdgeBuilder
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    generate_edge_id,
    generate_edge_id_v2,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, Node, NodeKind
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile
from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver


class ClassAnalyzer:
    """
    Handles class definition processing.

    Responsibilities:
    - Process class definitions
    - Extract base classes and resolve inheritance
    - Create CLASS nodes with all attributes
    - Create CONTAINS edges (parent → class)
    - Create INHERITS edges (child → base class)
    - Process class-level fields
    - Handle class decorators
    - Register classes in scope

    This analyzer focuses on class structure,
    delegating method processing to FunctionAnalyzer.

    Example:
        >>> nodes = []
        >>> edges = []
        >>> scope = ScopeStack("main")
        >>> edge_builder = EdgeBuilder(edges)
        >>> analyzer = ClassAnalyzer(
        ...     "repo1", nodes, edges, scope, edge_builder,
        ...     type_resolver, source, source_bytes, ast, timings
        ... )
        >>> # Process: class Child(Parent): ...
        >>> analyzer.process_class(class_ast_node)
        >>> assert len(nodes) >= 1  # CLASS node created
    """

    def __init__(
        self,
        repo_id: str,
        nodes: list[Node],
        edges: list[Edge],
        scope: ScopeStack,
        edge_builder: EdgeBuilder,
        type_resolver: TypeResolver,
        types: dict,
        source: SourceFile,
        source_bytes: bytes,
        ast: AstTree,
        timings: dict,
    ):
        """
        Initialize class analyzer.

        Args:
            repo_id: Repository identifier
            nodes: Shared node collection (will be mutated)
            edges: Shared edge collection (will be mutated)
            scope: Scope tracking stack
            edge_builder: Edge builder for CONTAINS edges
            type_resolver: Type resolution service
            types: Shared type entity collection
            source: Source file reference
            source_bytes: Source bytes (for text extraction)
            ast: AST tree (for span extraction)
            timings: Performance timing tracker
        """
        self._repo_id = repo_id
        self._nodes = nodes
        self._edges = edges
        self._scope = scope
        self._edge_builder = edge_builder
        self._type_resolver = type_resolver
        self._types = types
        self._source = source
        self._source_bytes = source_bytes
        self._ast = ast
        self._timings = timings
        self._temp_decorators = None

    def process_class(self, node: TSNode, method_processor=None):
        """
        Process class_definition node.

        Args:
            node: class_definition AST node
            method_processor: Optional callback for processing methods
                              Signature: method_processor(func_node, is_method=True)

        Example:
            >>> # class MyClass(Parent): ...
            >>> analyzer.process_class(class_ast)
            >>> # With method processor:
            >>> analyzer.process_class(class_ast, method_processor=func_analyzer.process_function)
        """
        start = time.perf_counter()

        # Get class name
        name_node = self._find_child_by_type(node, "identifier")
        if not name_node:
            return

        class_name = self._get_node_text(name_node)

        # Build FQN
        class_fqn = self._scope.build_fqn(class_name)

        # Generate node ID
        span = self._ast.get_span(node)
        node_id = generate_python_node_id(
            repo_id=self._repo_id,
            kind=NodeKind.CLASS,
            file_path=self._source.file_path,
            fqn=class_fqn,
        )

        # Extract docstring
        docstring = self._extract_docstring(node)

        # Get class body
        body_node = self._find_child_by_type(node, "block")
        body_span = self._ast.get_span(body_node) if body_node else None

        # Build attrs dict with decorators if present
        attrs = {}
        if self._temp_decorators:
            attrs["decorators"] = self._temp_decorators

        # Extract base classes for inheritance tracking
        base_classes = self.extract_base_classes(node)
        if base_classes:
            # Resolve base class names to FQNs
            base_fqns = []
            for base_name in base_classes:
                resolved_fqn = self._resolve_base_class_fqn(base_name)
                base_fqns.append(resolved_fqn)
            attrs["base_classes"] = base_fqns

        # Generate content hash
        content_hash = self._generate_content_hash(self._get_node_text(node))

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
            content_hash=content_hash,
            attrs=attrs,
        )

        self._nodes.append(class_node)

        # Add CONTAINS edge from parent
        parent_node_id = self._scope.current.node_id
        assert parent_node_id is not None, "Parent scope must have node_id set"
        self._edge_builder.add_contains_edge(parent_node_id, node_id, span)

        # Add INHERITS edges to base classes
        if base_classes:
            self._create_inherits_edges(node_id, class_fqn, base_classes, span)

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
                    if method_processor:
                        method_processor(child, is_method=True)
                elif child.type == "decorated_definition":
                    # Handle decorated methods
                    if method_processor:
                        self._process_decorated_method(child, method_processor)
                elif child.type == "expression_statement":
                    # Could be class-level assignment (field)
                    self._process_potential_field(child)
                elif child.type == "assignment":
                    # Direct class-level field assignment (type-annotated)
                    self.process_class_level_field(child)
        method_time_after = self._timings.get("function_process_ms", 0)
        method_time_in_class = method_time_after - method_time_before

        # Pop class scope
        self._scope.pop()

        # Record class overhead only (exclude method processing time)
        duration_ms = (time.perf_counter() - start) * 1000
        class_overhead = duration_ms - method_time_in_class
        self._record_time("class_process_ms", class_overhead)

    def process_class_with_decorators(self, node: TSNode, decorators: list[str], method_processor=None):
        """
        Process class with decorators.

        Args:
            node: class_definition AST node
            decorators: List of decorator strings (e.g., ["dataclass", "final"])
            method_processor: Optional callback for processing methods

        Example:
            >>> # @dataclass
            >>> # class Point: ...
            >>> analyzer.process_class_with_decorators(ast, ["dataclass"])
        """
        # Store decorators for later use
        self._temp_decorators = decorators
        # Process class normally
        self.process_class(node, method_processor)
        # Clear temp decorators
        self._temp_decorators = None

    def extract_base_classes(self, class_node: TSNode) -> list[str]:
        """
        Extract base class names from class_definition AST node.

        Args:
            class_node: Tree-sitter class_definition node

        Returns:
            List of base class names (e.g., ["Parent", "Mixin", "module.Base"])

        Example:
            >>> # class Child(Parent, Mixin): ...
            >>> bases = analyzer.extract_base_classes(ast)
            >>> assert bases == ["Parent", "Mixin"]
        """
        base_classes = []

        # Find argument_list node (contains base classes)
        for child in class_node.children:
            if child.type == "argument_list":
                # Extract each base class from argument_list
                for arg_child in child.children:
                    if arg_child.type == "identifier":
                        # Simple base class: class Child(Parent)
                        base_name = self._get_node_text(arg_child)
                        if base_name:
                            base_classes.append(base_name)
                    elif arg_child.type == "attribute":
                        # Qualified base class: class Child(module.Parent)
                        base_name = self._get_node_text(arg_child)
                        if base_name:
                            base_classes.append(base_name)

        return base_classes

    def process_class_level_field(self, assignment_node: TSNode):
        """
        Process class-level field from assignment node.

        Handles:
        - Type-annotated fields: name: str
        - Fields with defaults: age: int = 0

        Args:
            assignment_node: assignment AST node

        Example:
            >>> # class MyClass:
            >>> #     name: str
            >>> #     age: int = 0
            >>> analyzer.process_class_level_field(assignment_ast)
        """
        # Extract field name and check for type annotation
        field_name = None
        type_node = None
        has_type_annotation = False
        default_value = None

        for child in assignment_node.children:
            if child.type == "identifier" and field_name is None:
                field_name = self._get_node_text(child)
            elif child.type == ":":
                has_type_annotation = True
            elif child.type == "type" and has_type_annotation:
                type_node = child
            elif child.type not in ("identifier", ":", "type", "="):
                # This is the default value
                if has_type_annotation or field_name:
                    default_value = self._get_node_text(child)

        # Only create FIELD nodes for type-annotated fields (PEP 526)
        # Simple assignments (count = 0) are treated as class variables, not fields
        if not field_name or not has_type_annotation:
            return

        # Build FQN
        field_fqn = self._scope.build_fqn(field_name)

        # Generate node ID
        span = self._ast.get_span(assignment_node)
        node_id = generate_python_node_id(
            repo_id=self._repo_id,
            kind=NodeKind.FIELD,
            file_path=self._source.file_path,
            fqn=field_fqn,
        )

        # Resolve type if available
        declared_type_id = None
        if type_node:
            type_text = self._get_node_text(type_node)
            type_entity = self._type_resolver.resolve_type(type_text)
            if type_entity and self._types is not None:
                declared_type_id = type_entity.id
                self._types[declared_type_id] = type_entity

        # Build attrs
        attrs = {
            "field_kind": "class_field",  # class-level field
        }
        if default_value:
            attrs["default_value"] = default_value

        # Create FIELD node
        field_node = Node(
            id=node_id,
            kind=NodeKind.FIELD,
            fqn=field_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=field_name,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.current.node_id,
            declared_type_id=declared_type_id,
            attrs=attrs,
        )

        self._nodes.append(field_node)

        # Add CONTAINS edge from class
        parent_node_id = self._scope.current.node_id
        assert parent_node_id is not None, "Parent class must have node_id set"
        self._edge_builder.add_contains_edge(parent_node_id, node_id, span)

    # ============================================================
    # Private Helper Methods
    # ============================================================

    def _process_potential_field(self, node: TSNode):
        """
        Process potential class field (class-level assignment in expression_statement).

        Args:
            node: expression_statement node
        """
        # Check if this contains an assignment
        assignment_node = None
        for child in node.children:
            if child.type == "assignment":
                assignment_node = child
                break

        if not assignment_node:
            return

        # Delegate to class-level field processor
        self.process_class_level_field(assignment_node)

    def _resolve_base_class_fqn(self, base_name: str) -> str:
        """
        Resolve base class name to FQN.

        Args:
            base_name: Base class name (e.g., "Parent" or "module.Parent")

        Returns:
            Fully qualified name of base class
        """
        if "." in base_name:
            # Already qualified (e.g., module.Class)
            return base_name

        # Simple name - resolve via imports or local symbols
        # 1. Check if it's an imported name
        imported_symbol = self._scope.resolve_import(base_name)
        if imported_symbol:
            # It's an import, use the full import path
            return imported_symbol

        # 2. Try to find in registered symbols (local class)
        base_node_id = self._scope.lookup_symbol(base_name)
        if base_node_id:
            # Found locally, build FQN
            return f"{self._scope.module.fqn}.{base_name}"

        # Not found - assume it's in current module (builtins or undefined)
        return f"{self._scope.module.fqn}.{base_name}"

    def _create_inherits_edges(self, child_id: str, child_fqn: str, base_classes: list[str], span):
        """
        Create INHERITS edges from child class to base classes.

        Args:
            child_id: Child class node ID
            child_fqn: Child class FQN
            base_classes: List of base class names
            span: Span for edge
        """
        for base_name in base_classes:
            base_node_id = None

            # Try to find base class node
            if "." not in base_name:
                # Simple name - look up in current scope
                base_node_id = self._scope.lookup_symbol(base_name)

            # SOTA FIX: If not found in scope, create external reference
            if not base_node_id:
                # Create external base class node for imported/builtin classes
                base_fqn = self._resolve_base_class_fqn(base_name)

                # Create or find external node
                base_node_id = generate_python_node_id(
                    repo_id=self._repo_id,
                    kind=NodeKind.CLASS,
                    file_path="<external>",
                    fqn=base_fqn,
                )

                # Check if external node already exists
                existing = any(n.id == base_node_id for n in self._nodes)

                if not existing:
                    # Create external class node
                    from codegraph_engine.code_foundation.infrastructure.ir.models import Span

                    external_node = Node(
                        id=base_node_id,
                        kind=NodeKind.CLASS,
                        name=base_name.split(".")[-1],
                        fqn=base_fqn,
                        file_path="<external>",
                        language="python",
                        span=Span(start_line=0, start_col=0, end_line=0, end_col=0),
                        module_path="<external>",
                        attrs={"external": True, "reason": "base_class"},
                    )
                    self._nodes.append(external_node)

            # Create INHERITS edge (child → parent)
            # RFC-031 Phase B
            edge_id = generate_edge_id_v2(
                kind=EdgeKind.INHERITS.value,
                source_id=child_id,
                target_id=base_node_id,
            )
            inherits_edge = Edge(
                id=edge_id,
                kind=EdgeKind.INHERITS,
                source_id=child_id,
                target_id=base_node_id,
                span=span,
                attrs={
                    "child_class": child_fqn,
                    "parent_class": base_name,
                },
            )
            self._edges.append(inherits_edge)

    def _process_decorated_method(self, node: TSNode, method_processor):
        """
        Process decorated method within class.

        Args:
            node: decorated_definition AST node
            method_processor: Callback for processing methods
        """
        # Extract decorators and find the function_definition
        decorators = []
        func_node = None
        for dec_child in node.children:
            if dec_child.type == "decorator":
                dec_text = self._get_node_text(dec_child)
                dec_text = dec_text.lstrip("@").strip()
                decorators.append(dec_text)
            elif dec_child.type == "function_definition":
                func_node = dec_child

        if func_node and method_processor:
            # Call method processor with decorators
            # Note: method_processor should accept (node, decorators, is_method)
            # For now, we'll call the basic version
            method_processor(func_node, is_method=True)

    def _extract_docstring(self, node: TSNode) -> str | None:
        """
        Extract docstring from class definition.

        Args:
            node: class_definition AST node

        Returns:
            Docstring text or None
        """
        # Find block node
        body_node = self._find_child_by_type(node, "block")
        if not body_node:
            return None

        # Check first statement in block
        for child in body_node.children:
            # Docstring can be directly a string node
            if child.type == "string":
                docstring = self._get_node_text(child)
                return self._clean_docstring(docstring)
            # Or wrapped in expression_statement
            elif child.type == "expression_statement":
                # Check if it contains a string
                for expr_child in child.children:
                    if expr_child.type == "string":
                        docstring = self._get_node_text(expr_child)
                        return self._clean_docstring(docstring)
            # Stop after first non-comment/non-string statement
            if child.type not in ("comment", "expression_statement", "string"):
                break

        return None

    def _clean_docstring(self, raw_docstring: str) -> str:
        """
        Clean docstring by removing quotes and normalizing whitespace.

        Args:
            raw_docstring: Raw docstring text

        Returns:
            Cleaned docstring
        """
        # Remove triple quotes
        text = raw_docstring.strip()
        if text.startswith('"""') and text.endswith('"""'):
            text = text[3:-3]
        elif text.startswith("'''") and text.endswith("'''"):
            text = text[3:-3]
        elif text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        elif text.startswith("'") and text.endswith("'"):
            text = text[1:-1]

        # Normalize whitespace
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

    def _get_node_text(self, node: TSNode) -> str:
        """Get text content of AST node."""
        return self._source_bytes[node.start_byte : node.end_byte].decode("utf-8")

    def _find_child_by_type(self, node: TSNode, child_type: str) -> TSNode | None:
        """Find first child node of specific type."""
        for child in node.children:
            if child.type == child_type:
                return child
        return None
