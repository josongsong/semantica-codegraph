"""
Plan Domain Models (RFC-041)

Core domain models for Plan-Based Tool Orchestration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlanCategory(str, Enum):
    """Plan 카테고리"""

    UNDERSTAND = "understand"  # 코드 이해
    TRACE = "trace"  # 실행/데이터 추적
    ANALYZE = "analyze"  # 분석 (보안, 성능 등)
    IMPACT = "impact"  # 변경 영향
    GENERATE = "generate"  # 코드 생성/수정
    VERIFY = "verify"  # 검증


class StepStatus(str, Enum):
    """Step 실행 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"  # cache hit 또는 조건 미충족
    FAILED = "failed"


@dataclass
class StepConfig:
    """
    Step 설정 (AutoTool이 조정 가능한 파라미터)
    """

    # 기본 파라미터
    depth: int = 3
    max_results: int = 100
    timeout_ms: int = 30000

    # 조건부 실행
    skip_if_cached: bool = True
    skip_if_empty_input: bool = True

    # Fallback
    fallback_tool: str | None = None
    fallback_on_timeout: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "max_results": self.max_results,
            "timeout_ms": self.timeout_ms,
            "skip_if_cached": self.skip_if_cached,
            "skip_if_empty_input": self.skip_if_empty_input,
            "fallback_tool": self.fallback_tool,
            "fallback_on_timeout": self.fallback_on_timeout,
        }


@dataclass
class PlanStep:
    """
    Analysis Plan의 단일 Step

    하나의 Step은 하나의 의미적 역할만 가짐.
    내부적으로 하나 이상의 Tool을 사용할 수 있으나 외부에 노출되지 않음.
    """

    # Step 정의
    name: str  # "resolve_type_hierarchy"
    description: str  # "타입 계층 구조 분석"
    tool: str  # 바인딩된 Tool 이름 ("find_type_hierarchy")

    # 설정
    config: StepConfig = field(default_factory=StepConfig)

    # 의존성 (이전 Step 결과 필요 여부)
    depends_on: list[str] = field(default_factory=list)

    # Step 순서 (변경 불가)
    order: int = 0

    def __post_init__(self):
        if not self.name:
            raise ValueError("Step name cannot be empty")
        if not self.tool:
            raise ValueError(f"Step '{self.name}' must have a bound tool")


@dataclass
class StepResult:
    """Step 실행 결과"""

    step_name: str
    status: StepStatus
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    # 메타데이터
    tool_used: str | None = None
    was_cached: bool = False
    was_fallback: bool = False

    @property
    def is_success(self) -> bool:
        return self.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)


@dataclass
class AnalysisPlan:
    """
    Analysis Plan 정의

    특정 목적을 위한 결정론적 분석 시퀀스.
    Step 단위로 구성되며, 반드시 버전 관리됨.

    제약 조건:
    - Step 순서 변경 불가
    - Step 생략은 시스템 규칙으로만 가능
    - LLM은 Step 구성에 개입 불가
    """

    # Plan 식별
    name: str  # "plan_analyze_security"
    version: str  # "v1"
    description: str  # "보안 취약점 분석"

    # 카테고리
    category: PlanCategory

    # Step 시퀀스 (순서 고정)
    steps: list[PlanStep] = field(default_factory=list)

    # LLM 노출 설정
    llm_description: str = ""  # LLM에게 보여줄 설명
    llm_examples: list[str] = field(default_factory=list)  # 사용 예시

    # 메타데이터
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False
    successor: str | None = None  # deprecated 시 대체 Plan

    def __post_init__(self):
        if not self.name:
            raise ValueError("Plan name cannot be empty")
        if not self.version:
            raise ValueError("Plan version cannot be empty")
        if not self.steps:
            raise ValueError(f"Plan '{self.name}' must have at least one step")

        # Step 순서 자동 할당
        for i, step in enumerate(self.steps):
            step.order = i

    @property
    def full_name(self) -> str:
        """Full versioned name: plan_analyze_security:v1"""
        return f"{self.name}:{self.version}"

    def get_step(self, name: str) -> PlanStep | None:
        """이름으로 Step 찾기"""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def to_llm_tool(self) -> dict[str, Any]:
        """
        LLM Tool 포맷으로 변환 (OpenAI/Anthropic 호환)

        LLM은 이 포맷만 봄. 내부 Step 구조는 노출되지 않음.
        """
        return {
            "name": self.name,
            "description": self.llm_description or self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "분석 대상 (파일 경로, 함수명, 심볼 등)",
                    },
                    "context": {
                        "type": "string",
                        "description": "추가 컨텍스트 (선택)",
                    },
                },
                "required": ["target"],
            },
        }


@dataclass
class PlanResult:
    """Plan 실행 결과"""

    plan_name: str
    plan_version: str
    success: bool

    # Step 결과들
    step_results: list[StepResult] = field(default_factory=list)

    # 최종 데이터 (LLM 해석용)
    final_data: Any = None
    summary: str = ""

    # 메타데이터
    total_execution_time_ms: float = 0.0
    steps_completed: int = 0
    steps_skipped: int = 0
    steps_failed: int = 0

    def __post_init__(self):
        # 통계 계산
        for result in self.step_results:
            if result.status == StepStatus.COMPLETED:
                self.steps_completed += 1
            elif result.status == StepStatus.SKIPPED:
                self.steps_skipped += 1
            elif result.status == StepStatus.FAILED:
                self.steps_failed += 1

    @property
    def is_success(self) -> bool:
        return self.success and self.steps_failed == 0

    def get_step_result(self, step_name: str) -> StepResult | None:
        """이름으로 Step 결과 찾기"""
        for result in self.step_results:
            if result.step_name == step_name:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환 (직렬화용)"""
        return {
            "plan_name": self.plan_name,
            "plan_version": self.plan_version,
            "success": self.success,
            "step_results": [
                {
                    "step_name": r.step_name,
                    "status": r.status.value,
                    "data": r.data,
                    "error": r.error,
                    "execution_time_ms": r.execution_time_ms,
                }
                for r in self.step_results
            ],
            "final_data": self.final_data,
            "summary": self.summary,
            "total_execution_time_ms": self.total_execution_time_ms,
            "steps_completed": self.steps_completed,
            "steps_skipped": self.steps_skipped,
            "steps_failed": self.steps_failed,
        }
