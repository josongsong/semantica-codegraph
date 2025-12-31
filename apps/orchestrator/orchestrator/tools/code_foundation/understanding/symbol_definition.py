"""
Get Symbol Definition Tool

Code Foundation 통합: IR Analyzer + Cross File Resolver
"""

import logging

from ..base import CodeFoundationTool, ToolCategory, ToolMetadata, ToolResult

logger = logging.getLogger(__name__)


class GetSymbolDefinitionTool(CodeFoundationTool):
    """
    심볼 정의 찾기 도구

    기능:
    - 함수, 클래스, 변수 등 모든 심볼의 정의 위치 찾기
    - 크로스 파일 해결
    - 타입 정보 포함

    Code Foundation:
    - UnifiedAnalyzer: IR 생성
    - CrossFileResolver: 심볼 해결
    """

    def __init__(self, ir_analyzer, cross_file_resolver):
        """
        Args:
            ir_analyzer: IR 분석기 (UnifiedAnalyzer)
            cross_file_resolver: 크로스 파일 해결기
        """
        self.ir_analyzer = ir_analyzer
        self.cross_file_resolver = cross_file_resolver

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_symbol_definition",
            description=(
                "주어진 심볼(함수, 클래스, 변수 등)의 정의 위치를 찾습니다. "
                "파일 경로와 심볼 이름을 제공하면, 해당 심볼이 정의된 "
                "정확한 위치(파일, 라인, 컬럼)와 시그니처를 반환합니다. "
                "크로스 파일 참조도 해결합니다."
            ),
            category=ToolCategory.CODE_UNDERSTANDING,
            input_schema={
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "찾을 심볼 이름 (예: 'MyClass', 'calculate_total')",
                    },
                    "file_path": {"type": "string", "description": "심볼이 사용된 파일 경로"},
                    "line": {
                        "type": "integer",
                        "description": "심볼이 사용된 라인 번호 (선택, 정확도 향상)",
                        "optional": True,
                    },
                },
                "required": ["symbol_name", "file_path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "definition_location": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "column": {"type": "integer"},
                        },
                    },
                    "symbol_type": {"type": "string", "description": "function, class, variable, etc."},
                    "signature": {"type": "string", "description": "심볼 시그니처"},
                    "documentation": {"type": "string", "description": "독스트링/주석"},
                },
            },
            complexity=2,
            dependencies=[],
            tags=["symbol", "definition", "navigation", "goto"],
            version="1.0.0",
            stability="stable",
        )

    def execute(self, symbol_name: str, file_path: str, line: int | None = None) -> ToolResult:
        """
        심볼 정의 찾기

        Args:
            symbol_name: 심볼 이름
            file_path: 파일 경로
            line: 라인 번호 (선택)

        Returns:
            ToolResult: 정의 위치 정보
        """
        # STRICT: Input validation
        if not symbol_name or not symbol_name.strip():
            return ToolResult(
                success=False, data=None, error="symbol_name cannot be empty", error_type="ValueError", confidence=0.0
            )

        if not file_path or not file_path.strip():
            return ToolResult(
                success=False, data=None, error="file_path cannot be empty", error_type="ValueError", confidence=0.0
            )

        try:
            logger.info(f"Finding definition for symbol='{symbol_name}' in {file_path}:{line or 'any'}")

            # 1. IR 생성 (STRICT: None 체크)
            ir_doc = self.ir_analyzer.analyze(file_path)

            if ir_doc is None:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"IR analysis returned None for file: {file_path}. File may not exist or parsing failed.",
                    error_type="AnalysisError",
                    confidence=0.0,
                )

            # 2. 심볼 해결 (STRICT: None 체크)
            symbol = self.cross_file_resolver.resolve_symbol(
                symbol_name=symbol_name, source_doc=ir_doc, source_line=line
            )

            if symbol is None:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Symbol '{symbol_name}' not found in {file_path}. Symbol may not exist or is out of scope.",
                    error_type="SymbolNotFoundError",
                    confidence=0.0,
                )

            # 3. 결과 구성 (STRICT: 모든 필드 검증)
            if not hasattr(symbol, "file_path") or symbol.file_path is None:
                raise ValueError("Symbol missing required field: file_path")
            if not hasattr(symbol, "line") or symbol.line is None:
                raise ValueError("Symbol missing required field: line")
            if not hasattr(symbol, "column") or symbol.column is None:
                raise ValueError("Symbol missing required field: column")
            if not hasattr(symbol, "kind") or symbol.kind is None:
                raise ValueError("Symbol missing required field: kind")

            result_data = {
                "definition_location": {
                    "file": str(symbol.file_path),
                    "line": int(symbol.line),
                    "column": int(symbol.column),
                },
                "symbol_type": str(symbol.kind),
                "signature": str(symbol.signature) if hasattr(symbol, "signature") and symbol.signature else "",
                "documentation": str(symbol.documentation)
                if hasattr(symbol, "documentation") and symbol.documentation
                else "",
                "scope": str(symbol.scope) if hasattr(symbol, "scope") and symbol.scope else "unknown",
                "visibility": str(symbol.visibility)
                if hasattr(symbol, "visibility") and symbol.visibility
                else "unknown",
            }

            return ToolResult(
                success=True,
                data=result_data,
                metadata={"query": {"symbol_name": symbol_name, "file_path": file_path, "line": line}},
                confidence=0.95,
            )

        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return ToolResult(success=False, data=None, error=str(e), error_type="ValidationError", confidence=0.0)
        except AttributeError as e:
            logger.error(f"Schema mismatch: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Symbol object schema mismatch: {e}",
                error_type="SchemaMismatchError",
                confidence=0.0,
            )
        except Exception as e:
            logger.exception("Unexpected error finding symbol definition")
            return ToolResult(
                success=False,
                data=None,
                error=f"Unexpected error: {str(e)}",
                error_type=type(e).__name__,
                confidence=0.0,
            )
