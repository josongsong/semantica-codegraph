"""
Plan Step Tool Base (RFC-041)

Step에서 사용되는 Tool의 기본 클래스.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class StepToolResult:
    """Step Tool 실행 결과"""

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "execution_time_ms": self.execution_time_ms,
            "confidence": self.confidence,
        }


class StepTool(ABC):
    """
    Step Tool 기본 클래스

    Plan의 Step에서 호출되는 Tool.
    LLM에 직접 노출되지 않음.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool 이름 (step_tool_binding에서 참조)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool 설명"""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> StepToolResult:
        """
        Tool 실행

        Args:
            **kwargs: Step에서 전달된 파라미터

        Returns:
            StepToolResult
        """
        pass

    def safe_execute(self, **kwargs) -> StepToolResult:
        """안전한 실행 (에러 처리 포함)"""
        start_time = time.time()

        try:
            result = self.execute(**kwargs)
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.exception(f"Tool {self.name} failed")
            return StepToolResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
                confidence=0.0,
            )

    def __call__(self, **kwargs) -> StepToolResult:
        return self.safe_execute(**kwargs)


class QueryDSLMixin:
    """Query DSL 사용을 위한 Mixin"""

    def _get_query_engine(self, ir_doc: Any) -> Any:
        """QueryEngine 가져오기"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

        return QueryEngine(ir_doc)

    def _execute_query(self, query: Any, engine: Any) -> Any:
        """쿼리 실행"""
        return engine.execute_any_path(query)


class IRAnalyzerMixin:
    """IR 분석을 위한 Mixin"""

    def _analyze_file(self, file_path: str, ir_analyzer: Any) -> Any:
        """파일 IR 분석"""
        return ir_analyzer.analyze(file_path)

    def _get_symbols(self, ir_doc: Any) -> list[Any]:
        """IR에서 심볼 추출"""
        if hasattr(ir_doc, "symbols"):
            return ir_doc.symbols
        if hasattr(ir_doc, "get_symbols"):
            return ir_doc.get_symbols()
        return []
