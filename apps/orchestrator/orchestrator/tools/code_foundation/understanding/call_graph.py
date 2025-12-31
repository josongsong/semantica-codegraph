"""
Build Call Graph Tool

Code Foundation 통합: Precise Call Graph Builder
"""

import logging

from ..base import CodeFoundationTool, ToolCategory, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class BuildCallGraphTool(CodeFoundationTool):
    """
    호출 그래프 구축 도구

    기능:
    - 함수/메서드 호출 관계 그래프
    - Caller/Callee 관계
    - 정밀 호출 그래프 (타입 좁히기)

    Code Foundation:
    - PreciseCallGraphBuilder: 정밀 호출 그래프
    - TypeNarrowing: 타입 좁히기
    """

    def __init__(self, call_graph_builder, type_narrowing=None):
        """
        Args:
            call_graph_builder: 호출 그래프 빌더
            type_narrowing: 타입 좁히기 (선택)
        """
        self.call_graph_builder = call_graph_builder
        self.type_narrowing = type_narrowing

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="build_call_graph",
            description=(
                "주어진 함수/메서드의 호출 관계 그래프를 구축합니다. "
                "누가 이 함수를 호출하는지(caller), "
                "이 함수가 누구를 호출하는지(callee)를 분석합니다. "
                "타입 좁히기를 통해 정밀한 호출 그래프를 생성합니다."
            ),
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "분석할 함수/메서드 이름"},
                    "file_path": {"type": "string", "description": "함수가 정의된 파일"},
                    "direction": {
                        "type": "string",
                        "enum": ["callers", "callees", "both"],
                        "description": "호출 방향 (기본 both)",
                        "default": "both",
                        "optional": True,
                    },
                    "depth": {"type": "integer", "description": "탐색 깊이 (기본 2)", "default": 2, "optional": True},
                },
                "required": ["function_name", "file_path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "callers": {"type": "array", "description": "이 함수를 호출하는 함수들"},
                    "callees": {"type": "array", "description": "이 함수가 호출하는 함수들"},
                    "graph": {"type": "object", "description": "전체 호출 그래프"},
                },
            },
            complexity=4,
            dependencies=["get_symbol_definition"],
            tags=["call-graph", "caller", "callee", "dependencies"],
            version="1.0.0",
            stability="stable",
        )

    def execute(self, function_name: str, file_path: str, direction: str = "both", depth: int = 2) -> ToolResult:
        """
        호출 그래프 구축

        Args:
            function_name: 함수 이름
            file_path: 파일 경로
            direction: 호출 방향
            depth: 탐색 깊이

        Returns:
            ToolResult: 호출 그래프
        """
        try:
            logger.info(
                f"Building call graph for {function_name} in {file_path} (direction={direction}, depth={depth})"
            )

            # 호출 그래프 구축
            call_graph = self.call_graph_builder.build_precise_cg(
                target_function=function_name, file_path=file_path, use_type_narrowing=self.type_narrowing is not None
            )

            # 결과 추출
            callers = []
            callees = []

            if direction in ["callers", "both"]:
                callers = call_graph.get_callers(function_name, depth=depth)

            if direction in ["callees", "both"]:
                callees = call_graph.get_callees(function_name, depth=depth)

            # 그래프 직렬화
            graph_data = {
                "nodes": [{"name": node.name, "file": node.file_path, "line": node.line} for node in call_graph.nodes],
                "edges": [
                    {"from": edge.caller, "to": edge.callee, "confidence": edge.confidence} for edge in call_graph.edges
                ],
            }

            return ToolResult(
                success=True,
                data={
                    "callers": callers,
                    "callees": callees,
                    "graph": graph_data,
                    "total_nodes": len(call_graph.nodes),
                    "total_edges": len(call_graph.edges),
                },
                metadata={"query": {"function_name": function_name, "direction": direction, "depth": depth}},
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Error building call graph")
            return ToolResult(success=False, data=None, error=str(e), error_type=type(e).__name__, confidence=0.0)
