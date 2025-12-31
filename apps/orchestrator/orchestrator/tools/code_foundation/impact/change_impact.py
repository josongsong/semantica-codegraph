"""
Compute Change Impact Tool

Code Foundation 통합: Impact Analyzer
"""

import logging

from ..base import CodeFoundationTool, ToolCategory, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class ComputeChangeImpactTool(CodeFoundationTool):
    """
    변경 영향도 계산 도구

    기능:
    - 코드 변경시 영향 범위 계산
    - 하위 영향 분석
    - 리스크 점수

    Code Foundation:
    - ImpactAnalyzer: 영향 분석
    - DependencyGraph: 의존성 그래프
    """

    def __init__(self, impact_analyzer, dependency_graph):
        self.impact_analyzer = impact_analyzer
        self.dependency_graph = dependency_graph

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="compute_change_impact",
            description=(
                "코드 변경시 영향을 받는 범위와 리스크를 계산합니다. "
                "변경하려는 파일/함수를 제공하면, 영향을 받는 모든 "
                "코드 위치와 리스크 점수를 계산하여 반환합니다."
            ),
            category=ToolCategory.IMPACT_ANALYSIS,
            input_schema={
                "type": "object",
                "properties": {
                    "target_file": {"type": "string", "description": "변경할 파일"},
                    "target_function": {"type": "string", "description": "변경할 함수 (선택)", "optional": True},
                    "change_type": {
                        "type": "string",
                        "enum": ["modify", "delete", "rename"],
                        "description": "변경 유형",
                        "default": "modify",
                        "optional": True,
                    },
                },
                "required": ["target_file"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "affected_files": {"type": "array"},
                    "risk_score": {"type": "number"},
                    "impact_summary": {"type": "string"},
                },
            },
            complexity=4,
            dependencies=["find_all_references"],
            tags=["impact", "risk", "change-analysis"],
            version="1.0.0",
            stability="stable",
        )

    def execute(self, target_file: str, target_function: str = None, change_type: str = "modify") -> ToolResult:
        """변경 영향도 계산"""
        try:
            logger.info(f"Computing impact for {target_file}::{target_function or 'all'} (type={change_type})")

            # 영향 분석
            impact_result = self.impact_analyzer.analyze_impact(
                file_path=target_file, function_name=target_function, change_type=change_type
            )

            return ToolResult(
                success=True,
                data={
                    "affected_files": impact_result.affected_files,
                    "affected_functions": impact_result.affected_functions,
                    "risk_score": impact_result.risk_score,
                    "impact_summary": impact_result.summary,
                    "breaking_changes": impact_result.breaking_changes,
                },
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Error computing impact")
            return ToolResult(success=False, data=None, error=str(e), confidence=0.0)
