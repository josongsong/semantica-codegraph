"""
Find All References Tool

Code Foundation 통합: Call Graph + Reference Analyzer
"""

import logging

from ..base import CodeFoundationTool, ToolCategory, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class FindAllReferencesTool(CodeFoundationTool):
    """
    모든 참조 찾기 도구

    기능:
    - 심볼이 사용되는 모든 위치 찾기
    - 호출 지점, 변수 사용 등
    - 프로젝트 전체 검색

    Code Foundation:
    - CallGraphBuilder: 호출 관계
    - ReferenceAnalyzer: 참조 분석
    """

    def __init__(self, ir_analyzer, call_graph_builder, reference_analyzer):
        """
        Args:
            ir_analyzer: IR 분석기
            call_graph_builder: 호출 그래프 빌더
            reference_analyzer: 참조 분석기
        """
        self.ir_analyzer = ir_analyzer
        self.call_graph_builder = call_graph_builder
        self.reference_analyzer = reference_analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="find_all_references",
            description=(
                "주어진 심볼의 모든 참조(사용) 위치를 찾습니다. "
                "함수 호출, 변수 사용, 클래스 인스턴스화 등 "
                "심볼이 사용되는 모든 지점을 프로젝트 전체에서 검색합니다. "
                "변경 영향 분석에 필수적인 도구입니다."
            ),
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={
                "type": "object",
                "properties": {
                    "symbol_name": {"type": "string", "description": "찾을 심볼 이름"},
                    "file_path": {"type": "string", "description": "심볼이 정의된 파일"},
                    "max_results": {
                        "type": "integer",
                        "description": "최대 결과 개수 (기본 100)",
                        "default": 100,
                        "optional": True,
                    },
                },
                "required": ["symbol_name", "file_path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "line": {"type": "integer"},
                                "column": {"type": "integer"},
                                "context": {"type": "string"},
                                "reference_type": {"type": "string"},
                            },
                        },
                    },
                    "total_count": {"type": "integer"},
                },
            },
            complexity=3,
            dependencies=["get_symbol_definition"],
            tags=["references", "usages", "impact", "navigation"],
            version="1.0.0",
            stability="stable",
        )

    def execute(self, symbol_name: str, file_path: str, max_results: int = 100) -> ToolResult:
        """
        모든 참조 찾기

        Args:
            symbol_name: 심볼 이름
            file_path: 정의 파일
            max_results: 최대 결과 수

        Returns:
            ToolResult: 참조 목록
        """
        try:
            logger.info(f"Finding references for symbol='{symbol_name}' in {file_path} (max={max_results})")

            # 1. 심볼 정의 찾기 (의존성)
            ir_doc = self.ir_analyzer.analyze(file_path)
            if not ir_doc:
                return ToolResult(
                    success=False, data=None, error=f"Failed to analyze file: {file_path}", confidence=0.0
                )

            # 2. 참조 검색
            references = self.reference_analyzer.find_references(
                symbol_name=symbol_name, definition_file=file_path, max_results=max_results
            )

            # 3. 결과 구성
            reference_list = []
            for ref in references:
                reference_list.append(
                    {
                        "file": ref.file_path,
                        "line": ref.line,
                        "column": ref.column,
                        "context": ref.context_code,
                        "reference_type": ref.ref_type,  # call, assignment, etc.
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "references": reference_list,
                    "total_count": len(reference_list),
                    "truncated": len(references) >= max_results,
                },
                metadata={"query": {"symbol_name": symbol_name, "file_path": file_path}},
                confidence=0.9,
            )

        except Exception as e:
            logger.exception("Error finding references")
            return ToolResult(success=False, data=None, error=str(e), error_type=type(e).__name__, confidence=0.0)
