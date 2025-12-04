"""
TypeScript IR Generator

Tree-sitter 기반 TypeScript/TSX Structural IR 생성.

Features:
- 구조 파싱 (File/Class/Interface/Function/Variable)
- Import/Export 처리
- Edge 생성 (CONTAINS/CALLS/IMPORTS)
- ts-morph adapter 통한 타입 정보 보강
"""

import time
from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.generators.base import IRGenerator
from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.ir.models import Edge, IRDocument, Node, Span
from src.contexts.code_foundation.infrastructure.parsing import AstTree
from src.contexts.code_foundation.infrastructure.parsing.source_file import SourceFile

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from src.contexts.code_foundation.infrastructure.ir.external_analyzers.base import ExternalAnalyzer
from src.common.observability import get_logger

logger = get_logger(__name__)


class TypeScriptIRGenerator(IRGenerator):
    """
    TypeScript IR generator using tree-sitter-typescript.

    Features:
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

        return IRDocument(
            repo_id=self.repo_id,
            snapshot_id=snapshot_id,
            schema_version="4.1.0",
            nodes=self._nodes,
            edges=self._edges,
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
                self._process_import_export(child)

    def _create_file_node(self) -> Node:
        """Create file node."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        return Node(
            id=f"file:{self._source.file_path}",
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
        """Process class or interface declaration."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        node_kind = NodeKind.CLASS if node.type == "class_declaration" else NodeKind.INTERFACE

        class_fqn = f"{self._scope.current_fqn()}.{name}"

        class_node = Node(
            id=f"{node_kind.value.lower()}:{class_fqn}",
            kind=node_kind,
            name=name,
            fqn=class_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
        )

        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(class_node)
        self._edges.append(
            Edge(
                id=f"edge:contains:{parent_id}→{class_node.id}",
                source_id=parent_id,
                target_id=class_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process members
        body = node.child_by_field_name("body")
        if body:
            self._scope.push(node_kind.value, name, class_node.fqn)
            for child in body.children:
                if child.type == "method_definition":
                    self._process_method(child, class_node.id)
                elif child.type in ["public_field_definition", "property_signature"]:
                    self._process_field(child, class_node.id)
            self._scope.pop()

    def _process_function(self, node: "TSNode", parent_id: str) -> None:
        """Process function declaration."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        func_fqn = f"{self._scope.current_fqn()}.{name}"

        # Calculate control flow summary
        body = node.child_by_field_name("body")
        cf_summary = None
        if body:
            from src.contexts.code_foundation.infrastructure.generators.typescript.cfg_lowering import (
                calculate_control_flow_summary,
            )
            from src.contexts.code_foundation.infrastructure.ir.models.core import ControlFlowSummary

            cf_data = calculate_control_flow_summary(body)
            cf_summary = ControlFlowSummary(
                cyclomatic_complexity=cf_data["cyclomatic_complexity"],
                has_loop=cf_data["has_loop"],
                has_try=cf_data["has_try"],
                branch_count=cf_data["branch_count"],
            )

        func_node = Node(
            id=f"func:{func_fqn}",
            kind=NodeKind.FUNCTION,
            name=name,
            fqn=func_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            control_flow_summary=cf_summary,
        )

        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(func_node)
        self._edges.append(
            Edge(
                id=f"edge:contains:{parent_id}→{func_node.id}",
                source_id=parent_id,
                target_id=func_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process function body for calls
        if body:
            self._process_calls_in_body(body, func_node.id)

    def _process_method(self, node: "TSNode", parent_id: str) -> None:
        """Process method definition."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        method_fqn = f"{self._scope.current_fqn()}.{name}"

        # Calculate control flow summary
        body = node.child_by_field_name("body")
        cf_summary = None
        if body:
            from src.contexts.code_foundation.infrastructure.generators.typescript.cfg_lowering import (
                calculate_control_flow_summary,
            )
            from src.contexts.code_foundation.infrastructure.ir.models.core import ControlFlowSummary

            cf_data = calculate_control_flow_summary(body)
            cf_summary = ControlFlowSummary(
                cyclomatic_complexity=cf_data["cyclomatic_complexity"],
                has_loop=cf_data["has_loop"],
                has_try=cf_data["has_try"],
                branch_count=cf_data["branch_count"],
            )

        method_node = Node(
            id=f"method:{method_fqn}",
            kind=NodeKind.METHOD,
            name=name,
            fqn=method_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
            control_flow_summary=cf_summary,
        )

        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(method_node)
        self._edges.append(
            Edge(
                id=f"edge:contains:{parent_id}→{method_node.id}",
                source_id=parent_id,
                target_id=method_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

        # Process method body for calls
        if body:
            self._process_calls_in_body(body, method_node.id)

    def _process_field(self, node: "TSNode", parent_id: str) -> None:
        """Process field/property."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        field_fqn = f"{self._scope.current_fqn()}.{name}"

        field_node = Node(
            id=f"field:{field_fqn}",
            kind=NodeKind.FIELD,
            name=name,
            fqn=field_fqn,
            span=self._node_to_span(node),
            file_path=self._source.file_path,
            language="typescript",
        )

        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

        self._nodes.append(field_node)
        self._edges.append(
            Edge(
                id=f"edge:contains:{parent_id}→{field_node.id}",
                source_id=parent_id,
                target_id=field_node.id,
                kind=EdgeKind.CONTAINS,
            )
        )

    def _process_variable(self, node: "TSNode", parent_id: str) -> None:
        """Process variable declaration."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import NodeKind

        # lexical_declaration has variable_declarator children
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._get_node_text(name_node)

                    var_fqn = f"{self._scope.current_fqn()}.{name}"

                    var_node = Node(
                        id=f"var:{var_fqn}",
                        kind=NodeKind.VARIABLE,
                        name=name,
                        fqn=var_fqn,
                        span=self._node_to_span(child),
                        file_path=self._source.file_path,
                        language="typescript",
                    )

                    from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

                    self._nodes.append(var_node)
                    self._edges.append(
                        Edge(
                            id=f"edge:contains:{parent_id}→{var_node.id}",
                            source_id=parent_id,
                            target_id=var_node.id,
                            kind=EdgeKind.CONTAINS,
                        )
                    )

    def _process_import_export(self, node: "TSNode") -> None:
        """Process import/export statements."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind, NodeKind

        if node.type == "import_statement":
            # Get import source
            source_node = node.child_by_field_name("source")
            if source_node:
                import_source = self._get_node_text(source_node).strip("'\"")

                # Create import node
                import_fqn = f"{self._scope.current_fqn()}.import.{import_source.replace('/', '.')}"
                import_id = f"import:{import_fqn}"

                import_node = Node(
                    id=import_id,
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
                file_id = f"file:{self._source.file_path}"
                self._edges.append(
                    Edge(
                        id=f"edge:imports:{file_id}→{import_source}",
                        source_id=file_id,
                        target_id=import_source,  # Target는 나중에 resolve
                        kind=EdgeKind.IMPORTS,
                        attrs={"import_path": import_source},
                    )
                )

    def _get_node_text(self, node: "TSNode") -> str:
        """Get text content of a node."""
        return self._source_bytes[node.start_byte : node.end_byte].decode(self._source.encoding)

    def _process_calls_in_body(self, body_node: "TSNode", caller_id: str) -> None:
        """Process all call expressions in function/method body."""
        from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

        def traverse(node: "TSNode") -> None:
            if node.type == "call_expression":
                # Get function being called
                func_node = node.child_by_field_name("function")
                if func_node:
                    callee_name = self._get_node_text(func_node)

                    # Simple callee resolution
                    # TODO: 더 정교한 symbol resolution (scope 기반)
                    module_fqn = self._get_module_fqn(self._source.file_path)
                    callee_id = f"func:{module_fqn}.{callee_name}"

                    # Create CALLS edge
                    occurrence = sum(
                        1
                        for e in self._edges
                        if e.kind == EdgeKind.CALLS and e.source_id == caller_id and e.target_id == callee_id
                    )

                    edge_id = f"edge:calls:{caller_id}→{callee_id}@{occurrence}"

                    self._edges.append(
                        Edge(
                            id=edge_id,
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
