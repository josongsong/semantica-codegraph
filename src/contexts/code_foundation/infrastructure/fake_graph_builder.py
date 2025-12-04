"""
Fake Graph Builder

테스트용 간단한 그래프 빌더
"""

from ..domain.models import GraphDocument, GraphEdge, GraphNode, IRDocument


class FakeGraphBuilder:
    """테스트용 Fake 그래프 빌더"""

    def build(self, ir_doc: IRDocument) -> GraphDocument:
        """그래프 빌드"""
        nodes = []
        edges = []

        # 심볼을 노드로 변환
        for symbol in ir_doc.symbols:
            node_id = f"{ir_doc.file_path}::{symbol.name}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    type=symbol.type,
                    name=symbol.name,
                    file_path=ir_doc.file_path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    properties={"docstring": symbol.docstring or ""},
                )
            )

        # 파일 노드 추가
        file_node_id = f"file::{ir_doc.file_path}"
        nodes.append(
            GraphNode(
                id=file_node_id,
                type="file",
                name=ir_doc.file_path,
                file_path=ir_doc.file_path,
                start_line=1,
                end_line=1,
                properties={},
            )
        )

        # 파일과 심볼 간 엣지
        for symbol in ir_doc.symbols:
            node_id = f"{ir_doc.file_path}::{symbol.name}"
            edges.append(
                GraphEdge(
                    source=file_node_id,
                    target=node_id,
                    type="CONTAINS",
                    properties={},
                )
            )

        return GraphDocument(
            file_path=ir_doc.file_path,
            nodes=nodes,
            edges=edges,
        )
