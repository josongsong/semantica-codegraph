"""
Base interfaces for Code Foundation Tools

SOTA Reference:
- Anthropic tool_choice pattern
- OpenAI function calling schema
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class ToolCategory(str, Enum):
    """도구 카테고리 (Intent에 매핑)"""

    CODE_UNDERSTANDING = "code_understanding"
    IMPACT_ANALYSIS = "impact_analysis"
    BUG_DETECTION = "bug_detection"
    SECURITY_ANALYSIS = "security_analysis"
    REFACTORING = "refactoring"
    PERFORMANCE = "performance"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    TYPE_ANALYSIS = "type_analysis"
    TEST_ANALYSIS = "test_analysis"
    DOCUMENTATION = "documentation"


ExecutionMode = Literal["auto", "any", "specific", "none"]


@dataclass
class ToolMetadata:
    """도구 메타데이터 (OpenAI/Anthropic 호환)"""

    name: str
    description: str
    category: ToolCategory

    # JSON Schema (OpenAI function calling 호환)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    # 메타 정보
    complexity: int = 1  # 1-5: 실행 비용
    dependencies: list[str] = field(default_factory=list)  # 필요한 다른 도구들
    tags: list[str] = field(default_factory=list)

    # 버전 & 안정성
    version: str = "1.0.0"
    stability: Literal["stable", "beta", "experimental"] = "stable"

    def to_openai_function(self) -> dict[str, Any]:
        """OpenAI function calling 포맷으로 변환"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Anthropic tool use 포맷으로 변환"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolResult:
    """도구 실행 결과"""

    success: bool
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    # 성능 메트릭
    execution_time_ms: float = 0.0
    confidence: float = 1.0  # 0-1: 결과 신뢰도

    # 에러 정보
    error: str | None = None
    error_type: str | None = None

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.success and self.error is None

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata,
            "execution_time_ms": self.execution_time_ms,
            "confidence": self.confidence,
            "error": self.error,
            "error_type": self.error_type,
        }


class CodeFoundationTool(ABC):
    """
    Code Foundation 도구 베이스 클래스

    설계 원칙:
    1. 단일 책임: 하나의 도구는 하나의 분석만
    2. 명시적 의존성: 필요한 컴포넌트 명확히 주입
    3. 실패 격리: 한 도구 실패가 전체에 영향 X
    """

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """도구 메타데이터"""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        도구 실행

        Args:
            **kwargs: 도구별 파라미터

        Returns:
            ToolResult: 실행 결과
        """
        pass

    def validate_input(self, **kwargs) -> bool:
        """
        입력 검증

        JSON Schema 기반 검증 + 추가 비즈니스 로직
        """
        try:
            import jsonschema

            # JSON Schema 검증
            jsonschema.validate(instance=kwargs, schema=self.metadata.input_schema)

            # Required 필드 체크
            required = self.metadata.input_schema.get("required", [])
            for field in required:
                if field not in kwargs:
                    raise ValueError(f"Missing required field: {field}")
                if kwargs[field] is None:
                    raise ValueError(f"Required field '{field}' cannot be None")

            return True

        except ImportError:
            # jsonschema 없으면 기본 검증
            logger.warning("jsonschema not installed, using basic validation")
            required = self.metadata.input_schema.get("required", [])
            for field in required:
                if field not in kwargs or kwargs[field] is None:
                    raise ValueError(f"Required field '{field}' missing or None")
            return True

        except jsonschema.ValidationError as e:
            raise ValueError(f"Input validation failed: {e.message}")

    def _safe_execute(self, **kwargs) -> ToolResult:
        """
        안전한 실행 (에러 처리 포함)
        """
        start_time = time.time()

        try:
            # 입력 검증
            if not self.validate_input(**kwargs):
                return ToolResult(
                    success=False,
                    data=None,
                    error="Input validation failed",
                    error_type="ValidationError",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    confidence=0.0,
                )

            # 실행
            result = self.execute(**kwargs)
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=str(e),
                error_type=type(e).__name__,
                execution_time_ms=(time.time() - start_time) * 1000,
                confidence=0.0,
            )

    def __call__(self, **kwargs) -> ToolResult:
        """Callable로 사용 가능"""
        return self._safe_execute(**kwargs)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.metadata.name}')>"
