"""
Aggregate Root Unit Tests

애그리게이트 루트 비즈니스 불변식 테스트
"""

import pytest

from codegraph_engine.analysis_indexing.domain.aggregates.indexing_session import (
    IndexingSession,
    SessionStatus,
)
from codegraph_engine.analysis_indexing.domain.value_objects.file_hash import FileHash
from codegraph_engine.analysis_indexing.domain.value_objects.file_path import FilePath
from codegraph_engine.analysis_indexing.domain.value_objects.snapshot_id import SnapshotId


class TestIndexingSession:
    """IndexingSession 애그리게이트 루트 테스트"""

    def test_create_session(self):
        """세션 생성"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )

        assert session.status == SessionStatus.PENDING
        assert session.started_at is None
        assert session.total_files == 0

    def test_start_session(self):
        """세션 시작"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )

        session.start()

        assert session.status == SessionStatus.IN_PROGRESS
        assert session.started_at is not None

    def test_cannot_start_twice(self):
        """중복 시작 불가 (비즈니스 불변식)"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )

        session.start()

        with pytest.raises(ValueError, match="Cannot start session"):
            session.start()

    def test_index_file_success(self):
        """파일 인덱싱 성공"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session.start()

        file_path = FilePath.from_string("/tmp/test.py")
        file_hash = FileHash.from_content("test")

        session.index_file(
            file_path=file_path,
            file_hash=file_hash,
            language="python",
            ir_nodes_count=10,
            graph_nodes_count=5,
            chunks_count=3,
        )

        assert session.total_files == 1
        assert session.success_files == 1
        assert session.failed_files == 0

    def test_mark_file_failed(self):
        """파일 인덱싱 실패"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session.start()

        file_path = FilePath.from_string("/tmp/test.py")

        session.mark_file_failed(file_path, "Parse error")

        assert session.total_files == 1
        assert session.success_files == 0
        assert session.failed_files == 1

    def test_complete_session(self):
        """세션 완료"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session.start()

        session.complete()

        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None

    def test_domain_events_collected(self):
        """도메인 이벤트 수집"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session.start()

        file_path = FilePath.from_string("/tmp/test.py")
        file_hash = FileHash.from_content("test")

        session.index_file(
            file_path=file_path,
            file_hash=file_hash,
            language="python",
        )

        session.complete()

        events = session.collect_domain_events()

        assert len(events) == 2  # FileIndexed + IndexingCompleted
        assert events[0].__class__.__name__ == "FileIndexed"
        assert events[1].__class__.__name__ == "IndexingCompleted"

    def test_domain_events_cleared_after_collection(self):
        """도메인 이벤트 수집 후 클리어"""
        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session.start()
        session.complete()

        events1 = session.collect_domain_events()
        events2 = session.collect_domain_events()

        assert len(events1) == 1
        assert len(events2) == 0  # 한 번만 수집됨
