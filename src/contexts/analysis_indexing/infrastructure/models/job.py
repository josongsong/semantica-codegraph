"""
IndexJob models for concurrent editing support.

These models provide the foundation for:
- Job-based indexing with idempotency
- Distributed locking coordination
- Progress tracking and recovery
- Conflict detection and resolution
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TriggerType(Enum):
    """인덱싱 트리거 유형"""

    GIT_COMMIT = "git_commit"
    FS_EVENT = "fs_event"
    MANUAL = "manual"


class JobStatus(Enum):
    """Job 상태"""

    QUEUED = "queued"  # 큐에 대기 중
    ACQUIRING_LOCK = "acquiring_lock"  # 락 획득 시도 중
    LOCK_FAILED = "lock_failed"  # 락 획득 실패
    RUNNING = "running"  # 실행 중
    COMPLETED = "completed"  # 완료
    FAILED = "failed"  # 실패
    DEDUPED = "deduped"  # 중복 제거됨 (다른 job과 병합)
    SUPERSEDED = "superseded"  # 더 최신 job에 의해 대체됨
    CANCELLED = "cancelled"  # 취소됨


class IndexJobCheckpoint(Enum):
    """Job 실행 단계 체크포인트"""

    STARTED = "started"
    CHANGED_FILES_COMPUTED = "changed_files_computed"
    PARSING_COMPLETED = "parsing_completed"
    IR_BUILD_COMPLETED = "ir_build_completed"
    CHUNKS_STORED = "chunks_stored"
    INDEXES_UPDATED = "indexes_updated"
    COMPLETED = "completed"


@dataclass
class IndexJob:
    """
    인덱싱 작업 단위.

    이 모델은 동시편집 대응을 위한 핵심 추상화입니다:
    - 동일 (repo_id, snapshot_id)에 대해 단일 writer 보장
    - Job 단위 재시도 및 체크포인트
    - 분산 환경에서 상태 추적
    """

    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    repo_id: str = ""
    snapshot_id: str = ""

    # Scope
    scope_paths: list[str] | None = None  # None = 전체 레포

    # Trigger
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_metadata: dict[str, Any] = field(default_factory=dict)

    # Status
    status: JobStatus = JobStatus.QUEUED
    status_reason: str | None = None

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now())
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # Results
    changed_files_count: int = 0
    indexed_chunks_count: int = 0
    errors_count: int = 0

    # Retry
    retry_count: int = 0
    max_retries: int = 3
    last_error: str | None = None

    # Concurrency
    lock_acquired_by: str | None = None  # instance_id
    lock_expires_at: datetime | None = None

    def can_retry(self) -> bool:
        """재시도 가능 여부 확인"""
        return self.status == JobStatus.FAILED and self.retry_count < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (DB 저장용)"""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "snapshot_id": self.snapshot_id,
            "scope_paths": self.scope_paths,
            "trigger_type": self.trigger_type.value,
            "trigger_metadata": self.trigger_metadata,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "changed_files_count": self.changed_files_count,
            "indexed_chunks_count": self.indexed_chunks_count,
            "errors_count": self.errors_count,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "lock_acquired_by": self.lock_acquired_by,
            "lock_expires_at": self.lock_expires_at.isoformat() if self.lock_expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexJob":
        """딕셔너리에서 복원 (DB 로드용)"""
        return cls(
            id=data["id"],
            repo_id=data["repo_id"],
            snapshot_id=data["snapshot_id"],
            scope_paths=data.get("scope_paths"),
            trigger_type=TriggerType(data["trigger_type"]),
            trigger_metadata=data.get("trigger_metadata", {}),
            status=JobStatus(data["status"]),
            status_reason=data.get("status_reason"),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            changed_files_count=data.get("changed_files_count", 0),
            indexed_chunks_count=data.get("indexed_chunks_count", 0),
            errors_count=data.get("errors_count", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            last_error=data.get("last_error"),
            lock_acquired_by=data.get("lock_acquired_by"),
            lock_expires_at=(datetime.fromisoformat(data["lock_expires_at"]) if data.get("lock_expires_at") else None),
        )


@dataclass
class JobProgress:
    """
    Job 진행 상태 추적.

    체크포인트 기반 재시도를 위한 상태 정보.
    협력적 취소(cooperative cancellation)를 지원하며,
    실시간으로 진행상태를 업데이트하여 언제든 중단/재개 가능.
    """

    job_id: str
    current_checkpoint: IndexJobCheckpoint = IndexJobCheckpoint.STARTED
    completed_files: list[str] = field(default_factory=list)
    failed_files: dict[str, str] = field(default_factory=dict)  # file_path → error_message
    created_at: datetime = field(default_factory=datetime.now)

    # 협력적 취소 지원 필드
    processing_file: str | None = None  # 현재 처리 중인 파일
    total_files: int = 0  # 전체 파일 수 (진행률 계산용)
    paused_at: datetime | None = None  # 일시중지 시점

    @property
    def progress_percent(self) -> float:
        """진행률 (0.0 ~ 100.0)."""
        if self.total_files == 0:
            return 0.0
        return (len(self.completed_files) / self.total_files) * 100

    @property
    def is_paused(self) -> bool:
        """일시중지 상태인지 확인."""
        return self.paused_at is not None

    def pause(self) -> None:
        """일시중지 상태로 전환."""
        self.paused_at = datetime.now()
        self.processing_file = None

    def resume(self) -> None:
        """일시중지 해제."""
        self.paused_at = None

    def mark_file_completed(self, file_path: str):
        """파일 처리 완료 기록"""
        if file_path not in self.completed_files:
            self.completed_files.append(file_path)

    def mark_file_failed(self, file_path: str, error: str):
        """파일 처리 실패 기록"""
        self.failed_files[file_path] = error

    def can_skip_file(self, file_path: str) -> bool:
        """이미 처리된 파일인지 확인"""
        return file_path in self.completed_files

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "job_id": self.job_id,
            "checkpoint": self.current_checkpoint.value,
            "completed_files": self.completed_files,
            "failed_files": self.failed_files,
            "created_at": self.created_at.isoformat(),
            "processing_file": self.processing_file,
            "total_files": self.total_files,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobProgress":
        """딕셔너리에서 복원"""
        return cls(
            job_id=data["job_id"],
            current_checkpoint=IndexJobCheckpoint(data["checkpoint"]),
            completed_files=data.get("completed_files", []),
            failed_files=data.get("failed_files", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            processing_file=data.get("processing_file"),
            total_files=data.get("total_files", 0),
            paused_at=datetime.fromisoformat(data["paused_at"]) if data.get("paused_at") else None,
        )
