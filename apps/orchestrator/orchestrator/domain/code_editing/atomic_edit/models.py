"""
Atomic Edit Domain Models (L11 SOTA)

순수 비즈니스 로직 - 외부 의존성 없음 (Pure Python)

책임:
- Multi-file atomic edit 모델 정의
- 트랜잭션 상태 관리
- 충돌 감지 모델
- Rollback 정보 모델

DRY 원칙:
- Hash 계산: utils.hash_utils 사용
- Validation: utils.validators 사용
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from apps.orchestrator.orchestrator.domain.code_editing.utils.hash_utils import (
    compute_content_hash,
    verify_content_hash,
)
from apps.orchestrator.orchestrator.domain.code_editing.utils.validators import Validator


class IsolationLevel(str, Enum):
    """
    트랜잭션 격리 수준

    READ_UNCOMMITTED: 가장 약함 (Dirty Read 허용)
    READ_COMMITTED: Committed만 읽기
    SERIALIZABLE: 가장 강함 (완전 격리)
    """

    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    SERIALIZABLE = "serializable"


class TransactionState(str, Enum):
    """
    트랜잭션 상태

    PENDING: 시작 전
    LOCKED: Lock 획득됨
    APPLIED: 변경 적용됨
    COMMITTED: 커밋 완료
    ROLLED_BACK: 롤백됨
    FAILED: 실패
    """

    PENDING = "pending"
    LOCKED = "locked"
    APPLIED = "applied"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ConflictType(str, Enum):
    """
    충돌 유형

    HASH_MISMATCH: 파일 내용이 변경됨
    LOCK_HELD: 다른 에이전트가 Lock 보유
    FILE_DELETED: 파일이 삭제됨
    FILE_MOVED: 파일이 이동됨
    """

    HASH_MISMATCH = "hash_mismatch"
    LOCK_HELD = "lock_held"
    FILE_DELETED = "file_deleted"
    FILE_MOVED = "file_moved"


# Hash 길이 상수 (DRY)
HASH_LENGTH = 16


@dataclass
class FileEdit:
    """
    단일 파일 편집 정보

    Attributes:
        file_path: 파일 경로
        original_content: 원본 내용
        new_content: 새 내용
        expected_hash: 예상 해시 (충돌 감지용)
    """

    file_path: str
    original_content: str
    new_content: str
    expected_hash: str | None = None

    def __post_init__(self) -> None:
        """Runtime validation"""
        # Validation 1: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 2: original != new (변경 없으면 안 됨)
        if self.original_content == self.new_content:
            raise ValueError(f"No changes detected in {self.file_path}")

        # Auto-compute hash if not provided (DRY - utils 사용)
        if self.expected_hash is None:
            self.expected_hash = compute_content_hash(self.original_content, length=HASH_LENGTH)

    @property
    def content_hash(self) -> str:
        """현재 원본 내용의 해시 (DRY - utils 사용)"""
        return compute_content_hash(self.original_content, length=HASH_LENGTH)

    def verify_hash(self, actual_content: str) -> bool:
        """해시 검증 (DRY - utils 사용)"""
        return verify_content_hash(actual_content, self.expected_hash or "")


@dataclass
class ConflictInfo:
    """
    충돌 정보

    Attributes:
        file_path: 충돌 파일 경로
        conflict_type: 충돌 유형
        expected_hash: 예상 해시
        actual_hash: 실제 해시
        locked_by: Lock 보유자 (해당 시)
        message: 충돌 메시지
    """

    file_path: str
    conflict_type: ConflictType
    expected_hash: str | None = None
    actual_hash: str | None = None
    locked_by: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        """Runtime validation"""
        # Validation 1: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 2: conflict_type 타입 체크
        Validator.type_check(self.conflict_type, ConflictType, "conflict_type")

        # Validation 3: HASH_MISMATCH면 해시 필수
        if self.conflict_type == ConflictType.HASH_MISMATCH:
            if not self.expected_hash or not self.actual_hash:
                raise ValueError("expected_hash and actual_hash required for HASH_MISMATCH")

        # Validation 4: LOCK_HELD면 locked_by 필수
        if self.conflict_type == ConflictType.LOCK_HELD:
            Validator.non_empty_string(self.locked_by, "locked_by")

    @property
    def is_resolvable(self) -> bool:
        """자동 해결 가능 여부"""
        # HASH_MISMATCH는 merge로 해결 가능할 수 있음
        # LOCK_HELD는 대기 후 재시도 가능
        return self.conflict_type in (ConflictType.HASH_MISMATCH, ConflictType.LOCK_HELD)


@dataclass
class AtomicEditRequest:
    """
    Atomic Edit 요청

    Attributes:
        edits: 파일 편집 리스트
        isolation_level: 격리 수준
        dry_run: 미리보기 모드
        timeout_seconds: 타임아웃 (초)
        agent_id: 에이전트 ID (multi-agent 환경)
    """

    edits: list[FileEdit]
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    dry_run: bool = False
    timeout_seconds: float = 30.0
    agent_id: str = "default"

    def __post_init__(self) -> None:
        """Runtime validation"""
        # Validation 1: edits 비어있으면 안 됨
        Validator.non_empty_list(self.edits, "edits")

        # Validation 2: timeout_seconds
        Validator.positive_number(self.timeout_seconds, "timeout_seconds")

        # Validation 3: agent_id
        Validator.non_empty_string(self.agent_id, "agent_id")

        # Validation 4: 중복 파일 체크
        file_paths = [edit.file_path for edit in self.edits]
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("Duplicate file paths in edits")

    @property
    def file_count(self) -> int:
        """편집할 파일 수"""
        return len(self.edits)

    @property
    def is_multi_file(self) -> bool:
        """다중 파일 편집 여부"""
        return len(self.edits) > 1


@dataclass
class RollbackInfo:
    """
    Rollback 정보

    Attributes:
        rollback_id: Rollback ID
        original_state: 원본 상태 스냅샷
        timestamp: 타임스탬프
        reason: Rollback 이유
    """

    rollback_id: str
    original_state: dict[str, str]  # file_path -> content
    timestamp: datetime
    reason: str

    def __post_init__(self) -> None:
        """Runtime validation"""
        # Validation 1: rollback_id
        Validator.non_empty_string(self.rollback_id, "rollback_id")

        # Validation 2: original_state 비어있으면 안 됨
        if not self.original_state:
            raise ValueError("original_state cannot be empty")

        # Validation 3: reason
        Validator.non_empty_string(self.reason, "reason")

    @property
    def file_count(self) -> int:
        """백업된 파일 수"""
        return len(self.original_state)


@dataclass
class AtomicEditResult:
    """
    Atomic Edit 결과

    Attributes:
        success: 성공 여부
        transaction_state: 최종 트랜잭션 상태
        committed_files: 커밋된 파일 목록
        conflicts: 충돌 정보 리스트
        rollback_info: Rollback 정보 (실패 시)
        execution_time_ms: 실행 시간
        errors: 에러 메시지
    """

    success: bool
    transaction_state: TransactionState
    committed_files: list[str]
    conflicts: list[ConflictInfo] = field(default_factory=list)
    rollback_info: RollbackInfo | None = None
    execution_time_ms: float = 0
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Runtime validation"""
        # Validation 1: execution_time_ms
        Validator.non_negative_number(self.execution_time_ms, "execution_time_ms")

        # Validation 2: 성공 시 COMMITTED 상태
        if self.success and self.transaction_state != TransactionState.COMMITTED:
            raise ValueError(f"success=True requires COMMITTED state, got {self.transaction_state.value}")

        # Validation 3: 실패 시 errors 필수
        if not self.success and not self.errors:
            raise ValueError("errors must be provided when success is False")

        # Validation 4: Rollback 시 rollback_info 필수
        if self.transaction_state == TransactionState.ROLLED_BACK and not self.rollback_info:
            raise ValueError("rollback_info required for ROLLED_BACK state")

    @property
    def has_conflicts(self) -> bool:
        """충돌 있는지"""
        return len(self.conflicts) > 0

    @property
    def total_files_committed(self) -> int:
        """커밋된 파일 수"""
        return len(self.committed_files)
