"""
Repository Integration Tests

리포지토리 통합 테스트
"""

import pytest

from src.contexts.analysis_indexing.domain.aggregates.indexing_session import IndexingSession
from src.contexts.analysis_indexing.domain.value_objects.snapshot_id import SnapshotId
from src.contexts.analysis_indexing.infrastructure.repositories.in_memory_session_repository import (
    InMemorySessionRepository,
)


@pytest.mark.asyncio
class TestInMemorySessionRepository:
    """InMemory 세션 리포지토리 통합 테스트"""

    async def test_save_and_find(self):
        """저장 및 조회"""
        repo = InMemorySessionRepository()

        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )

        await repo.save(session)

        found = await repo.find_by_id("test-1")

        assert found is not None
        assert found.session_id == "test-1"
        assert found.repo_id == "repo-1"

    async def test_find_by_repo(self):
        """리포지토리 ID로 조회"""
        repo = InMemorySessionRepository()

        session1 = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )
        session2 = IndexingSession(
            session_id="test-2",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-2"),
            mode="incremental",
        )
        session3 = IndexingSession(
            session_id="test-3",
            repo_id="repo-2",
            snapshot_id=SnapshotId.from_string("snap-3"),
            mode="full",
        )

        await repo.save(session1)
        await repo.save(session2)
        await repo.save(session3)

        sessions = await repo.find_by_repo("repo-1")

        assert len(sessions) == 2
        assert all(s.repo_id == "repo-1" for s in sessions)

    async def test_delete(self):
        """삭제"""
        repo = InMemorySessionRepository()

        session = IndexingSession(
            session_id="test-1",
            repo_id="repo-1",
            snapshot_id=SnapshotId.from_string("snap-1"),
            mode="full",
        )

        await repo.save(session)
        await repo.delete("test-1")

        found = await repo.find_by_id("test-1")

        assert found is None
