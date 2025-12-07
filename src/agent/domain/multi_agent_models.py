"""
Multi-Agent Collaboration Models (SOTA급)

여러 Agent 동시 실행 및 충돌 관리를 위한 Domain Model.

핵심 기능:
1. Agent Session 추적
2. Soft Lock (편집 중 추적)
3. Conflict 감지 및 해결
4. Hash Drift 감지
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Agent 타입"""

    USER = "user"  # 사용자 직접 편집
    AI = "ai"  # AI Agent
    SYSTEM = "system"  # 시스템 Agent


class AgentStateType(str, Enum):
    """Agent 상태"""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"  # Lock 대기
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"  # 충돌 발생


class LockType(str, Enum):
    """Lock 타입"""

    READ = "read"  # 읽기 전용
    WRITE = "write"  # 쓰기 (편집)


class ConflictType(str, Enum):
    """충돌 타입"""

    CONCURRENT_EDIT = "concurrent_edit"  # 동시 편집
    HASH_DRIFT = "hash_drift"  # 파일 변경 감지
    LOCK_TIMEOUT = "lock_timeout"  # Lock 타임아웃


class MergeStrategy(str, Enum):
    """Merge 전략"""

    AUTO = "auto"  # 자동 merge
    MANUAL = "manual"  # 수동 해결
    ABORT = "abort"  # 중단
    ACCEPT_OURS = "accept_ours"  # 우리 것 채택
    ACCEPT_THEIRS = "accept_theirs"  # 상대 것 채택


@dataclass
class AgentSession:
    """
    Agent 세션.

    여러 Agent가 동시에 실행될 때 각 Agent의 상태를 추적합니다.
    """

    session_id: str
    agent_id: str
    agent_type: AgentType
    task_id: str | None = None
    locked_files: set[str] = field(default_factory=set)
    state: AgentStateType = AgentStateType.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """활성 상태인지 확인"""
        return self.state in [AgentStateType.RUNNING, AgentStateType.WAITING]

    def is_editing(self, file_path: str) -> bool:
        """특정 파일을 편집 중인지 확인"""
        return file_path in self.locked_files

    def add_lock(self, file_path: str) -> None:
        """Lock 추가"""
        self.locked_files.add(file_path)
        self.last_active = datetime.now()
        logger.debug(f"Agent {self.agent_id} locked {file_path}")
        logger.info(f"Lock added: {self.agent_id} → {file_path}")

    def remove_lock(self, file_path: str) -> None:
        """Lock 제거"""
        self.locked_files.discard(file_path)
        self.last_active = datetime.now()
        logger.debug(f"Agent {self.agent_id} released {file_path}")

    def update_state(self, new_state: AgentStateType) -> None:
        """상태 업데이트"""
        old_state = self.state
        self.state = new_state
        self.last_active = datetime.now()
        logger.info(f"Agent {self.agent_id} state: {old_state} → {new_state}")


@dataclass
class SoftLock:
    """
    Soft Lock (편집 중 추적).

    Hard Lock과 달리 다른 Agent의 접근을 완전히 막지 않고,
    충돌 가능성만 알려줍니다.
    """

    file_path: str
    agent_id: str
    acquired_at: datetime = field(default_factory=datetime.now)
    file_hash: str | None = None  # Lock 시점 파일 해시
    lock_type: LockType = LockType.WRITE
    ttl_seconds: int = 1800  # 30분
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """만료 여부 확인"""
        elapsed = (datetime.now() - self.acquired_at).total_seconds()
        return elapsed > self.ttl_seconds

    def is_write_lock(self) -> bool:
        """쓰기 Lock인지 확인"""
        return self.lock_type == LockType.WRITE

    def to_dict(self) -> dict[str, Any]:
        """Redis 저장용 dict 변환"""
        return {
            "file_path": self.file_path,
            "agent_id": self.agent_id,
            "acquired_at": self.acquired_at.isoformat(),
            "file_hash": self.file_hash,
            "lock_type": self.lock_type.value,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SoftLock":
        """Redis에서 복원"""
        return cls(
            file_path=data["file_path"],
            agent_id=data["agent_id"],
            acquired_at=datetime.fromisoformat(data["acquired_at"]),
            file_hash=data.get("file_hash"),
            lock_type=LockType(data["lock_type"]),
            ttl_seconds=data.get("ttl_seconds", 1800),
        )


@dataclass
class Conflict:
    """
    충돌.

    여러 Agent가 동일 파일을 동시에 편집할 때 발생합니다.
    """

    conflict_id: str
    file_path: str
    agent_a_id: str
    agent_b_id: str
    agent_a_changes: str | None = None  # Agent A의 변경사항
    agent_b_changes: str | None = None  # Agent B의 변경사항
    base_content: str | None = None  # 충돌 시점 원본
    conflict_type: ConflictType = ConflictType.CONCURRENT_EDIT
    detected_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolution: str | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_resolved(self) -> bool:
        """해결 여부 확인"""
        return self.resolved

    def mark_resolved(self, resolution: str) -> None:
        """해결 완료 표시"""
        self.resolved = True
        self.resolution = resolution
        self.resolved_at = datetime.now()
        logger.info(f"Conflict {self.conflict_id} resolved: {resolution}")
        logger.debug(f"Resolution details: {self.file_path}, strategy={resolution}")

    def get_summary(self) -> str:
        """충돌 요약"""
        return (
            f"Conflict in {self.file_path}\n"
            f"  Agent A: {self.agent_a_id}\n"
            f"  Agent B: {self.agent_b_id}\n"
            f"  Type: {self.conflict_type.value}\n"
            f"  Detected: {self.detected_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )


@dataclass
class MergeResult:
    """
    Merge 결과.

    3-way merge 또는 수동 해결의 결과입니다.
    """

    success: bool
    merged_content: str | None = None
    conflicts: list[str] = field(default_factory=list)  # 충돌 영역 (line ranges)
    strategy: MergeStrategy = MergeStrategy.AUTO
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_conflicts(self) -> bool:
        """충돌 영역이 있는지 확인"""
        return len(self.conflicts) > 0

    def is_auto_mergeable(self) -> bool:
        """자동 merge 가능한지 확인"""
        return self.success and not self.has_conflicts()

    def get_conflict_summary(self) -> str:
        """충돌 요약"""
        if not self.has_conflicts():
            return "No conflicts"

        return f"{len(self.conflicts)} conflict region(s):\n" + "\n".join(
            f"  - {conflict}" for conflict in self.conflicts
        )


@dataclass
class LockAcquisitionResult:
    """Lock 획득 결과"""

    success: bool
    lock: SoftLock | None = None
    existing_lock: SoftLock | None = None  # 기존 Lock (충돌 시)
    conflict: Conflict | None = None
    message: str | None = None


@dataclass
class DriftDetectionResult:
    """Hash Drift 감지 결과"""

    drift_detected: bool
    file_path: str
    original_hash: str | None = None
    current_hash: str | None = None
    lock_info: SoftLock | None = None
    message: str | None = None

    def get_summary(self) -> str:
        """Drift 요약"""
        if not self.drift_detected:
            return f"No drift: {self.file_path}"

        return (
            f"Hash drift detected: {self.file_path}\n  Original: {self.original_hash}\n  Current:  {self.current_hash}"
        )
