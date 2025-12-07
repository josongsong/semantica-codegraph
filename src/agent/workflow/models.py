"""Workflow 데이터 모델

ADR-003: Graph Workflow Engine
Analyze → Plan → Generate → Critic → Test → Self-heal
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStep(Enum):
    """Workflow 단계"""

    ANALYZE = "analyze"
    PLAN = "plan"
    GENERATE = "generate"
    CRITIC = "critic"
    TEST = "test"
    SELF_HEAL = "self_heal"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowExitReason(Enum):
    """Workflow 종료 이유"""

    SUCCESS = "success"
    MAX_ITERATIONS = "max_iterations"
    CONFIDENCE_LOW = "confidence_low"
    ERROR = "error"
    USER_CANCELLED = "user_cancelled"


@dataclass
class StepResult:
    """단일 Step 실행 결과"""

    step: WorkflowStep
    success: bool
    output: Any
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """검증: success=False이면 error 필요"""
        if not self.success and not self.error:
            self.error = "Unknown error"


@dataclass
class WorkflowState:
    """Workflow 전체 상태"""

    current_step: WorkflowStep
    iteration: int
    context: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    step_history: list[StepResult] = field(default_factory=list)
    exit_reason: WorkflowExitReason | None = None

    def add_step_result(self, step_result: StepResult) -> None:
        """Step 결과 기록"""
        self.step_history.append(step_result)

    def get_last_step_result(self) -> StepResult | None:
        """마지막 Step 결과 조회"""
        return self.step_history[-1] if self.step_history else None

    def is_terminal(self) -> bool:
        """종료 상태 여부"""
        return self.current_step in [WorkflowStep.COMPLETED, WorkflowStep.FAILED]
