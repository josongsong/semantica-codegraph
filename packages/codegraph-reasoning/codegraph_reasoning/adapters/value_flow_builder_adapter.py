"""
ValueFlowBuilder Adapter

Infrastructure ValueFlowBuilder를 Port로 래핑
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument


class ValueFlowBuilderAdapter:
    """
    ValueFlowBuilder Adapter

    Infrastructure → Port 브릿지

    Example:
        adapter = ValueFlowBuilderAdapter(workspace_root="/path/to/project")
        boundaries = adapter.discover_boundaries()
        vfg = adapter.build_from_ir(ir_documents, graph_document)
    """

    def __init__(self, workspace_root: str):
        """
        Initialize adapter

        Args:
            workspace_root: Project root directory
        """
        from ..infrastructure.cross_lang.value_flow_builder import ValueFlowBuilder

        self._builder = ValueFlowBuilder(workspace_root=workspace_root)

    def discover_boundaries(self) -> list[Any]:
        """
        서비스 경계 자동 발견 (Port 메서드)

        Scans for:
        - openapi.yaml, swagger.json
        - *.proto files
        - schema.graphql

        Returns:
            List of BoundarySpec
        """
        return self._builder.discover_boundaries()

    def build_from_ir(
        self,
        ir_documents: list["IRDocument"],
        graph_document: "GraphDocument | None" = None,
    ) -> Any:
        """
        IR에서 ValueFlowGraph 빌드 (Port 메서드)

        Args:
            ir_documents: IR documents from code analysis
            graph_document: Optional GraphDocument for edges

        Returns:
            ValueFlowGraph
        """
        return self._builder.build_from_ir(ir_documents, graph_document)

    def add_boundary_flows(
        self,
        vfg: Any,
        boundaries: list[Any],
        ir_documents: list["IRDocument"],
    ) -> int:
        """
        경계 간 플로우 추가 (Port 메서드)

        Args:
            vfg: ValueFlowGraph to augment
            boundaries: Discovered boundaries
            ir_documents: IR documents for matching

        Returns:
            Number of boundary edges added
        """
        return self._builder.add_boundary_flows(vfg, boundaries, ir_documents)
