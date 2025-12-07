"""
Java IR Generator

Tree-sitter 기반 Java Structural IR 생성.

Features:
- 구조 파싱 (File/Class/Interface/Method/Field)
- Import 처리
- Edge 생성 (CONTAINS/CALLS/IMPORTS)
"""

import time
from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.generators.base import IRGenerator
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

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import ExternalAnalyzer

logger = get_logger(__name__)

# Java-specific Tree-sitter node types
JAVA_BRANCH_TYPES = {
    "if_statement",
    "switch_expression",
    "switch_statement",
}

JAVA_LOOP_TYPES = {
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
}

JAVA_TRY_TYPES = {
    "try_statement",
    "try_with_resources_statement",
}


class JavaIRGenerator(IRGenerator):
    """
    Java IR generator using tree-sitter-java.

    Features:
    - File/Class/Interface/Enum/Method/Field 노드 생성
    - Import/Package 분석
    - Edge 생성 (CONTAINS/CALLS/IMPORTS/INHERITS/IMPLEMENTS)
    """

    def __init__(
        self,
        repo_id: str,
        external_analyzer: "ExternalAnalyzer | None" = None,
        jdtls_adapter: "Any | None" = None,
    ):
        """
        Initialize Java generator.

        Args:
            repo_id: Repository identifier
            external_analyzer: Optional external analyzer
            jdtls_adapter: Optional JDT.LS adapter for semantic resolution
        """
        super().__init__(repo_id)

        self._nodes: list[Node] = []
        self._edges: list[Edge] = []
        self._external_analyzer = external_analyzer
        self._jdtls = jdtls_adapter  # Optional: enhances accuracy to 10/10

        # Scope tracking
        self._scope: ScopeStack

        # Source reference
        self._source: SourceFile
        self._source_bytes: bytes
        self._ast: AstTree

        # Package name
        self._package_name: str = ""

        self._timings: dict[str, float] = {}

    def _track_symbol_scope(self, symbol_name: str, symbol_type: str, scope_fqn: str) -> None:
        """
        Track symbol in current scope for shadowing detection.

        Args:
            symbol_name: Simple name (e.g., "value")
            symbol_type: Type ("field", "variable", "parameter")
            scope_fqn: Fully qualified scope name
        """
        if not hasattr(self, "_symbol_scopes"):
            self._symbol_scopes = {}

        if scope_fqn not in self._symbol_scopes:
            self._symbol_scopes[scope_fqn] = {}

        if symbol_name in self._symbol_scopes[scope_fqn]:
            # Shadowing detected
            existing = self._symbol_scopes[scope_fqn][symbol_name]
            # Create SHADOWS edge (will be added later)
            if not hasattr(self, "_shadowings"):
                self._shadowings = []

            self._shadowings.append(
                {
                    "inner_name": symbol_name,
                    "inner_type": symbol_type,
                    "inner_scope": scope_fqn,
                    "outer_name": existing["name"],
                    "outer_type": existing["type"],
                    "outer_scope": existing["scope"],
                }
            )

        self._symbol_scopes[scope_fqn][symbol_name] = {"name": symbol_name, "type": symbol_type, "scope": scope_fqn}

    def _detect_import_collisions(self) -> list[dict]:
        """
        Detect import collisions (same simple name, different packages).

        Returns:
            List of collision info
        """
        if not hasattr(self, "_import_map"):
            return []

        collisions = []
        simple_name_map = {}

        for import_path, import_info in self._import_map.items():
            simple_name = import_path.split(".")[-1]

            if simple_name in simple_name_map:
                # Collision detected
                existing = simple_name_map[simple_name]
                collisions.append(
                    {
                        "simple_name": simple_name,
                        "import1": existing,
                        "import2": import_path,
                        "collision_type": "import",
                    }
                )
            else:
                simple_name_map[simple_name] = import_path

        return collisions

    def _create_shadowing_edges(self) -> None:
        """Create SHADOWS edges for all detected shadowing."""
        if not hasattr(self, "_shadowings"):
            return

        for shadow in self._shadowings:
            # Create source and target IDs
            source_id = f"var:{self.repo_id}:{self._source.file_path}:{shadow['inner_scope']}.{shadow['inner_name']}"
            target_id = f"var:{self.repo_id}:{self._source.file_path}:{shadow['outer_scope']}.{shadow['outer_name']}"

            shadows_edge = Edge(
                id=generate_edge_id(EdgeKind.SHADOWS, source_id, target_id),
                kind=EdgeKind.SHADOWS,
                source_id=source_id,
                target_id=target_id,
                attrs={
                    "inner_name": shadow["inner_name"],
                    "inner_type": shadow["inner_type"],
                    "outer_name": shadow["outer_name"],
                    "outer_type": shadow["outer_type"],
                    "shadowing_type": "name_collision",
                },
            )
            self._edges.append(shadows_edge)

    def _validate_fqn_uniqueness(self) -> list[dict]:
        """
        Validate that all FQNs are unique.

        Returns:
            List of FQN collisions (should be empty in well-formed IR)
        """
        fqn_map = {}
        collisions = []

        for node in self._nodes:
            fqn = node.fqn

            if fqn in fqn_map:
                # Collision detected
                existing = fqn_map[fqn]
                collisions.append(
                    {
                        "fqn": fqn,
                        "node1": existing.name,
                        "node1_kind": existing.kind.value,
                        "node2": node.name,
                        "node2_kind": node.kind.value,
                        "collision_type": "fqn_duplicate",
                    }
                )
            else:
                fqn_map[fqn] = node

        if collisions:
            logger.warning(f"FQN collisions detected: {len(collisions)}")
            for collision in collisions:
                logger.warning(f"  {collision['fqn']}: {collision['node1']} vs {collision['node2']}")

        return collisions

    def _create_unified_symbol(self, node, source: SourceFile) -> "UnifiedSymbol":
        """
        Convert IR Node to UnifiedSymbol (SCIP-compatible)

        Args:
            node: IR Node (Class, Method, Function, etc.)
            source: Source file

        Returns:
            UnifiedSymbol with full SCIP descriptor
        """
        from pathlib import Path

        from src.contexts.code_foundation.domain.models import UnifiedSymbol
        from src.contexts.code_foundation.infrastructure.version_detector import VersionDetector

        # Extract FQN
        fqn = node.attrs.get("fqn", node.name)

        # Create SCIP descriptor suffix
        descriptor = fqn
        if node.kind.value == "Function" or node.kind.value == "Method":
            descriptor += "()."
        elif node.kind.value == "Class":
            descriptor += "#"
        elif node.kind.value == "Interface":
            descriptor += "#"
        elif node.kind.value == "Enum":
            descriptor += "#"
        else:
            descriptor += "."

        # Extract package name
        package_name = self._package_name or "default"

        # Detect version
        try:
            project_root = str(Path(source.file_path).parent.absolute())
            detector = VersionDetector(project_root)
            version = detector.detect_version("java", package_name)
        except Exception:
            version = "unknown"

        return UnifiedSymbol(
            scheme="java",
            manager="maven",
            package=package_name,
            version=version,
            root="/",
            file_path=source.file_path,
            descriptor=descriptor,
            language_fqn=fqn,
            language_kind=node.kind.value,
        )

    def generate(
        self,
        source: SourceFile,
        snapshot_id: str,
        old_content: str | None = None,
        diff_text: str | None = None,
        ast: AstTree | None = None,
    ) -> IRDocument:
        """
        Generate IR from Java source.

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
        self._import_map = {}  # Track imports for collision detection
        self._symbol_scopes = {}  # Track symbols for shadowing detection
        self._shadowings = []  # Track detected shadowings
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

        # Initialize scope with package name only
        # (Classes will add their own names)
        if self._package_name:
            initial_scope = self._package_name
        else:
            # Fallback: use file path without filename
            parts = source.file_path.replace(".java", "").split("/")
            initial_scope = ".".join(parts[:-1]) if len(parts) > 1 else ""

        self._scope = ScopeStack(initial_scope)

        # Generate nodes
        gen_start = time.perf_counter()
        self._process_root()

        # Detect import collisions
        import_collisions = self._detect_import_collisions()

        # Create shadowing edges
        self._create_shadowing_edges()

        # Validate FQN uniqueness
        fqn_collisions = self._validate_fqn_uniqueness()

        self._timings["node_generation_ms"] = (time.perf_counter() - gen_start) * 1000
        self._timings["total_ms"] = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"Java IR generated: {len(self._nodes)} nodes, "
            f"{len(self._edges)} edges in {self._timings['total_ms']:.1f}ms"
        )

        # Generate UnifiedSymbols for cross-language resolution
        unified_symbols = []
        for node in self._nodes:
            # Only create UnifiedSymbols for definitions
            if node.kind.value in ["Class", "Method", "Function", "Interface", "Enum"]:
                try:
                    unified = self._create_unified_symbol(node, source)
                    unified_symbols.append(unified)
                except Exception as e:
                    # Skip if conversion fails
                    logger.debug(f"Failed to create UnifiedSymbol for {node.name}: {e}")
                    pass

        return IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="3.0",  # Java SOTA features (Method Ref, Generics, Exception Flow, etc.)
            nodes=self._nodes,
            edges=self._edges,
            unified_symbols=unified_symbols,
            meta={
                "file_path": source.file_path,
                "language": "java",
                "package": self._package_name,
                "import_count": len(self._import_map),
                "import_collisions": len(import_collisions) if import_collisions else 0,
                "shadowing_count": len(self._shadowings) if hasattr(self, "_shadowings") else 0,
                "fqn_collisions": len(fqn_collisions) if fqn_collisions else 0,
                "timings": self._timings,
            },
        )

    def _extract_package(self) -> None:
        """Extract package declaration."""
        root = self._ast.root
        for child in root.children:
            if child.type == "package_declaration":
                # package com.example.app;
                scoped_identifier = self.find_child_by_type(child, "scoped_identifier")
                if scoped_identifier:
                    self._package_name = self.get_node_text(scoped_identifier, self._source_bytes)
                else:
                    # Simple identifier
                    identifier = self.find_child_by_type(child, "identifier")
                    if identifier:
                        self._package_name = self.get_node_text(identifier, self._source_bytes)
                break

    def _get_module_fqn(self, file_path: str) -> str:
        """
        Get module FQN from package and file path.

        For top-level class FQN generation, returns package.ClassName.
        For scope initialization, just returns package name.
        """
        # Use package name if available
        if self._package_name:
            class_name = file_path.split("/")[-1].replace(".java", "")
            return f"{self._package_name}.{class_name}"

        # Fallback: convert file path
        # src/main/java/com/example/App.java -> com.example.App
        path = file_path.replace(".java", "").replace("/", ".")
        return path

    def _process_root(self) -> None:
        """Process root node and traverse."""
        root = self._ast.root

        # Create file node
        file_node = self._create_file_node()
        self._nodes.append(file_node)

        # Process imports
        for child in root.children:
            if child.type == "import_declaration":
                self._process_import(child, file_node.id)

        # Process class/interface/enum declarations
        for child in root.children:
            if child.type == "class_declaration":
                self._process_class(child, file_node.id)
            elif child.type == "interface_declaration":
                self._process_interface(child, file_node.id)
            elif child.type == "enum_declaration":
                self._process_enum(child, file_node.id)

    def _create_file_node(self) -> Node:
        """Create file node."""
        # Use file_path as FQN to avoid collision with class names
        fqn = self._source.file_path
        return Node(
            id=generate_logical_id(
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
            language="java",
            module_path=self._package_name or None,
        )

    def _process_import(self, node: "TSNode", parent_id: str) -> None:
        """Process import declaration."""
        # import java.util.List;
        # import static java.lang.Math.*;
        scoped_identifier = None
        asterisk = None

        for child in node.children:
            if child.type in ["scoped_identifier", "identifier"]:
                scoped_identifier = child
            elif child.type == "asterisk":
                asterisk = child

        if not scoped_identifier:
            return

        import_path = self.get_node_text(scoped_identifier, self._source_bytes)
        is_wildcard = asterisk is not None

        # Create import node
        import_node = Node(
            id=generate_logical_id(
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
            language="java",
            parent_id=parent_id,
            attrs={"wildcard": is_wildcard},
        )
        self._nodes.append(import_node)

        # Create IMPORTS edge
        import_edge = Edge(
            id=generate_edge_id(EdgeKind.IMPORTS, parent_id, import_node.id),
            kind=EdgeKind.IMPORTS,
            source_id=parent_id,
            target_id=import_node.id,
            span=self._node_to_span(node),
        )
        self._edges.append(import_edge)

        # Track import for collision detection
        self._import_map[import_path] = {
            "path": import_path,
            "wildcard": is_wildcard,
            "simple_name": import_path.split(".")[-1] if not is_wildcard else "*",
        }

    def _process_class(self, node: "TSNode", parent_id: str) -> None:
        """Process class declaration."""
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        class_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Calculate complexity
        body = self.find_child_by_type(node, "class_body")
        complexity = self.calculate_cyclomatic_complexity(body, JAVA_BRANCH_TYPES) if body else 1

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        # Extract generic type parameters (e.g., <T extends Number>)
        type_params_info = []
        type_params_node = self.find_child_by_type(node, "type_parameters")
        if type_params_node:
            for child in type_params_node.children:
                if child.type == "type_parameter":
                    param_text = self.get_node_text(child, self._source_bytes)
                    type_params_info.append(param_text)

        attrs = {**modifiers}
        if type_params_info:
            attrs["type_parameters"] = type_params_info

        class_node = Node(
            id=generate_logical_id(
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
            language="java",
            parent_id=parent_id,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, JAVA_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, JAVA_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, JAVA_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(class_node)

        # Process type parameters as separate nodes
        self._process_type_parameters(node, class_node.id)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, class_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=class_node.id,
        )
        self._edges.append(contains_edge)

        # Process inheritance
        self._process_inheritance(node, class_node.id)

        # Enter class scope
        self._scope.push("class", name, class_fqn)

        # Process class body
        if body:
            for child in body.children:
                if child.type == "method_declaration":
                    self._process_method(child, class_node.id)
                elif child.type == "constructor_declaration":
                    self._process_constructor(child, class_node.id)
                elif child.type == "field_declaration":
                    self._process_field(child, class_node.id)
                elif child.type == "class_declaration":
                    self._process_class(child, class_node.id)  # Nested class
                elif child.type == "interface_declaration":
                    self._process_interface(child, class_node.id)

        self._scope.pop()

    def _process_interface(self, node: "TSNode", parent_id: str) -> None:
        """Process interface declaration."""
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        interface_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Extract modifiers
        modifiers = self._extract_modifiers(node)

        interface_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.INTERFACE,
                file_path=self._source.file_path,
                fqn=interface_fqn,
            ),
            kind=NodeKind.INTERFACE,
            name=name,
            fqn=interface_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            attrs=modifiers,
        )
        self._nodes.append(interface_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, interface_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=interface_node.id,
        )
        self._edges.append(contains_edge)

        # Process extends
        self._process_interface_extends(node, interface_node.id)

        # Enter interface scope
        self._scope.push("interface", name, interface_fqn)

        # Process interface body
        body = self.find_child_by_type(node, "interface_body")
        if body:
            for child in body.children:
                if child.type == "method_declaration":
                    self._process_method(child, interface_node.id)
                elif child.type == "constant_declaration":
                    self._process_field(child, interface_node.id)

        self._scope.pop()

    def _process_enum(self, node: "TSNode", parent_id: str) -> None:
        """Process enum declaration."""
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)
        enum_fqn = f"{self._scope.current_fqn()}.{name}" if self._scope.current_fqn() else name

        # Use CLASS kind for enum (Java enums are special classes)
        enum_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.CLASS,
                file_path=self._source.file_path,
                fqn=enum_fqn,
            ),
            kind=NodeKind.CLASS,
            name=name,
            fqn=enum_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            attrs={"is_enum": True},
        )
        self._nodes.append(enum_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, enum_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=enum_node.id,
        )
        self._edges.append(contains_edge)

    def _extract_parameter_signature(self, params_node: "TSNode") -> str:
        """
        Extract parameter signature from formal_parameters node.

        Returns signature like "(int,String)" or "(String...)" for varargs.
        This ensures unique FQNs for overloaded methods.
        """
        if not params_node:
            return "()"

        param_types = []
        for child in params_node.children:
            if child.type == "formal_parameter":
                # Check for varargs (spread_parameter)
                is_varargs = False
                for grandchild in child.children:
                    if grandchild.type == "spread_parameter":
                        is_varargs = True
                        break

                # Get type from formal_parameter
                type_node = (
                    self.find_child_by_type(child, "type_identifier")
                    or self.find_child_by_type(child, "integral_type")
                    or self.find_child_by_type(child, "floating_point_type")
                    or self.find_child_by_type(child, "boolean_type")
                    or self.find_child_by_type(child, "generic_type")
                    or self.find_child_by_type(child, "array_type")
                )

                if type_node:
                    type_name = self.get_node_text(type_node, self._source_bytes)
                    # Add varargs marker
                    if is_varargs:
                        type_name = f"{type_name}..."
                    param_types.append(type_name)
            elif child.type == "spread_parameter":
                # Direct varargs parameter
                type_node = (
                    self.find_child_by_type(child, "type_identifier")
                    or self.find_child_by_type(child, "integral_type")
                    or self.find_child_by_type(child, "generic_type")
                )
                if type_node:
                    type_name = self.get_node_text(type_node, self._source_bytes)
                    param_types.append(f"{type_name}...")

        return f"({','.join(param_types)})" if param_types else "()"

    def _extract_modifiers(self, node: "TSNode") -> dict[str, any]:
        """
        Extract modifiers from a declaration node.

        Returns dict with:
        - is_static: bool
        - is_final: bool
        - is_abstract: bool
        - visibility: str (public/private/protected/package)
        """
        modifiers = {
            "is_static": False,
            "is_final": False,
            "is_abstract": False,
            "visibility": "package",  # default
        }

        # Find modifiers node
        for child in node.children:
            if child.type == "modifiers":
                for modifier in child.children:
                    modifier_text = self.get_node_text(modifier, self._source_bytes)

                    if modifier_text == "static":
                        modifiers["is_static"] = True
                    elif modifier_text == "final":
                        modifiers["is_final"] = True
                    elif modifier_text == "abstract":
                        modifiers["is_abstract"] = True
                    elif modifier_text == "public":
                        modifiers["visibility"] = "public"
                    elif modifier_text == "private":
                        modifiers["visibility"] = "private"
                    elif modifier_text == "protected":
                        modifiers["visibility"] = "protected"

        return modifiers

    def _extract_annotations(self, node: "TSNode") -> list[str]:
        """Extract annotations from a declaration node."""
        annotations = []

        # Annotations can be direct children or inside modifiers
        for child in node.children:
            if child.type in ["marker_annotation", "annotation"]:
                # Get annotation name (after @)
                name_node = self.find_child_by_type(child, "identifier") or self.find_child_by_type(
                    child, "scoped_identifier"
                )
                if name_node:
                    ann_name = self.get_node_text(name_node, self._source_bytes)
                    annotations.append(f"@{ann_name}")
                elif child.type == "marker_annotation":
                    # For simple @Override, the text is the whole thing
                    ann_text = self.get_node_text(child, self._source_bytes)
                    annotations.append(ann_text)
            elif child.type == "modifiers":
                # Check inside modifiers too
                for modifier_child in child.children:
                    if modifier_child.type in ["marker_annotation", "annotation"]:
                        ann_text = self.get_node_text(modifier_child, self._source_bytes)
                        annotations.append(ann_text)

        return annotations

    def _process_method(self, node: "TSNode", parent_id: str) -> None:
        """Process method declaration."""
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)

        # Extract parameter types for method signature (for overloading)
        params_node = self.find_child_by_type(node, "formal_parameters")
        param_signature = self._extract_parameter_signature(params_node) if params_node else "()"

        # Include parameter signature in FQN for uniqueness
        method_fqn = f"{self._scope.current_fqn()}.{name}{param_signature}"

        # Get method body
        body = self.find_child_by_type(node, "block")

        # Calculate complexity
        complexity = self.calculate_cyclomatic_complexity(body, JAVA_BRANCH_TYPES) if body else 1

        # Extract modifiers and annotations
        modifiers = self._extract_modifiers(node)
        annotations = self._extract_annotations(node)

        # Extract generic type parameters (e.g., <T extends Comparable<T>>)
        type_params_info = []
        type_params_node = self.find_child_by_type(node, "type_parameters")
        if type_params_node:
            for child in type_params_node.children:
                if child.type == "type_parameter":
                    param_text = self.get_node_text(child, self._source_bytes)
                    type_params_info.append(param_text)

        # Extract detailed type information (including wildcards)
        type_info = self._extract_method_type_info(node)

        # Extract throws clause
        throws_list = self._extract_throws_clause(node)

        # Merge into attrs
        attrs = {**modifiers}
        if annotations:
            attrs["annotations"] = annotations
        if type_params_info:
            attrs["type_parameters"] = type_params_info
        if type_info:
            attrs["type_info"] = type_info
        if throws_list:
            attrs["throws"] = throws_list

        method_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.METHOD,
                file_path=self._source.file_path,
                fqn=method_fqn,
            ),
            kind=NodeKind.METHOD,
            name=name,
            fqn=method_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            body_span=self._node_to_span(body) if body else None,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, JAVA_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, JAVA_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, JAVA_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(method_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, method_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=method_node.id,
        )
        self._edges.append(contains_edge)

        # Process type parameters as separate nodes
        self._process_type_parameters(node, method_node.id)

        # Process exception throws (create THROWS edges)
        if throws_list:
            self._process_exception_throws(node, method_node.id)

        # Process method calls and exception handling in body
        if body:
            # Analyze exception propagation
            exception_flow = self._analyze_exception_propagation(method_node, body)
            if exception_flow and any(exception_flow.values()):
                attrs["exception_flow"] = exception_flow
                # Update node attrs
                method_node.attrs = attrs

            # Process try-catch blocks first
            self._process_try_catch_blocks(body, method_node.id)
            # Process method calls
            self._process_method_calls(body, method_node.id)

    def _process_constructor(self, node: "TSNode", parent_id: str) -> None:
        """Process constructor declaration."""
        name_node = self.find_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self.get_node_text(name_node, self._source_bytes)

        # Extract parameter signature for constructor overloading
        params_node = self.find_child_by_type(node, "formal_parameters")
        param_signature = self._extract_parameter_signature(params_node) if params_node else "()"

        # Constructor FQN includes parameter signature
        constructor_fqn = f"{self._scope.current_fqn()}.{name}{param_signature}"

        # Get constructor body
        body = self.find_child_by_type(node, "constructor_body")

        # Calculate complexity
        complexity = self.calculate_cyclomatic_complexity(body, JAVA_BRANCH_TYPES) if body else 1

        # Extract modifiers
        modifiers = self._extract_modifiers(node)
        attrs = {**modifiers, "is_constructor": True}

        constructor_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.METHOD,  # Constructors are treated as methods
                file_path=self._source.file_path,
                fqn=constructor_fqn,
            ),
            kind=NodeKind.METHOD,
            name=name,
            fqn=constructor_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            body_span=self._node_to_span(body) if body else None,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, JAVA_LOOP_TYPES) if body else False,
                has_try=self.has_try(body, JAVA_TRY_TYPES) if body else False,
                branch_count=self.count_branches(body, JAVA_BRANCH_TYPES) if body else 0,
            ),
            attrs=attrs,
        )
        self._nodes.append(constructor_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, constructor_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=constructor_node.id,
        )
        self._edges.append(contains_edge)

        # Process method calls in constructor body
        if body:
            self._process_method_calls(body, constructor_node.id)

    def _process_field(self, node: "TSNode", parent_id: str) -> None:
        """Process field declaration."""
        # field_declaration can have multiple variable declarators
        declarators = self.find_children_by_type(node, "variable_declarator")

        # Extract field type (shared across all declarators)
        field_type_node = None
        for child in node.children:
            if child.type in [
                "type_identifier",
                "generic_type",
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "array_type",
            ]:
                field_type_node = child
                break

        for declarator in declarators:
            name_node = self.find_child_by_type(declarator, "identifier")
            if not name_node:
                continue

            name = self.get_node_text(name_node, self._source_bytes)
            field_fqn = f"{self._scope.current_fqn()}.{name}"

            # Extract modifiers
            modifiers = self._extract_modifiers(node)

            # Extract type information (including generics)
            attrs = {**modifiers}
            if field_type_node:
                type_info = self._extract_generic_type_info(field_type_node)
                if type_info:
                    attrs["type_info"] = type_info

            # Check for instantiation (e.g., = new ArrayList<>())
            initializer = self.find_child_by_type(declarator, "object_creation_expression")
            if initializer:
                attrs["has_initializer"] = True
                # Extract instantiated type
                inst_type_node = self.find_child_by_type(initializer, "type_identifier") or self.find_child_by_type(
                    initializer, "generic_type"
                )
                if inst_type_node:
                    inst_type = self._extract_generic_type_info(inst_type_node)
                    if inst_type:
                        attrs["instantiated_type"] = inst_type

            field_node = Node(
                id=generate_logical_id(
                    repo_id=self.repo_id,
                    kind=NodeKind.FIELD,
                    file_path=self._source.file_path,
                    fqn=field_fqn,
                ),
                kind=NodeKind.FIELD,
                name=name,
                fqn=field_fqn,
                span=self._node_to_span(declarator),
                file_path=self._source.file_path,
                language="java",
                parent_id=parent_id,
                attrs=attrs,
            )
            self._nodes.append(field_node)

            # CONTAINS edge
            contains_edge = Edge(
                id=generate_edge_id(EdgeKind.CONTAINS, parent_id, field_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=field_node.id,
            )
            self._edges.append(contains_edge)

    def _process_inheritance(self, node: "TSNode", class_id: str) -> None:
        """Process class inheritance (extends/implements)."""
        # extends clause
        superclass = self.find_child_by_type(node, "superclass")
        if superclass:
            type_node = self.find_child_by_type(superclass, "type_identifier")
            if type_node:
                parent_class = self.get_node_text(type_node, self._source_bytes)
                # Create unresolved target ID in proper format
                # Will be resolved in post-processing phase
                target_fqn = f"{self._package_name}.{parent_class}" if self._package_name else parent_class
                target_id = f"class:{self.repo_id}:{self._source.file_path}:{parent_class}"

                # Create INHERITS edge
                edge = Edge(
                    id=generate_edge_id(EdgeKind.INHERITS, class_id, target_id),
                    kind=EdgeKind.INHERITS,
                    source_id=class_id,
                    target_id=target_id,
                    attrs={"unresolved": True, "target_name": parent_class},
                )
                self._edges.append(edge)

        # implements clause
        super_interfaces = self.find_child_by_type(node, "super_interfaces")
        if super_interfaces:
            type_list = self.find_child_by_type(super_interfaces, "type_list")
            if type_list:
                for child in type_list.children:
                    if child.type == "type_identifier":
                        interface_name = self.get_node_text(child, self._source_bytes)
                        # Create unresolved target ID in proper format
                        target_id = f"interface:{self.repo_id}:{self._source.file_path}:{interface_name}"

                        # Create IMPLEMENTS edge
                        edge = Edge(
                            id=generate_edge_id(EdgeKind.IMPLEMENTS, class_id, target_id),
                            kind=EdgeKind.IMPLEMENTS,
                            source_id=class_id,
                            target_id=target_id,
                            attrs={"unresolved": True, "target_name": interface_name},
                        )
                        self._edges.append(edge)

    def _process_interface_extends(self, node: "TSNode", interface_id: str) -> None:
        """Process interface extends."""
        extends_interfaces = self.find_child_by_type(node, "extends_interfaces")
        if extends_interfaces:
            type_list = self.find_child_by_type(extends_interfaces, "type_list")
            if type_list:
                for child in type_list.children:
                    if child.type == "type_identifier":
                        parent_interface = self.get_node_text(child, self._source_bytes)
                        # Create unresolved target ID in proper format
                        target_id = f"interface:{self.repo_id}:{self._source.file_path}:{parent_interface}"

                        # Create INHERITS edge
                        edge = Edge(
                            id=generate_edge_id(EdgeKind.INHERITS, interface_id, target_id),
                            kind=EdgeKind.INHERITS,
                            source_id=interface_id,
                            target_id=target_id,
                            attrs={"unresolved": True, "target_name": parent_interface},
                        )
                        self._edges.append(edge)

    def _process_method_calls(self, body: "TSNode", caller_id: str) -> None:
        """Process method calls, lambdas, method references, and anonymous classes in method body."""

        def traverse(node: "TSNode") -> None:
            # Process lambda expressions
            if node.type == "lambda_expression":
                self._process_lambda(node, caller_id)
                return  # Don't traverse children (lambda handles its own body)

            # Process method references (::)
            elif node.type == "method_reference":
                self._process_method_reference(node, caller_id)
                return  # Don't traverse children (leaf node)

            # Process anonymous classes
            elif node.type == "object_creation_expression":
                # Check if it has a class_body (anonymous class)
                class_body = self.find_child_by_type(node, "class_body")
                if class_body:
                    self._process_anonymous_class(node, caller_id)
                    return  # Don't traverse children (anon class handles its own body)

            # Process method calls
            elif node.type == "method_invocation":
                # Extract method name
                name_node = self.find_child_by_type(node, "identifier")
                if name_node:
                    callee_name = self.get_node_text(name_node, self._source_bytes)

                    # Create unresolved target ID in proper format
                    target_id = f"method:{self.repo_id}:{self._source.file_path}:{callee_name}"

                    # Create CALLS edge (unresolved target)
                    edge = Edge(
                        id=generate_edge_id(EdgeKind.CALLS, caller_id, target_id),
                        kind=EdgeKind.CALLS,
                        source_id=caller_id,
                        target_id=target_id,
                        span=self._node_to_span(node),
                        attrs={"unresolved": True, "target_name": callee_name},
                    )
                    self._edges.append(edge)

            # Traverse children
            for child in node.children:
                traverse(child)

        traverse(body)

    def _process_lambda(self, node: "TSNode", parent_id: str) -> None:
        """Process lambda expression."""
        # Lambda structure: (params) -> body
        # Get lambda parameters
        params_node = (
            self.find_child_by_type(node, "inferred_parameters")
            or self.find_child_by_type(node, "formal_parameters")
            or self.find_child_by_type(node, "identifier")
        )  # single param

        # Extract parameter signature
        if params_node:
            if params_node.type == "identifier":
                param_sig = f"({self.get_node_text(params_node, self._source_bytes)})"
            else:
                param_sig = (
                    self._extract_parameter_signature(params_node) if params_node.type == "formal_parameters" else "()"
                )
        else:
            param_sig = "()"

        # Generate unique FQN for lambda
        # Use location (line:col) in source as part of FQN for uniqueness
        lambda_line = node.start_point[0] + 1
        lambda_col = node.start_point[1]
        lambda_fqn = f"{self._scope.current_fqn()}.lambda${lambda_line}:{lambda_col}{param_sig}"

        # Get lambda body
        body = (
            self.find_child_by_type(node, "block")
            or self.find_child_by_type(node, "expression_statement")
            or node.children[-1]
        )  # Last child is usually the body

        # Calculate complexity
        complexity = 1
        if body and body.type == "block":
            complexity = self.calculate_cyclomatic_complexity(body, JAVA_BRANCH_TYPES)

        lambda_node = Node(
            id=generate_logical_id(
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
            language="java",
            parent_id=parent_id,
            body_span=self._node_to_span(body) if body else None,
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(body, JAVA_LOOP_TYPES) if body and body.type == "block" else False,
                has_try=self.has_try(body, JAVA_TRY_TYPES) if body and body.type == "block" else False,
                branch_count=self.count_branches(body, JAVA_BRANCH_TYPES) if body and body.type == "block" else 0,
            ),
            attrs={"is_lambda": True, "param_signature": param_sig},
        )
        self._nodes.append(lambda_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, lambda_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=lambda_node.id,
        )
        self._edges.append(contains_edge)

        # Analyze variable captures (closure)
        if body:
            captures = self._analyze_lambda_captures(body, lambda_node.id, self._scope.current_fqn())
            if captures:
                lambda_node.attrs["captures"] = [c["name"] for c in captures]
                lambda_node.attrs["capture_count"] = len(captures)

        # Process calls in lambda body
        if body and body.type == "block":
            self._process_method_calls(body, lambda_node.id)

    def _process_anonymous_class(self, node: "TSNode", parent_id: str) -> None:
        """Process anonymous class (object_creation_expression with class_body)."""
        # Get the type being instantiated
        type_node = self.find_child_by_type(node, "type_identifier") or self.find_child_by_type(node, "generic_type")

        if not type_node:
            return

        type_name = self.get_node_text(type_node, self._source_bytes)

        # Get class body
        class_body = self.find_child_by_type(node, "class_body")
        if not class_body:
            return  # Not an anonymous class, just regular instantiation

        # Generate unique FQN for anonymous class
        anon_line = node.start_point[0] + 1
        anon_col = node.start_point[1]
        anon_fqn = f"{self._scope.current_fqn()}.anon${type_name}${anon_line}:{anon_col}"

        # Calculate complexity
        complexity = self.calculate_cyclomatic_complexity(class_body, JAVA_BRANCH_TYPES)

        anon_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.LAMBDA,  # Use LAMBDA kind for anonymous classes too
                file_path=self._source.file_path,
                fqn=anon_fqn,
            ),
            kind=NodeKind.LAMBDA,
            name=f"anon${type_name}${anon_line}",
            fqn=anon_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            body_span=self._node_to_span(class_body),
            control_flow_summary=ControlFlowSummary(
                cyclomatic_complexity=complexity,
                has_loop=self.has_loop(class_body, JAVA_LOOP_TYPES),
                has_try=self.has_try(class_body, JAVA_TRY_TYPES),
                branch_count=self.count_branches(class_body, JAVA_BRANCH_TYPES),
            ),
            attrs={"is_anonymous_class": True, "type_name": type_name},
        )
        self._nodes.append(anon_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, anon_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=anon_node.id,
        )
        self._edges.append(contains_edge)

        # Analyze outer field accesses
        accesses = self._analyze_anonymous_class_accesses(class_body, anon_node.id)
        if accesses:
            anon_node.attrs["accesses"] = [a["name"] for a in accesses]
            anon_node.attrs["access_count"] = len(accesses)

        # Enter anonymous class scope
        self._scope.push("class", f"anon${type_name}${anon_line}", anon_fqn)

        # Process methods in anonymous class
        for child in class_body.children:
            if child.type == "method_declaration":
                self._process_method(child, anon_node.id)
            elif child.type == "field_declaration":
                self._process_field(child, anon_node.id)

        self._scope.pop()

    def _process_method_reference(self, node: "TSNode", parent_id: str) -> None:
        """
        Process method reference (::).

        4 types:
        - STATIC: Integer::parseInt
        - INSTANCE_BOUND: str::toUpperCase
        - INSTANCE_UNBOUND: String::toLowerCase
        - CONSTRUCTOR: ArrayList::new
        """
        # Method reference structure: qualifier :: method_name
        # Children: [qualifier, "::", method_name or "new"]

        if len(node.children) < 3:
            return

        # Get qualifier (left side of ::)
        qualifier_node = node.children[0]
        qualifier_text = self.get_node_text(qualifier_node, self._source_bytes)

        # Get method name (right side of ::)
        method_name_node = node.children[2] if len(node.children) > 2 else None
        if not method_name_node:
            return

        method_name = self.get_node_text(method_name_node, self._source_bytes)

        # Determine reference type
        ref_type = self._determine_method_ref_type(qualifier_node, method_name)

        # Generate unique FQN for method reference
        ref_line = node.start_point[0] + 1
        ref_col = node.start_point[1]
        ref_fqn = f"{self._scope.current_fqn()}.ref${ref_line}:{ref_col}#{qualifier_text}::{method_name}"

        # Create target ID (unresolved for now, will be resolved by LSP)
        target_name = f"{qualifier_text}.{method_name}" if method_name != "new" else f"{qualifier_text}.<init>"
        target_id = f"method:{self.repo_id}:{self._source.file_path}:{target_name}"

        method_ref_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.METHOD_REFERENCE,
                file_path=self._source.file_path,
                fqn=ref_fqn,
            ),
            kind=NodeKind.METHOD_REFERENCE,
            name=f"ref${ref_line}",
            fqn=ref_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            attrs={
                "is_method_reference": True,
                "ref_type": ref_type,
                "qualifier": qualifier_text,
                "method_name": method_name,
                "target": target_name,
            },
        )
        self._nodes.append(method_ref_node)

        # CONTAINS edge (method reference is contained in parent)
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, method_ref_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=method_ref_node.id,
        )
        self._edges.append(contains_edge)

        # REFERENCES edge (method reference -> target method)
        references_edge = Edge(
            id=generate_edge_id(EdgeKind.REFERENCES, method_ref_node.id, target_id),
            kind=EdgeKind.REFERENCES,
            source_id=method_ref_node.id,
            target_id=target_id,
            span=self._node_to_span(node),
            attrs={
                "unresolved": True,
                "target_name": target_name,
                "ref_type": ref_type,
            },
        )
        self._edges.append(references_edge)

        # Optional: Store for later JDT.LS refinement
        if self._jdtls:
            method_ref_node.attrs["jdtls_refinement_pending"] = True

    async def _refine_method_ref_with_jdtls(self, method_ref_node: Node) -> str:
        """
        Refine ref_type using JDT.LS (optional enhancement).

        Only called if JDT.LS adapter is available.

        Returns:
            Refined ref_type (STATIC, INSTANCE_BOUND, INSTANCE_UNBOUND, CONSTRUCTOR)
        """
        if not self._jdtls:
            return method_ref_node.attrs.get("ref_type", "STATIC")

        try:
            # Get position of method reference
            from pathlib import Path

            file_path = Path(self._source.file_path)
            line = method_ref_node.span.start_line - 1  # 0-based
            col = method_ref_node.span.start_col

            # Try to get definition
            definition = await self._jdtls.definition(file_path, line, col)

            if not definition:
                # Fallback to heuristic
                return method_ref_node.attrs.get("ref_type", "STATIC")

            # Get hover info to check modifiers
            hover = await self._jdtls.hover(file_path, line, col)

            if hover and hover.type_string:
                type_str = hover.type_string.lower()

                # Check for static keyword
                if "static" in type_str or "static method" in hover.documentation.lower():
                    return "STATIC"

                # Check if qualifier is a variable (INSTANCE_BOUND)
                qualifier = method_ref_node.attrs.get("qualifier", "")
                if qualifier and qualifier[0].islower():
                    return "INSTANCE_BOUND"

                # Otherwise, it's INSTANCE_UNBOUND (Type::instanceMethod)
                return "INSTANCE_UNBOUND"

        except Exception as e:
            # Fallback to heuristic on any error
            logger.debug(f"JDT.LS refinement failed for {method_ref_node.name}: {e}")

        return method_ref_node.attrs.get("ref_type", "STATIC")

    def _determine_method_ref_type(self, qualifier_node: "TSNode", method_name: str) -> str:
        """
        Determine the type of method reference.

        Uses multiple heuristics:
        1. Method name "new" → CONSTRUCTOR
        2. Qualifier naming convention (Java standard)
        3. Scope variable tracking

        Returns:
            - "CONSTRUCTOR" if method_name is "new"
            - "STATIC" if qualifier is likely a type
            - "INSTANCE_BOUND" if qualifier is likely a variable
            - "INSTANCE_UNBOUND" if qualifier is a type for instance method
        """
        if method_name == "new":
            return "CONSTRUCTOR"

        # Get qualifier text
        qualifier_text = self.get_node_text(qualifier_node, self._source_bytes)

        # Heuristic 1: Java naming convention
        # Types start with uppercase, variables start with lowercase
        if qualifier_text and len(qualifier_text) > 0:
            first_char = qualifier_text[0]

            # Special cases: this, super
            if qualifier_text in ["this", "super"]:
                return "INSTANCE_BOUND"

            # Field access: obj.field, this.field
            if "." in qualifier_text:
                # Check last part (e.g., "System.out" → "out")
                last_part = qualifier_text.split(".")[-1]
                if last_part[0].islower():
                    return "INSTANCE_BOUND"
                # Could be Type.staticField → treat as bound
                return "INSTANCE_BOUND"

            # Simple identifier
            if first_char.isupper():
                # Type name (Integer, String, MyClass)
                # Could be STATIC or INSTANCE_UNBOUND
                # Default to STATIC (common case)
                # LSP will refine this later
                return "STATIC"
            else:
                # Variable name (str, list, obj)
                return "INSTANCE_BOUND"

        # Default to STATIC
        return "STATIC"

    def _process_type_parameters(self, node: "TSNode", parent_id: str) -> list[Node]:
        """
        Process generic type parameters (e.g., <T extends Number>).

        Returns list of TYPE_PARAMETER nodes.
        """
        type_params_node = self.find_child_by_type(node, "type_parameters")
        if not type_params_node:
            return []

        type_param_nodes = []

        for child in type_params_node.children:
            if child.type != "type_parameter":
                continue

            # Extract type parameter name (e.g., "T")
            type_name_node = self.find_child_by_type(child, "type_identifier")
            if not type_name_node:
                continue

            type_name = self.get_node_text(type_name_node, self._source_bytes)

            # Extract bounds (e.g., "extends Number & Serializable")
            bounds = self._extract_type_bounds(child)

            # Create FQN for type parameter
            type_param_fqn = f"{self._scope.current_fqn()}.<{type_name}>"

            type_param_node = Node(
                id=generate_logical_id(
                    repo_id=self.repo_id,
                    kind=NodeKind.TYPE_PARAMETER,
                    file_path=self._source.file_path,
                    fqn=type_param_fqn,
                ),
                kind=NodeKind.TYPE_PARAMETER,
                name=type_name,
                fqn=type_param_fqn,
                span=self._node_to_span(child),
                file_path=self._source.file_path,
                language="java",
                parent_id=parent_id,
                attrs={
                    "is_type_parameter": True,
                    "bounds": bounds,
                    "upper_bounds": [b for b in bounds if b.get("kind") == "extends"],
                    "lower_bounds": [b for b in bounds if b.get("kind") == "super"],
                },
            )
            type_param_nodes.append(type_param_node)
            self._nodes.append(type_param_node)

            # CONTAINS edge
            contains_edge = Edge(
                id=generate_edge_id(EdgeKind.CONTAINS, parent_id, type_param_node.id),
                kind=EdgeKind.CONTAINS,
                source_id=parent_id,
                target_id=type_param_node.id,
            )
            self._edges.append(contains_edge)

        return type_param_nodes

    def _extract_type_bounds(self, type_param_node: "TSNode") -> list[dict]:
        """
        Extract type bounds from type parameter.

        Example:
        - <T extends Number> → [{"kind": "extends", "type": "Number"}]
        - <T extends A & B> → [{"kind": "extends", "type": "A"}, {"kind": "extends", "type": "B"}]
        """
        bounds = []

        # Find type_bound node (e.g., "extends Number")
        type_bound = self.find_child_by_type(type_param_node, "type_bound")
        if not type_bound:
            return bounds

        # Type bound structure: "extends" type1 "&" type2 ...
        current_bound_kind = None

        for child in type_bound.children:
            if child.type == "extends":
                current_bound_kind = "extends"
            elif child.type == "super":
                current_bound_kind = "super"
            elif child.type in ["type_identifier", "generic_type", "scoped_type_identifier"]:
                if current_bound_kind:
                    bound_type = self.get_node_text(child, self._source_bytes)
                    bounds.append(
                        {
                            "kind": current_bound_kind,
                            "type": bound_type,
                        }
                    )

        return bounds

    def _extract_wildcard_type(self, type_node: "TSNode") -> dict | None:
        """
        Extract wildcard type information (?, ? extends T, ? super T).

        Returns:
            {"wildcard": True, "bound": "extends|super|none", "type": "T"}
        """
        wildcard_node = self.find_child_by_type(type_node, "wildcard")
        if not wildcard_node:
            return None

        result = {"wildcard": True, "bound": "none", "type": None}

        # Check for bounds
        for child in wildcard_node.children:
            if child.type == "extends":
                result["bound"] = "extends"
            elif child.type == "super":
                result["bound"] = "super"
            elif child.type in ["type_identifier", "generic_type"]:
                result["type"] = self.get_node_text(child, self._source_bytes)

        return result

    def _extract_generic_type_info(self, type_node: "TSNode") -> dict:
        """
        Extract detailed generic type information including wildcards.

        Examples:
        - List<String> → {"base": "List", "args": [{"type": "String"}]}
        - List<? extends Number> → {"base": "List", "args": [{"wildcard": True, "bound": "extends", "type": "Number"}]}
        - Map<String, ? super Integer> → {"base": "Map", "args": [{"type": "String"}, {"wildcard": True, "bound": "super", "type": "Integer"}]}
        """
        if not type_node:
            return {}

        # Simple type (no generics)
        if type_node.type in ["type_identifier", "integral_type", "floating_point_type", "boolean_type"]:
            return {"type": self.get_node_text(type_node, self._source_bytes)}

        # Generic type
        if type_node.type == "generic_type":
            result = {}

            # Get base type
            base_type_node = self.find_child_by_type(type_node, "type_identifier") or self.find_child_by_type(
                type_node, "scoped_type_identifier"
            )
            if base_type_node:
                result["base"] = self.get_node_text(base_type_node, self._source_bytes)

            # Get type arguments
            type_args_node = self.find_child_by_type(type_node, "type_arguments")
            if type_args_node:
                args = []
                for child in type_args_node.children:
                    if child.type == "wildcard":
                        wildcard_info = self._extract_wildcard_type(type_args_node)
                        if wildcard_info:
                            args.append(wildcard_info)
                    elif child.type in ["type_identifier", "generic_type", "integral_type", "floating_point_type"]:
                        # Recursive for nested generics (e.g., List<List<String>>)
                        nested = self._extract_generic_type_info(child)
                        if nested:
                            args.append(nested)

                if args:
                    result["args"] = args

            return result

        # Array type
        if type_node.type == "array_type":
            element_type = self.find_child_by_type(type_node, "type_identifier") or self.find_child_by_type(
                type_node, "generic_type"
            )
            if element_type:
                base = self._extract_generic_type_info(element_type)
                return {**base, "array": True}

        return {"type": self.get_node_text(type_node, self._source_bytes)}

    def _extract_method_type_info(self, method_node: "TSNode") -> dict:
        """
        Extract detailed type information from method (return type + parameters).

        Returns:
            {
                "return_type": {...},
                "parameters": [{"name": "x", "type": {...}}, ...]
            }
        """
        result = {}

        # Extract return type
        return_type_node = None
        for child in method_node.children:
            if child.type in [
                "type_identifier",
                "generic_type",
                "integral_type",
                "floating_point_type",
                "boolean_type",
                "void_type",
                "array_type",
            ]:
                return_type_node = child
                break

        if return_type_node:
            if return_type_node.type == "void_type":
                result["return_type"] = {"type": "void"}
            else:
                result["return_type"] = self._extract_generic_type_info(return_type_node)

        # Extract parameters
        params_node = self.find_child_by_type(method_node, "formal_parameters")
        if params_node:
            params = []
            for child in params_node.children:
                if child.type == "formal_parameter":
                    param_info = {}

                    # Get parameter name
                    name_node = self.find_child_by_type(child, "identifier")
                    if name_node:
                        param_info["name"] = self.get_node_text(name_node, self._source_bytes)

                    # Get parameter type
                    type_node = None
                    for grandchild in child.children:
                        if grandchild.type in [
                            "type_identifier",
                            "generic_type",
                            "integral_type",
                            "floating_point_type",
                            "boolean_type",
                            "array_type",
                        ]:
                            type_node = grandchild
                            break

                    if type_node:
                        param_info["type"] = self._extract_generic_type_info(type_node)

                    # Check for varargs
                    for grandchild in child.children:
                        if (
                            grandchild.type == "spread_parameter"
                            or self.get_node_text(grandchild, self._source_bytes) == "..."
                        ):
                            param_info["varargs"] = True
                            break

                    if param_info:
                        params.append(param_info)

            if params:
                result["parameters"] = params

        return result

    def _extract_throws_clause(self, method_node: "TSNode") -> list[str]:
        """
        Extract exception types from throws clause.

        Example: throws IOException, SQLException
        Returns: ["IOException", "SQLException"]
        """
        throws_list = []

        # Find throws clause
        for child in method_node.children:
            if child.type == "throws":
                # throws clause contains type identifiers
                for grandchild in child.children:
                    if grandchild.type in ["type_identifier", "scoped_type_identifier"]:
                        exception_type = self.get_node_text(grandchild, self._source_bytes)
                        throws_list.append(exception_type)

        return throws_list

    def _process_exception_throws(self, method_node: "TSNode", method_id: str) -> None:
        """
        Process throws clause and create THROWS edges.

        Creates THROWS edges from method to exception types.
        """
        throws_list = self._extract_throws_clause(method_node)

        for exception_type in throws_list:
            # Create target ID for exception type
            target_id = f"class:{self.repo_id}:{self._source.file_path}:{exception_type}"

            # Create THROWS edge
            throws_edge = Edge(
                id=generate_edge_id(EdgeKind.THROWS, method_id, target_id),
                kind=EdgeKind.THROWS,
                source_id=method_id,
                target_id=target_id,
                attrs={
                    "exception_type": exception_type,
                    "declared": True,  # Declared in throws clause
                },
            )
            self._edges.append(throws_edge)

    def _process_try_catch_blocks(self, body: "TSNode", parent_id: str) -> None:
        """
        Process try-catch-finally blocks and create TRY_CATCH nodes.

        Analyzes:
        - Try block
        - Catch clauses (with exception types)
        - Finally block
        - Nested try-catch
        """

        def traverse(node: "TSNode") -> None:
            if node.type == "try_statement":
                self._process_try_statement(node, parent_id)
                return  # Don't traverse children (handled internally)

            for child in node.children:
                traverse(child)

        traverse(body)

    def _process_try_statement(self, node: "TSNode", parent_id: str) -> None:
        """
        Process a single try statement.

        Structure:
        - try { ... }
        - catch (ExceptionType e) { ... }
        - finally { ... }
        """
        # Create TRY_CATCH node
        try_line = node.start_point[0] + 1
        try_fqn = f"{self._scope.current_fqn()}.try${try_line}"

        # Extract caught exception types
        caught_exceptions = []
        catch_clauses = self.find_children_by_type(node, "catch_clause")
        for catch_clause in catch_clauses:
            # Get the full text of catch clause and parse with regex
            # Format: catch (ExceptionType varName) { ... }
            catch_text = self.get_node_text(catch_clause, self._source_bytes)

            # Extract exception type from "catch (Type var)" pattern
            import re

            match = re.search(r"catch\s*\(\s*([A-Z][A-Za-z0-9_.]*)", catch_text)
            if match:
                exception_type = match.group(1)
                caught_exceptions.append(exception_type)

        # Check for finally block
        has_finally = False
        for child in node.children:
            if child.type == "finally_clause":
                has_finally = True
                break

        try_catch_node = Node(
            id=generate_logical_id(
                repo_id=self.repo_id,
                kind=NodeKind.TRY_CATCH,
                file_path=self._source.file_path,
                fqn=try_fqn,
            ),
            kind=NodeKind.TRY_CATCH,
            name=f"try${try_line}",
            fqn=try_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="java",
            parent_id=parent_id,
            attrs={
                "is_try_catch": True,
                "caught_exceptions": caught_exceptions,
                "has_finally": has_finally,
                "catch_count": len(catch_clauses),
            },
        )
        self._nodes.append(try_catch_node)

        # CONTAINS edge
        contains_edge = Edge(
            id=generate_edge_id(EdgeKind.CONTAINS, parent_id, try_catch_node.id),
            kind=EdgeKind.CONTAINS,
            source_id=parent_id,
            target_id=try_catch_node.id,
        )
        self._edges.append(contains_edge)

        # Process nested try-catch blocks and method calls recursively
        try_block = self.find_child_by_type(node, "block")
        if try_block:
            # Process nested try-catch
            self._process_try_catch_blocks(try_block, try_catch_node.id)
            # Process method calls in try block
            self._process_method_calls(try_block, try_catch_node.id)

        # Process catch blocks
        for catch_clause in catch_clauses:
            catch_block = self.find_child_by_type(catch_clause, "block")
            if catch_block:
                self._process_try_catch_blocks(catch_block, try_catch_node.id)
                self._process_method_calls(catch_block, try_catch_node.id)

        # Process finally block
        finally_clause = None
        for child in node.children:
            if child.type == "finally_clause":
                finally_clause = child
                break

        if finally_clause:
            finally_block = self.find_child_by_type(finally_clause, "block")
            if finally_block:
                self._process_try_catch_blocks(finally_block, try_catch_node.id)
                self._process_method_calls(finally_block, try_catch_node.id)

    def _analyze_exception_propagation(self, method_node: Node, body: "TSNode") -> dict:
        """
        Analyze exception propagation in method body.

        Tracks:
        1. Thrown exceptions (explicit throws)
        2. Propagated exceptions (from method calls)
        3. Caught exceptions (in try-catch)
        4. Uncaught exceptions (may propagate)

        Returns:
            {
                "explicit_throws": [...],  # throw new Exception()
                "propagated_from_calls": [...],  # method calls that throw
                "caught": [...],  # caught in try-catch
                "may_propagate": [...]  # uncaught exceptions
            }
        """
        result = {"explicit_throws": [], "propagated_from_calls": [], "caught": [], "may_propagate": []}

        if not body:
            return result

        # Find all throw statements
        def find_throws(node: "TSNode", in_try_block: bool = False) -> None:
            if node.type == "throw_statement":
                # Extract exception type from throw statement
                # Format: throw new ExceptionType(...)
                throw_text = self.get_node_text(node, self._source_bytes)
                import re

                match = re.search(r"throw\s+new\s+([A-Z][A-Za-z0-9_.]*)", throw_text)
                if match:
                    exception_type = match.group(1)
                    result["explicit_throws"].append(exception_type)
                    if not in_try_block:
                        result["may_propagate"].append(exception_type)
            elif node.type == "try_statement":
                # Process try block separately (track what's caught)
                try_block = self.find_child_by_type(node, "block")
                if try_block:
                    find_throws(try_block, in_try_block=True)

                # Extract caught exceptions
                catch_clauses = self.find_children_by_type(node, "catch_clause")
                for catch_clause in catch_clauses:
                    catch_text = self.get_node_text(catch_clause, self._source_bytes)
                    import re

                    match = re.search(r"catch\s*\(\s*([A-Z][A-Za-z0-9_.]*)", catch_text)
                    if match:
                        exception_type = match.group(1)
                        result["caught"].append(exception_type)
            else:
                for child in node.children:
                    find_throws(child, in_try_block)

        find_throws(body)

        # Calculate uncaught exceptions that may propagate
        # (This is simplified - full analysis would require semantic type hierarchy)
        caught_set = set(result["caught"])
        may_propagate = []

        for exception in result["explicit_throws"]:
            if exception not in caught_set:
                may_propagate.append(exception)

        result["may_propagate"] = may_propagate

        return result

    def _analyze_lambda_captures(self, lambda_body: "TSNode", lambda_id: str, parent_scope: str) -> list[dict]:
        """
        Analyze variable captures in lambda expression.

        Tracks:
        1. Local variables from outer scope
        2. Fields from enclosing class
        3. Parameters from outer methods
        4. Effectively final validation (heuristic)

        Returns:
            List of captured variables with metadata
        """
        captures = []

        if not lambda_body:
            return captures

        # Track all variable references in lambda body
        def find_variable_refs(node: "TSNode", parent_type: str = None) -> list[str]:
            refs = []

            if node.type == "identifier":
                # Skip if this identifier is part of a method invocation
                if parent_type == "method_invocation":
                    return refs

                # Skip if this identifier is part of a field access as the field name
                if parent_type == "field_access":
                    # Only skip if it's the right side of the dot
                    return refs

                var_name = self.get_node_text(node, self._source_bytes)
                # Filter out method calls and type names
                # Heuristic: lowercase first char = variable
                if var_name and len(var_name) > 0 and var_name[0].islower():
                    # Additional filter: common keywords
                    if var_name not in ["this", "super", "new", "return", "throw"]:
                        refs.append(var_name)

            for child in node.children:
                refs.extend(find_variable_refs(child, node.type))

            return refs

        variable_refs = find_variable_refs(lambda_body)

        # Deduplicate
        unique_refs = list(set(variable_refs))

        # For each reference, determine if it's a capture
        for var_name in unique_refs:
            # Create capture info
            capture_info = {
                "name": var_name,
                "type": "unknown",  # Will be enhanced with semantic analysis
                "effectively_final": True,  # Assume true (heuristic)
                "scope": "outer",  # outer method or class field
            }

            captures.append(capture_info)

            # Create CAPTURES edge
            # Target ID is variable in parent scope
            target_id = f"var:{self.repo_id}:{self._source.file_path}:{parent_scope}.{var_name}"

            captures_edge = Edge(
                id=generate_edge_id(EdgeKind.CAPTURES, lambda_id, target_id),
                kind=EdgeKind.CAPTURES,
                source_id=lambda_id,
                target_id=target_id,
                attrs={
                    "variable_name": var_name,
                    "effectively_final": True,  # Heuristic
                    "capture_type": "closure",
                },
            )
            self._edges.append(captures_edge)

        return captures

    def _analyze_anonymous_class_accesses(self, anon_class_body: "TSNode", anon_class_id: str) -> list[dict]:
        """
        Analyze outer field accesses in anonymous class.

        Different from lambda captures:
        - Anonymous classes can access outer fields via 'this'
        - No effectively final requirement
        - Can modify outer state

        Returns:
            List of accessed fields
        """
        accesses = []

        if not anon_class_body:
            return accesses

        # Find 'this' references and field accesses
        def find_field_accesses(node: "TSNode") -> list[str]:
            refs = []

            # Look for field_access: this.fieldName or just fieldName
            if node.type == "field_access":
                # Get the field name
                field_name_node = self.find_child_by_type(node, "identifier")
                if field_name_node:
                    field_name = self.get_node_text(field_name_node, self._source_bytes)
                    refs.append(field_name)

            for child in node.children:
                refs.extend(find_field_accesses(child))

            return refs

        field_refs = find_field_accesses(anon_class_body)
        unique_refs = list(set(field_refs))

        for field_name in unique_refs:
            access_info = {
                "name": field_name,
                "type": "field",
                "mutable": True,  # Anonymous classes can modify fields
            }

            accesses.append(access_info)

            # Create ACCESSES edge
            target_id = f"field:{self.repo_id}:{self._source.file_path}:{self._scope.current_fqn()}.{field_name}"

            accesses_edge = Edge(
                id=generate_edge_id(EdgeKind.ACCESSES, anon_class_id, target_id),
                kind=EdgeKind.ACCESSES,
                source_id=anon_class_id,
                target_id=target_id,
                attrs={
                    "field_name": field_name,
                    "access_type": "outer_field",
                },
            )
            self._edges.append(accesses_edge)

        return accesses

    def _node_to_span(self, node: "TSNode") -> Span:
        """Convert tree-sitter node to Span."""
        return Span(
            start_line=node.start_point[0] + 1,
            start_col=node.start_point[1],
            end_line=node.end_point[0] + 1,
            end_col=node.end_point[1],
        )
