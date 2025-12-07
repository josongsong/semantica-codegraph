"""
Indexing Session Aggregate Root

인덱싱 세션 애그리게이트 루트

비즈니스 불변식:
- 세션은 한 번 시작되면 완료 또는 실패로 끝나야 함
- 파일은 중복 인덱싱되지 않음
- 실패한 파일은 재시도 가능
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from ..entities.indexed_file import IndexedFile
from ..events.base import DomainEvent
from ..events.file_indexed import FileIndexed, FileIndexingFailed
from ..events.indexing_completed import IndexingCompleted, IndexingFailed
from ..value_objects.file_path import FilePath
from ..value_objects.snapshot_id import SnapshotId


class SessionStatus(str, Enum):
    """세션 상태"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexingSession:
    """인덱싱 세션 애그리게이트 루트"""

    session_id: str
    repo_id: str
    snapshot_id: SnapshotId
    mode: str
    status: SessionStatus = SessionStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    indexed_files: dict[str, IndexedFile] = field(default_factory=dict)
    _domain_events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def start(self) -> None:
        """
        세션 시작

        비즈니스 규칙:
        - PENDING 상태에서만 시작 가능
        """
        if self.status != SessionStatus.PENDING:
            raise ValueError(f"Cannot start session in {self.status} state")

        self.status = SessionStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC)

    def index_file(
        self,
        file_path: FilePath,
        file_hash,
        language: str,
        ir_nodes_count: int = 0,
        graph_nodes_count: int = 0,
        chunks_count: int = 0,
    ) -> None:
        """
        파일 인덱싱 성공 기록

        비즈니스 규칙:
        - IN_PROGRESS 상태에서만 파일 인덱싱 가능
        - 같은 파일은 한 번만 인덱싱
        """
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError(f"Cannot index file in {self.status} state")

        file_key = str(file_path)

        indexed_file = IndexedFile(
            file_path=file_path,
            file_hash=file_hash,
            language=language,
            ir_nodes_count=ir_nodes_count,
            graph_nodes_count=graph_nodes_count,
            chunks_count=chunks_count,
        )

        self.indexed_files[file_key] = indexed_file

        # Domain Event 발행
        self._domain_events.append(
            FileIndexed(
                aggregate_id=self.session_id,
                file_path=str(file_path),
                ir_nodes_count=ir_nodes_count,
                graph_nodes_count=graph_nodes_count,
                chunks_count=chunks_count,
                language=language,
            )
        )

    def mark_file_failed(self, file_path: FilePath, error: str) -> None:
        """
        파일 인덱싱 실패 기록

        비즈니스 규칙:
        - IN_PROGRESS 상태에서만 실패 기록 가능
        """
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError(f"Cannot mark file failed in {self.status} state")

        file_key = str(file_path)

        # 실패 파일도 기록 (재시도 추적용)
        if file_key in self.indexed_files:
            self.indexed_files[file_key].mark_failed(error)
        else:
            from ..value_objects.file_hash import FileHash

            indexed_file = IndexedFile(
                file_path=file_path,
                file_hash=FileHash(value=""),
                language="unknown",
            )
            indexed_file.mark_failed(error)
            self.indexed_files[file_key] = indexed_file

        # Domain Event 발행
        self._domain_events.append(
            FileIndexingFailed(
                aggregate_id=self.session_id,
                file_path=str(file_path),
                error=error,
            )
        )

    def complete(self) -> None:
        """
        세션 완료

        비즈니스 규칙:
        - IN_PROGRESS 상태에서만 완료 가능
        """
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError(f"Cannot complete session in {self.status} state")

        self.status = SessionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

        # Domain Event 발행
        self._domain_events.append(
            IndexingCompleted(
                aggregate_id=self.session_id,
                repo_id=self.repo_id,
                snapshot_id=str(self.snapshot_id),
                total_files=self.total_files,
                success_files=self.success_files,
                failed_files=self.failed_files,
                mode=self.mode,
            )
        )

    def fail(self, error: str) -> None:
        """
        세션 실패

        비즈니스 규칙:
        - IN_PROGRESS 상태에서만 실패 가능
        """
        if self.status != SessionStatus.IN_PROGRESS:
            raise ValueError(f"Cannot fail session in {self.status} state")

        self.status = SessionStatus.FAILED
        self.completed_at = datetime.now(UTC)

        # Domain Event 발행
        self._domain_events.append(
            IndexingFailed(
                aggregate_id=self.session_id,
                repo_id=self.repo_id,
                snapshot_id=str(self.snapshot_id),
                error=error,
                mode=self.mode,
            )
        )

    @property
    def total_files(self) -> int:
        """전체 파일 수"""
        return len(self.indexed_files)

    @property
    def success_files(self) -> int:
        """성공 파일 수"""
        return sum(1 for f in self.indexed_files.values() if f.is_success)

    @property
    def failed_files(self) -> int:
        """실패 파일 수"""
        return sum(1 for f in self.indexed_files.values() if not f.is_success)

    def collect_domain_events(self) -> list[DomainEvent]:
        """도메인 이벤트 수집 (한 번만 수집됨)"""
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
