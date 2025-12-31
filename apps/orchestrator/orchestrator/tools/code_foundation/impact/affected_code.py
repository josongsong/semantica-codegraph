"""Find Affected Code Tool"""

import logging

from ..base import CodeFoundationTool, ToolCategory, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class FindAffectedCodeTool(CodeFoundationTool):
    """영향받는 코드 찾기"""

    def __init__(self, impact_analyzer):
        self.impact_analyzer = impact_analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="find_affected_code",
            description="변경시 영향받는 코드 위치들을 찾습니다.",
            category=ToolCategory.IMPACT_ANALYSIS,
            input_schema={
                "type": "object",
                "properties": {"file_path": {"type": "string"}, "symbol_name": {"type": "string", "optional": True}},
                "required": ["file_path"],
            },
            output_schema={"type": "object", "properties": {"affected_locations": {"type": "array"}}},
            complexity=3,
            dependencies=["find_all_references"],
            tags=["impact", "affected"],
            version="1.0.0",
        )

    def execute(self, file_path: str, symbol_name: str = None) -> ToolResult:
        """영향받는 코드 찾기"""
        try:
            affected = self.impact_analyzer.find_affected(file_path, symbol_name)

            return ToolResult(success=True, data={"affected_locations": affected}, confidence=0.9)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e), confidence=0.0)
