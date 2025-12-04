"""
Agent Automation Domain Models

에이전트 자동화 도메인의 핵심 모델
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AgentMode(str, Enum):
    """에이전트 모드"""

    DEBUG = "debug"
    REFACTOR = "refactor"
    IMPLEMENT = "implement"
    TEST = "test"
    REVIEW = "review"


class SessionStatus(str, Enum):
    """세션 상태"""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSession:
    """에이전트 세션"""

    session_id: str
    repo_id: str
    mode: AgentMode
    prompt: str
    status: SessionStatus
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


@dataclass
class AgentStep:
    """에이전트 실행 단계"""

    step_number: int
    description: str
    completed: bool = False


@dataclass
class AgentResult:
    """에이전트 실행 결과"""

    session_id: str
    success: bool
    steps: list[AgentStep] = field(default_factory=list)
    diff_summary: str = ""
    error_message: str | None = None
