"""CLI 도메인 모델 (타입 안정성)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    """실행 이벤트 타입."""

    EXECUTION_START = "execution_start"
    STEP_START = "step_start"
    STEP_END = "step_end"
    LLM_CALL = "llm_call"
    EXECUTION_COMPLETE = "execution_complete"
    ERROR = "error"


class StepStatus(str, Enum):
    """단계 실행 상태."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionStartData:
    """실행 시작 데이터."""

    instructions: str
    repo: str


@dataclass
class StepStartData:
    """단계 시작 데이터."""

    step: str
    message: str


@dataclass
class StepEndData:
    """단계 완료 데이터."""

    step: str
    status: StepStatus


@dataclass
class ExecutionCompleteData:
    """실행 완료 데이터."""

    status: str
    message: str
    files_changed: int


@dataclass
class ErrorData:
    """에러 데이터."""

    error: str
    error_type: str
    traceback: str | None = None


@dataclass
class ExecutionEvent:
    """실행 중 발생하는 이벤트 (타입 안전)."""

    type: EventType
    timestamp: datetime
    data: ExecutionStartData | StepStartData | StepEndData | ExecutionCompleteData | ErrorData

    @classmethod
    def execution_start(cls, instructions: str, repo: str) -> "ExecutionEvent":
        """실행 시작 이벤트 생성."""
        return cls(
            type=EventType.EXECUTION_START,
            timestamp=datetime.now(),
            data=ExecutionStartData(instructions=instructions, repo=repo),
        )

    @classmethod
    def step_start(cls, step: str, message: str) -> "ExecutionEvent":
        """단계 시작 이벤트 생성."""
        return cls(
            type=EventType.STEP_START,
            timestamp=datetime.now(),
            data=StepStartData(step=step, message=message),
        )

    @classmethod
    def step_end(cls, step: str, status: StepStatus) -> "ExecutionEvent":
        """단계 완료 이벤트 생성."""
        return cls(
            type=EventType.STEP_END,
            timestamp=datetime.now(),
            data=StepEndData(step=step, status=status),
        )

    @classmethod
    def execution_complete(cls, status: str, message: str, files_changed: int) -> "ExecutionEvent":
        """실행 완료 이벤트 생성."""
        return cls(
            type=EventType.EXECUTION_COMPLETE,
            timestamp=datetime.now(),
            data=ExecutionCompleteData(status=status, message=message, files_changed=files_changed),
        )

    @classmethod
    def error(cls, error: Exception, traceback: str | None = None) -> "ExecutionEvent":
        """에러 이벤트 생성."""
        return cls(
            type=EventType.ERROR,
            timestamp=datetime.now(),
            data=ErrorData(error=str(error), error_type=type(error).__name__, traceback=traceback),
        )
