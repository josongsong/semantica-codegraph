"""
TypeScript IR Generator

Tree-sitter 기반 TypeScript/TSX Structural IR 생성.

Features:
- 구조 파싱 (File/Class/Interface/Function/Variable)
- Import/Export 처리
- Edge 생성 (CONTAINS/CALLS/IMPORTS)
- ts-morph adapter 통한 타입 정보 보강
- React Hooks 분석 (type-safe)

SOTA Improvements (2025-12-21):
- Type-safe React hooks (ENUM)
- Arrow function 분석 강화
- Dead code 제거
"""

import time
from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.generators.typescript.react_hooks import (
    ReactHookType,
    is_react_hook,
    get_hook_category,
)
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    CanonicalIdentity,
    generate_edge_id_v2,
    generate_node_id_v2,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, IRDocument, Node, Span
from codegraph_engine.code_foundation.infrastructure.parsing import AstTree
from codegraph_engine.code_foundation.infrastructure.parsing.source_file import SourceFile

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.base import ExternalAnalyzer
    from codegraph_analysis.security_analysis.domain.models import UnifiedSymbol
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class _TypeScriptIRGenerator(IRGenerator):
    """
    TypeScript IR generator using tree-sitter-typescript.

    ⚠️ INTERNAL USE ONLY - Do NOT instantiate directly!
    Use LayeredIRBuilder instead for full 9-layer IR construction.

    This generator only provides Layer 1 (Structural IR).
    Direct usage will miss Layers 2-9 (Occurrence, LSP, CrossFile, Semantic, etc.)

    Correct usage:
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
        builder = LayeredIRBuilder(project_root)
        ir_docs, ctx, idx, diag, pkg = await builder.build_full(files)

    Features (Layer 1 only):
    - File/Class/Interface/Function/Variable 노드 생성
    - Import/Export 분석
    - Edge 생성 (CONTAINS/CALLS/IMPORTS)
    - External analyzer (ts-morph) 통한 타입 정보
    """

    def __init__(self, repo_id: str, external_analyzer: "ExternalAnalyzer | None" = None):
        """
        Initialize TypeScript generator.

        Args:
            repo_id: Repository identifier
            external_analyzer: Optional external analyzer (ts-morph)
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

        self._timings: dict[str, float] = {}

        # O(1) occurrence counter for CALLS edges (optimization from O(n²) to O(1))
        self._call_counts: dict[tuple[str, str], int] = {}

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

        from codegraph_engine.code_foundation.domain.models import UnifiedSymbol
        from codegraph_engine.code_foundation.infrastructure.version_detector import VersionDetector

        # Extract FQN
        fqn = node.attrs.get("fqn", node.name)

        # Create SCIP descriptor suffix
        descriptor = fqn
        if node.kind.value in ["Function", "Method", "ArrowFunction"]:
            descriptor += "()."
        elif node.kind.value in ["Class", "Interface"]:
            descriptor += "#"
        elif node.kind.value == "Enum":
            descriptor += "#"
        else:
            descriptor += "."

        # Extract package name from file path or use module FQN
        module_fqn = self._get_module_fqn(source.file_path)
        package_name = module_fqn.split(".")[0] if module_fqn else "default"

        # Detect version
        try:
            project_root = str(Path(source.file_path).parent.absolute())
            detector = VersionDetector(project_root)
            version = detector.detect_version("typescript", package_name)
        except Exception:
            version = "unknown"

        return UnifiedSymbol(
            scheme="typescript",
            manager="npm",
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
        Generate IR from TypeScript source.

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
        self._call_counts.clear()  # Reset O(1) occurrence counter
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

        # Initialize scope
        module_fqn = self._get_module_fqn(source.file_path)
        self._scope = ScopeStack(module_fqn)

        # Generate nodes
        gen_start = time.perf_counter()
        self._process_root()
        self._timings["node_generation_ms"] = (time.perf_counter() - gen_start) * 1000

        self._timings["total_ms"] = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"TypeScript IR generated: {len(self._nodes)} nodes, "
            f"{len(self._edges)} edges in {self._timings['total_ms']:.1f}ms"
        )

        # Generate UnifiedSymbols for cross-language resolution
        unified_symbols = []
        for node in self._nodes:
            # Only create UnifiedSymbols for definitions
            if node.kind.value in ["Class", "Function", "Method", "Interface", "Enum", "ArrowFunction"]:
                try:
                    unified = self._create_unified_symbol(node, source)
                    unified_symbols.append(unified)
                except Exception as e:
                    # Skip if conversion fails (SOTA: No dead code)
                    logger.debug(f"Failed to create UnifiedSymbol for {node.name}: {e}")

        return IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="4.1.0",
            nodes=self._nodes,
            edges=self._edges,
            unified_symbols=unified_symbols,
            meta={
                "file_path": source.file_path,
                "language": "typescript",
                "timings": self._timings,
            },
        )

    def _get_module_fqn(self, file_path: str) -> str:
        """Get module FQN from file path."""
        # src/utils/helper.ts -> src.utils.helper
        path = file_path.replace(".ts", "").replace(".tsx", "").replace("/", ".")
        return path

    def _process_root(self) -> None:
        """Process root node and traverse."""
        root = self._ast.root

        # Create file node
        file_node = self._create_file_node()
        self._nodes.append(file_node)

        # Process top-level declarations
        for child in root.children:
            if child.type in ["class_declaration", "interface_declaration"]:
                self._process_class_or_interface(child, file_node.id)
            elif child.type == "function_declaration":
                self._process_function(child, file_node.id)
            elif child.type in ["lexical_declaration", "variable_declaration"]:
                self._process_variable(child, file_node.id)
            elif child.type in ["import_statement", "export_statement"]:
                self._process_import_export(child, file_node.id)

    def _create_file_node(self) -> Node:
        """Create file node."""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        # RFC-031 Phase B: Use Hash ID with CanonicalIdentity
        fqn = self._get_module_fqn(self._source.file_path)
        identity = CanonicalIdentity(
            repo_id=self.repo_id,
            kind=NodeKind.FILE.value,
            file_path=self._source.file_path,
            fqn=fqn,
            language="typescript",
        )

        return Node(
            id=generate_node_id_v2(identity),
            kind=NodeKind.FILE,
            name=self._source.file_path.split("/")[-1],
            fqn=self._get_module_fqn(self._source.file_path),
            span=Span(
                start_line=1,
                end_line=len(self._source.content.splitlines()),
                start_col=0,
                end_col=0,
            ),
            file_path=self._source.file_path,
            language="typescript",
        )

    def _process_class_or_interface(self, node: "TSNode", parent_id: str) -> None:
        """
        Process class or interface declaration (SOTA upgrade).

        New features:
        - Extract decorators (@Component, @Injectable, etc.)
        - Extract generic type parameters (<T extends U>)
        - Store type metadata in attrs
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        node_kind = NodeKind.CLASS if node.type == "class_declaration" else NodeKind.INTERFACE

        class_fqn = f"{self._scope.current_fqn()}.{name}"

        # SOTA: Extract decorators (Angular/NestJS patterns)
        decorators = self._extract_decorators(node)

        # SOTA: Extract generic type parameters
        generic_params = self._extract_generic_params(node)

        # RFC-031 Phase B: Use Hash ID with CanonicalIdentity
        identity = CanonicalIdentity(
            repo_id=self.repo_id,
            kind=node_kind.value,
            file_path=self._source.file_path,
            fqn=class_fqn,
            language="typescript",
        )

        class_node = Node(
            id=generate_node_id_v2(identity),
            kind=node_kind,
            name=name,
            fqn=class_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            attrs={
                "decorators": decorators,
                "generic_params": generic_params,
            }
            if decorators or generic_params
            else {},
        )

        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(class_node)
        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS.value, parent_id, class_node.id),
                source_id=parent_id,
                target_id=class_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process members
        body = node.child_by_field_name("body")
        if body:
            # Fix: node_kind.value is "Class", but ScopeKind needs "class" (lowercase)
            scope_kind = "class" if node_kind.value == "Class" else node_kind.value.lower()
            self._scope.push(scope_kind, name, class_node.fqn)
            for child in body.children:
                if child.type == "method_definition":
                    self._process_method(child, class_node.id)
                elif child.type in ["public_field_definition", "property_signature"]:
                    self._process_field(child, class_node.id)
            self._scope.pop()

    def _extract_decorators(self, node: "TSNode") -> list[dict]:
        """
        Extract TypeScript/Angular decorators

        Examples:
        - @Component({selector: 'app-root'})
        - @Input() name: string
        - @Injectable()

        Returns:
            List of decorator metadata
        """
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import DecoratorExtractor

        extractor = DecoratorExtractor()
        return extractor.extract_decorators(node)

    def _extract_generic_params(self, node: "TSNode") -> list[dict]:
        """
        Extract generic type parameters

        Examples:
        - class Box<T> { ... }
        - function identity<T extends NonNullable<any>>(arg: T): T { ... }
        - interface Props<T = string> { ... }

        Returns:
            List of {
                'name': 'T',
                'constraint': 'NonNullable<any>',
                'default': 'string'
            }
        """
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import (
            TypeScriptTypeParser,
        )

        # Find type_parameters child
        type_params_node = node.child_by_field_name("type_parameters")
        if not type_params_node:
            return []

        parser = TypeScriptTypeParser()
        return parser.parse_generic_params(type_params_node)

    def _parse_type_annotation(self, node: "TSNode") -> dict | None:
        """
        Parse TypeScript type annotation

        Handles:
        - Union types: string | null
        - Intersection types: Base & Mixin
        - Generic types: Promise<User>
        - Utility types: NonNullable<T>

        Returns:
            Type metadata dict
        """
        from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import (
            TypeScriptTypeParser,
        )

        if not node:
            return None

        type_annotation = node.child_by_field_name("type")
        if not type_annotation:
            return None

        parser = TypeScriptTypeParser()

        # Check type kind
        if type_annotation.type == "union_type":
            return parser.parse_union_type(type_annotation)
        elif type_annotation.type == "intersection_type":
            return parser.parse_intersection_type(type_annotation)
        else:
            # Simple type or complex nested type
            type_str = self._get_node_text(type_annotation)

            # Check if utility type
            utility_info = parser.parse_utility_type(type_str)
            if utility_info:
                return utility_info

            # Default: simple type
            return {"kind": "simple", "type": type_str, "is_nullable": "null" in type_str or "undefined" in type_str}

    def _is_async_function(self, node: "TSNode") -> bool:
        """Check if function is async"""
        # Check for 'async' modifier
        for child in node.children:
            if child.type == "async":
                return True
        return False

    def _is_react_hook_call(self, node: "TSNode") -> tuple[bool, str | None]:
        """
        Detect React hook calls

        Examples:
        - const [state, setState] = useState(null)
        - useEffect(() => {}, [deps])
        - const ref = useRef<HTMLDivElement>(null)

        Returns:
            (is_hook, hook_name)
        """
        if node.type != "call_expression":
            return False, None

        callee = node.child_by_field_name("function")
        if not callee:
            return False, None

        func_name = self._get_node_text(callee)

        # React hooks start with 'use'
        if func_name.startswith("use") and func_name[3:4].isupper():
            return True, func_name

        return False, None

    def _process_function(self, node: "TSNode", parent_id: str) -> None:
        """
        Process function declaration (SOTA upgrade).

        New features:
        - Detect async functions (add 'is_async' to attrs)
        - Extract generic type parameters
        - Extract return type annotation
        - Detect React hooks usage
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        func_fqn = f"{self._scope.current_fqn()}.{name}"

        # SOTA: Check if async function
        is_async = self._is_async_function(node)

        # SOTA: Extract generic params
        generic_params = self._extract_generic_params(node)

        # SOTA: Extract return type
        return_type = self._parse_type_annotation(node)

        # Calculate control flow summary
        body = node.child_by_field_name("body")
        cf_summary = None
        if body:
            from codegraph_engine.code_foundation.infrastructure.generators.typescript.cfg_lowering import (
                calculate_control_flow_summary,
            )
            from codegraph_engine.code_foundation.infrastructure.ir.models.core import ControlFlowSummary

            cf_data = calculate_control_flow_summary(body)

            # SOTA: Add async edge if function is async
            if is_async:
                cf_data["is_async"] = True

            cf_summary = ControlFlowSummary(
                cyclomatic_complexity=cf_data["cyclomatic_complexity"],
                has_loop=cf_data["has_loop"],
                has_try=cf_data["has_try"],
                branch_count=cf_data["branch_count"],
            )

        # SOTA: Detect React hooks in body (type-safe)
        uses_hooks = []
        if body:
            uses_hooks = self._detect_react_hooks_in_body(body)

        # RFC-19: Extract type_info for null analysis
        type_info = self._extract_type_info(node)

        # RFC-19: Extract body statements for null analysis
        body_statements = []
        if body:
            body_statements = self._extract_body_statements(body)

        # Build attrs
        attrs = {}
        if is_async:
            attrs["is_async"] = is_async
        if generic_params:
            attrs["generic_params"] = generic_params
        if return_type:
            attrs["return_type"] = return_type
        if uses_hooks:
            attrs["uses_hooks"] = uses_hooks
            # SOTA: Extract hook categories for analysis
            hook_categories = list(set(h["category"] for h in uses_hooks))
            attrs["hook_categories"] = hook_categories

        # RFC-19: Add type_info and parameters
        if type_info:
            attrs["type_info"] = type_info
            if "parameters" in type_info:
                attrs["parameters"] = type_info["parameters"]

        # RFC-19: Add body_statements
        if body_statements:
            attrs["body_statements"] = body_statements

        # RFC-031 Phase B: Use Hash ID
        identity = CanonicalIdentity(
            repo_id=self.repo_id,
            kind=NodeKind.FUNCTION.value,
            file_path=self._source.file_path,
            fqn=func_fqn,
            language="typescript",
        )

        func_node = Node(
            id=generate_node_id_v2(identity),
            kind=NodeKind.FUNCTION,
            name=name,
            fqn=func_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            control_flow_summary=cf_summary,
            attrs=attrs,
        )

        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(func_node)
        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS.value, parent_id, func_node.id),
                source_id=parent_id,
                target_id=func_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process function body for calls
        if body:
            self._process_calls_in_body(body, func_node.id)

    def _extract_type_info(self, func_node: "TSNode") -> dict:
        """
        Extract type information from function (RFC-19 support).

        Parses:
        - Parameters with type annotations (T | null, T | undefined)
        - Return type annotations

        Args:
            func_node: Function declaration AST node

        Returns:
            Dictionary with 'parameters' and 'return_type' keys
        """
        type_info = {}

        # Extract parameters
        params_node = func_node.child_by_field_name("parameters")
        if params_node:
            parameters = []

            for child in params_node.children:
                if child.type in ("required_parameter", "optional_parameter"):
                    param_info = self._parse_parameter(child)
                    if param_info:
                        parameters.append(param_info)

            if parameters:
                type_info["parameters"] = parameters

        # Extract return type
        return_type_node = func_node.child_by_field_name("return_type")
        if return_type_node:
            return_type_text = self._get_node_text(return_type_node)
            # Remove leading ':' if present
            return_type_text = return_type_text.lstrip(": ")

            type_info["return_type"] = return_type_text

            # Check if nullable (T | null, T | undefined)
            if (
                " | null" in return_type_text
                or "|null" in return_type_text
                or " | undefined" in return_type_text
                or "|undefined" in return_type_text
            ):
                type_info["return_nullable"] = True
            else:
                type_info["return_nullable"] = False

        return type_info

    def _parse_parameter(self, param_node: "TSNode") -> dict | None:
        """
        Parse parameter with type annotation.

        Examples:
        - id: string → {"name": "id", "type": "string", "nullable": False}
        - id: string | null → {"name": "id", "type": "string | null", "nullable": True}
        - id?: string → {"name": "id", "type": "string", "nullable": True}

        Args:
            param_node: Parameter AST node

        Returns:
            Parameter info dict or None
        """
        param_name = None
        param_type = None
        is_optional = param_node.type == "optional_parameter"

        # Find name
        name_node = param_node.child_by_field_name("pattern")
        if name_node and name_node.type == "identifier":
            param_name = self._get_node_text(name_node)

        # Find type
        type_node = param_node.child_by_field_name("type")
        if type_node:
            param_type = self._get_node_text(type_node)
            # Remove leading ':' if present
            param_type = param_type.lstrip(": ")

        if not param_name:
            return None

        param_info = {"name": param_name}

        if param_type:
            param_info["type"] = param_type

            # Check if nullable
            if (
                is_optional
                or " | null" in param_type
                or "|null" in param_type
                or " | undefined" in param_type
                or "|undefined" in param_type
            ):
                param_info["nullable"] = True
            else:
                param_info["nullable"] = False
        elif is_optional:
            param_info["nullable"] = True

        return param_info

    def _extract_body_statements(self, body_node: "TSNode") -> list[dict]:
        """
        Extract body statements for null analysis (RFC-19 support).

        Extracts:
        - Method calls (x.method())
        - Property access (x.prop)
        - Return statements

        Args:
            body_node: Function body block node

        Returns:
            List of statement dictionaries
        """
        statements = []

        def visit_node(node: "TSNode"):
            # Method call: x.method()
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node and func_node.type == "member_expression":
                    obj_node = func_node.child_by_field_name("object")
                    prop_node = func_node.child_by_field_name("property")
                    if obj_node and prop_node:
                        statements.append(
                            {
                                "type": "method_call",
                                "object": self._get_node_text(obj_node),
                                "method": self._get_node_text(prop_node),
                            }
                        )

            # Property access: x.prop
            elif node.type == "member_expression":
                obj_node = node.child_by_field_name("object")
                prop_node = node.child_by_field_name("property")
                if obj_node and prop_node:
                    statements.append(
                        {
                            "type": "field_access",
                            "object": self._get_node_text(obj_node),
                            "field": self._get_node_text(prop_node),
                        }
                    )

            # Return statement
            elif node.type == "return_statement":
                for child in node.children:
                    if child.type != "return":
                        value_text = self._get_node_text(child)
                        statements.append(
                            {
                                "type": "return",
                                "value": value_text,
                            }
                        )
                        # Check for null/undefined return
                        if value_text in ("null", "undefined"):
                            statements.append(
                                {
                                    "type": "return_null",
                                    "value": value_text,
                                }
                            )

            # Recurse
            for child in node.children:
                visit_node(child)

        visit_node(body_node)
        return statements

    def _detect_react_hooks_in_body(self, body_node: "TSNode") -> list[dict]:
        """
        Detect React hooks usage in function body (SOTA: Type-safe with ENUM).

        Returns:
            List of hook info: [{"name": "useState", "type": ReactHookType.USE_STATE, "category": "STATE"}]
        """
        hooks = []
        seen_hooks = set()

        def traverse(node: "TSNode") -> None:
            is_hook, hook_type = self._is_react_hook_call(node)
            if is_hook:
                # Get hook name (from ENUM or custom)
                hook_name = hook_type.value if hook_type else self._get_node_text(node.child_by_field_name("function"))

                if hook_name and hook_name not in seen_hooks:
                    seen_hooks.add(hook_name)

                    hook_info = {"name": hook_name}

                    # SOTA: Add type-safe metadata if known hook
                    if hook_type:
                        hook_info["hook_type"] = hook_type
                        hook_info["category"] = get_hook_category(hook_type).value
                    else:
                        hook_info["category"] = "CUSTOM"

                    hooks.append(hook_info)

            # Recursively traverse children
            for child in node.children:
                traverse(child)

        traverse(body_node)
        return hooks

    def _process_method(self, node: "TSNode", parent_id: str) -> None:
        """
        Process method definition (SOTA upgrade).

        New features:
        - Extract decorators (@Input, @Output, @HostListener, etc.)
        - Detect async methods
        - Extract generic params
        - Extract return type
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        method_fqn = f"{self._scope.current_fqn()}.{name}"

        # SOTA: Extract decorators (Angular @Input, @Output, etc.)
        decorators = self._extract_decorators(node)

        # SOTA: Check if async method
        is_async = self._is_async_function(node)

        # SOTA: Extract generic params
        generic_params = self._extract_generic_params(node)

        # SOTA: Extract return type
        return_type = self._parse_type_annotation(node)

        # Calculate control flow summary
        body = node.child_by_field_name("body")
        cf_summary = None
        if body:
            from codegraph_engine.code_foundation.infrastructure.generators.typescript.cfg_lowering import (
                calculate_control_flow_summary,
            )
            from codegraph_engine.code_foundation.infrastructure.ir.models.core import ControlFlowSummary

            cf_data = calculate_control_flow_summary(body)

            # SOTA: Add async edge if method is async
            if is_async:
                cf_data["is_async"] = True

            cf_summary = ControlFlowSummary(
                cyclomatic_complexity=cf_data["cyclomatic_complexity"],
                has_loop=cf_data["has_loop"],
                has_try=cf_data["has_try"],
                branch_count=cf_data["branch_count"],
            )

        # RFC-19: Extract type_info for null analysis
        type_info = self._extract_type_info(node)

        # RFC-19: Extract body statements for null analysis
        body_statements = []
        if body:
            body_statements = self._extract_body_statements(body)

        # Build attrs
        attrs = {}
        if decorators:
            attrs["decorators"] = decorators
        if is_async:
            attrs["is_async"] = is_async
        if generic_params:
            attrs["generic_params"] = generic_params
        if return_type:
            attrs["return_type"] = return_type

        # RFC-19: Add type_info and parameters
        if type_info:
            attrs["type_info"] = type_info
            if "parameters" in type_info:
                attrs["parameters"] = type_info["parameters"]

        # RFC-19: Add body_statements
        if body_statements:
            attrs["body_statements"] = body_statements

        # RFC-031 Phase B: Use Hash ID
        identity = CanonicalIdentity(
            repo_id=self.repo_id,
            kind=NodeKind.METHOD.value,
            file_path=self._source.file_path,
            fqn=method_fqn,
            language="typescript",
        )

        method_node = Node(
            id=generate_node_id_v2(identity),
            kind=NodeKind.METHOD,
            name=name,
            fqn=method_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            control_flow_summary=cf_summary,
            attrs=attrs,
        )

        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(method_node)
        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS.value, parent_id, method_node.id),
                source_id=parent_id,
                target_id=method_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process method body for calls
        if body:
            self._process_calls_in_body(body, method_node.id)

    def _process_field(self, node: "TSNode", parent_id: str) -> None:
        """
        Process field/property (SOTA upgrade).

        New features:
        - Extract decorators (@Input, @Output, @ViewChild, etc.)
        - Extract type annotation (including union/nullable types)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        field_fqn = f"{self._scope.current_fqn()}.{name}"

        # SOTA: Extract decorators (Angular @Input, @Output, etc.)
        decorators = self._extract_decorators(node)

        # SOTA: Extract type annotation
        field_type = self._parse_type_annotation(node)

        # RFC-031 Phase B: Use Hash ID
        identity = CanonicalIdentity(
            repo_id=self.repo_id,
            kind=NodeKind.FIELD.value,
            file_path=self._source.file_path,
            fqn=field_fqn,
            language="typescript",
        )

        field_node = Node(
            id=generate_node_id_v2(identity),
            kind=NodeKind.FIELD,
            name=name,
            fqn=field_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            attrs={
                "decorators": decorators,
                "field_type": field_type,
            }
            if (decorators or field_type)
            else {},
        )

        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(field_node)
        self._edges.append(
            Edge(
                id=generate_edge_id_v2(EdgeKind.CONTAINS.value, parent_id, field_node.id),
                source_id=parent_id,
                target_id=field_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

    def _process_variable(self, node: "TSNode", parent_id: str) -> None:
        """Process variable declaration."""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import NodeKind

        # lexical_declaration has variable_declarator children
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._get_node_text(name_node)

                    var_fqn = f"{self._scope.current_fqn()}.{name}"

                    # RFC-031 Phase B: Use Hash ID
                    identity = CanonicalIdentity(
                        repo_id=self.repo_id,
                        kind=NodeKind.VARIABLE.value,
                        file_path=self._source.file_path,
                        fqn=var_fqn,
                        language="typescript",
                    )

                    var_node = Node(
                        id=generate_node_id_v2(identity),
                        kind=NodeKind.VARIABLE,
                        name=name,
                        fqn=var_fqn,
                        span=self._node_to_span(child),
                        file_path=self._source.file_path,
                        language="typescript",
                    )

                    from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

                    self._nodes.append(var_node)
                    self._edges.append(
                        Edge(
                            id=generate_edge_id_v2(EdgeKind.CONTAINS.value, parent_id, var_node.id),
                            source_id=parent_id,
                            target_id=var_node.id,
                            kind=EdgeKind.CONTAINS,
                        )
                    )

    def _process_import_export(self, node: "TSNode", parent_id: str) -> None:
        """Process import/export statements."""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind, NodeKind

        if node.type == "import_statement":
            # Get import source
            source_node = node.child_by_field_name("source")
            if source_node:
                import_source = self._get_node_text(source_node).strip("'\"")

                # Create import node
                import_fqn = f"{self._scope.current_fqn()}.import.{import_source.replace('/', '.')}"

                # RFC-031 Phase B: Use Hash ID
                identity = CanonicalIdentity(
                    repo_id=self.repo_id,
                    kind=NodeKind.IMPORT.value,
                    file_path=self._source.file_path,
                    fqn=import_fqn,
                    language="typescript",
                )

                import_node = Node(
                    id=generate_node_id_v2(identity),
                    kind=NodeKind.IMPORT,
                    name=import_source,
                    fqn=import_fqn,
                    span=self._node_to_span(node),
                    file_path=self._source.file_path,
                    language="typescript",
                    attrs={"import_source": import_source},
                )

                self._nodes.append(import_node)

                # Create IMPORTS edge (file imports module)
                # Use file node ID from parent (already in correct format)
                self._edges.append(
                    Edge(
                        id=generate_edge_id_v2(EdgeKind.IMPORTS.value, parent_id, import_source),
                        source_id=parent_id,  # parent_id is file node ID
                        target_id=import_source,  # Target는 나중에 resolve
                        kind=EdgeKind.IMPORTS,
                        attrs={"import_path": import_source},
                    )
                )

    def _get_node_text(self, node: "TSNode") -> str:
        """Get text content of a node."""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import get_node_text

        return get_node_text(node, self._source_bytes, self._source.encoding)

    def _process_calls_in_body(self, body_node: "TSNode", caller_id: str) -> None:
        """Process all call expressions in function/method body."""
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        def traverse(node: "TSNode") -> None:
            if node.type == "call_expression":
                # Get function being called
                func_node = node.child_by_field_name("function")
                if func_node:
                    callee_name = self._get_node_text(func_node)

                    # Simple callee resolution (scope-based resolution in Layer 4)
                    module_fqn = self._get_module_fqn(self._source.file_path)
                    callee_id = f"func:{module_fqn}.{callee_name}"

                    # Create CALLS edge
                    # OPTIMIZATION: O(1) lookup instead of O(n) list scan
                    key = (caller_id, callee_id)
                    occurrence = self._call_counts.get(key, 0)
                    self._call_counts[key] = occurrence + 1

                    self._edges.append(
                        Edge(
                            id=generate_edge_id_v2(EdgeKind.CALLS.value, caller_id, callee_id, occurrence),
                            kind=EdgeKind.CALLS,
                            source_id=caller_id,
                            target_id=callee_id,
                            span=self._node_to_span(node),
                            attrs={"callee_name": callee_name},
                        )
                    )

            # Recursive traversal
            for child in node.children:
                traverse(child)

        traverse(body_node)

    def _node_to_span(self, node: "TSNode") -> Span:
        """Convert TSNode to Span."""
        return Span(
            start_line=node.start_point[0] + 1,  # 1-indexed
            end_line=node.end_point[0] + 1,
            start_col=node.start_point[1],
            end_col=node.end_point[1],
        )
