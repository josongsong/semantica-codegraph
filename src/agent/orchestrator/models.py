"""Orchestrator 데이터 모델

실행 결과 및 컨텍스트 정의
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.agent.router.models import Intent


class ExecutionStatus(str, Enum):
    """실행 상태"""

    PENDING = "pending"
    ROUTING = "routing"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # 부분 성공


@dataclass
class ExecutionContext:
    """실행 컨텍스트 (전체 파이프라인)

    사용자 요청부터 최종 결과까지의 모든 컨텍스트 정보
    """

    user_request: str
    repo_id: str
    session_id: str = field(default_factory=lambda: f"session_{datetime.now().timestamp()}")
    user_id: str | None = None

    # 실행 옵션
    enable_streaming: bool = False
    max_iterations: int = 3
    budget_tokens: int = 100000
    timeout_seconds: float = 300.0

    # 추가 컨텍스트
    additional_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "user_request": self.user_request,
            "repo_id": self.repo_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            **self.additional_context,
        }


@dataclass
class AgentResult:
    """최종 실행 결과

    Agent 실행의 모든 결과 정보 포함
    """

    # 기본 정보
    intent: Intent
    confidence: float
    status: ExecutionStatus

    # 실행 결과
    result: Any  # 생성된 코드, 답변 등
    tasks_completed: list[str] = field(default_factory=list)

    # 메타데이터
    metadata: dict[str, Any] = field(default_factory=dict)

    # 성능 메트릭 (Phase 1에서 실제 측정)
    execution_time_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0

    # 에러 정보 (실패 시)
    error: str | None = None
    error_details: dict[str, Any] | None = None

    def is_success(self) -> bool:
        """성공 여부"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.PARTIAL]

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "status": self.status.value,
            "result": str(self.result) if self.result else None,
            "tasks_completed": self.tasks_completed,
            "metadata": self.metadata,
            "execution_time_ms": self.execution_time_ms,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "is_success": self.is_success(),
        }


@dataclass
class OrchestratorConfig:
    """Orchestrator 설정

    실행 동작 제어
    """

    # 재시도
    max_retries: int = 3
    retry_delay_seconds: float = 1.0

    # Fallback
    enable_fallback: bool = True
    fallback_to_simple_mode: bool = True

    # Phase 설정
    enable_full_workflow: bool = False  # Phase 0: False, Phase 1: True

    # 관찰성
    enable_tracing: bool = True
    enable_metrics: bool = True

    # Low confidence 처리
    ask_user_on_low_confidence: bool = False  # Phase 0: False, Phase 1: True
