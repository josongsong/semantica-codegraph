"""
Fake Graph Builder

⚠️  TEST ONLY - DO NOT USE IN PRODUCTION ⚠️

테스트용 간단한 그래프 빌더. 실제 그래프 구축을 수행하지 않습니다.
프로덕션에서는 FoundationGraphBuilderAdapter를 사용하세요.

See Also:
    - src/contexts/code_foundation/adapters/foundation_adapters.py
    - src/contexts/code_foundation/infrastructure/graph/

Note:
    Supports both Infrastructure IRDocument (nodes) and Domain IRDocument (symbols).
    Domain IRDocument support is DEPRECATED.
"""

from typing import Any

from codegraph_engine.code_foundation.domain.models import GraphDocument, GraphEdge, GraphNode


class FakeGraphBuilder:
    """테스트용 Fake 그래프 빌더 (nodes/symbols 둘 다 지원)"""

    def _get_items(self, ir_doc: Any) -> list[Any]:
        """Get nodes or symbols from IR document"""
        if hasattr(ir_doc, "nodes") and ir_doc.nodes:
            return ir_doc.nodes
        # DEPRECATED: Domain IRDocument uses 'symbols'
        if hasattr(ir_doc, "symbols"):
            return ir_doc.symbols
        return []

    def _get_file_path(self, ir_doc: Any) -> str:
        """Get file path from IR document"""
        if hasattr(ir_doc, "file_path") and ir_doc.file_path:
            return ir_doc.file_path
        if hasattr(ir_doc, "meta") and ir_doc.meta:
            return ir_doc.meta.get("file_path", "")
        return ""

    def build(self, ir_doc: Any) -> GraphDocument:
        """그래프 빌드"""
        nodes = []
        edges = []
        file_path = self._get_file_path(ir_doc)

        # 노드/심볼을 GraphNode로 변환
        for item in self._get_items(ir_doc):
            name = getattr(item, "name", "unknown")

            # Get start/end lines (Node uses span, Symbol uses direct attrs)
            if hasattr(item, "span") and item.span:
                start_line = item.span.start_line
                end_line = item.span.end_line
            else:
                start_line = getattr(item, "start_line", 1)
                end_line = getattr(item, "end_line", 1)

            # Get type/kind
            if hasattr(item, "kind"):
                kind = item.kind
                node_type = kind.value if hasattr(kind, "value") else str(kind)
            else:
                node_type = getattr(item, "type", "unknown")

            node_id = f"{file_path}::{name}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    type=node_type,
                    name=name,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    properties={"docstring": getattr(item, "docstring", "") or ""},
                )
            )

        # 파일 노드 추가
        file_node_id = f"file::{file_path}"
        nodes.append(
            GraphNode(
                id=file_node_id,
                type="file",
                name=file_path,
                file_path=file_path,
                start_line=1,
                end_line=1,
                properties={},
            )
        )

        # 파일과 노드 간 엣지
        for item in self._get_items(ir_doc):
            name = getattr(item, "name", "unknown")
            node_id = f"{file_path}::{name}"
            edges.append(
                GraphEdge(
                    source=file_node_id,
                    target=node_id,
                    type="CONTAINS",
                    properties={},
                )
            )

        return GraphDocument(
            file_path=file_path,
            nodes=nodes,
            edges=edges,
        )
