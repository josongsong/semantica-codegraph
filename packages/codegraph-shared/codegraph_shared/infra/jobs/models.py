"""
Job Queue 도메인 모델.

SemanticaTask와 호환 가능한 모델 정의.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobState(str, Enum):
    """
    Job 상태.

    SemanticaTask 호환:
    - QUEUED, RUNNING, DONE, FAILED, SUPERSEDED
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class JobPriority(int, Enum):
    """Job 우선순위 상수."""

    CRITICAL = 100
    HIGH = 50
    NORMAL = 0
    LOW = -50


@dataclass
class Job:
    """
    범용 Job 모델.

    SemanticaTask 스펙 호환:
    - job_type: 작업 유형 (예: "INDEX_FILE", "EMBED_CHUNK")
    - queue: 큐 이름 (예: "code_intel", "default")
    - subject_key: 중복 방지 키 (예: "repo123::main.py")
    - payload: 작업 데이터 (JSON 직렬화 가능)
    - priority: 우선순위 (정수)
    """

    job_id: str
    job_type: str
    queue: str
    subject_key: str
    payload: dict[str, Any]
    state: JobState = JobState.QUEUED
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        """JSON-RPC 응답용."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "queue": self.queue,
            "subject_key": self.subject_key,
            "state": self.state.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
        }
