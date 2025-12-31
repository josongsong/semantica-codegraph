"""
Idempotency Manager for Incremental Indexing

중복 인덱싱 방지를 위한 Idempotency 키 관리.
(repo_id, snapshot_id, head_sha, file_path) 기준.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class IndexingRecord:
    """인덱싱 이력 레코드."""

    repo_id: str
    snapshot_id: str
    file_path: str
    head_sha: str  # Git HEAD commit SHA
    indexed_at: datetime

    @property
    def key(self) -> tuple[str, str, str, str]:
        """Idempotency 키."""
        return (self.repo_id, self.snapshot_id, self.head_sha, self.file_path)


class IdempotencyPort(Protocol):
    """Idempotency 저장소 포트."""

    async def mark_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> None:
        """파일 인덱싱 완료 기록."""
        ...

    async def is_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> bool:
        """이미 인덱싱됐는지 확인."""
        ...

    async def filter_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        head_sha: str,
    ) -> tuple[list[str], list[str]]:
        """
        파일 목록을 필터링.

        Returns:
            (인덱싱 필요한 파일, 이미 인덱싱된 파일)
        """
        ...


class InMemoryIdempotencyStore:
    """
    인메모리 Idempotency 저장소.

    프로덕션에서는 PostgreSQL/Redis로 교체 권장.
    현재는 간단한 구현으로 시작.
    """

    def __init__(self, ttl_hours: int = 24):
        """
        Initialize in-memory store.

        Args:
            ttl_hours: 레코드 유지 시간 (시간)
        """
        self.records: dict[tuple, IndexingRecord] = {}
        self.ttl = timedelta(hours=ttl_hours)

    async def mark_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> None:
        """파일 인덱싱 완료 기록."""
        record = IndexingRecord(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_path=file_path,
            head_sha=head_sha,
            indexed_at=datetime.now(timezone.utc),
        )

        self.records[record.key] = record

        # 오래된 레코드 정리
        await self._cleanup_old_records()

        logger.debug(
            "indexing_record_created",
            repo_id=repo_id,
            file_path=file_path,
            head_sha=head_sha[:8],
        )

    async def is_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> bool:
        """이미 인덱싱됐는지 확인."""
        key = (repo_id, snapshot_id, head_sha, file_path)

        if key not in self.records:
            return False

        # TTL 체크
        record = self.records[key]
        age = datetime.now(timezone.utc) - record.indexed_at

        if age > self.ttl:
            # 만료됨
            del self.records[key]
            return False

        return True

    async def filter_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        head_sha: str,
    ) -> tuple[list[str], list[str]]:
        """
        파일 목록 필터링.

        Optimized: O(n) single-pass instead of N individual lookups.
        """
        needs_indexing = []
        already_indexed = []
        now = datetime.now(timezone.utc)

        # O(n) single pass - avoid N function calls
        for file_path in file_paths:
            key = (repo_id, snapshot_id, head_sha, file_path)
            record = self.records.get(key)

            if record is not None:
                # TTL check inline
                age = now - record.indexed_at
                if age <= self.ttl:
                    already_indexed.append(file_path)
                    continue
                # Expired - remove and mark as needs indexing
                del self.records[key]

            needs_indexing.append(file_path)

        if already_indexed:
            logger.info(
                "idempotency_filter_applied",
                repo_id=repo_id,
                head_sha=head_sha[:8],
                total_files=len(file_paths),
                needs_indexing=len(needs_indexing),
                already_indexed=len(already_indexed),
            )

        return needs_indexing, already_indexed

    async def _cleanup_old_records(self):
        """오래된 레코드 정리."""
        now = datetime.now(timezone.utc)

        to_delete = [key for key, record in self.records.items() if now - record.indexed_at > self.ttl]

        for key in to_delete:
            del self.records[key]

        if to_delete:
            logger.debug("old_indexing_records_cleaned", count=len(to_delete))


class PostgresIdempotencyStore:
    """
    PostgreSQL 기반 Idempotency 저장소.

    프로덕션용 구현 (향후).
    """

    def __init__(self, postgres_store):
        """
        Initialize PostgreSQL store.

        Args:
            postgres_store: PostgreSQL store
        """
        self.postgres = postgres_store

    async def mark_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> None:
        """파일 인덱싱 완료 기록."""
        query = """
            INSERT INTO indexing_history (repo_id, snapshot_id, file_path, head_sha, indexed_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (repo_id, snapshot_id, file_path, head_sha)
            DO UPDATE SET indexed_at = NOW()
        """
        await self.postgres.execute(query, repo_id, snapshot_id, file_path, head_sha)
        logger.debug(
            "indexing_marked",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_path=file_path,
            head_sha=head_sha[:8],
        )

    async def is_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        head_sha: str,
    ) -> bool:
        """이미 인덱싱됐는지 확인 (24시간 이내)."""
        query = """
            SELECT EXISTS(
                SELECT 1 FROM indexing_history
                WHERE repo_id = $1 AND snapshot_id = $2
                  AND file_path = $3 AND head_sha = $4
                  AND indexed_at > NOW() - INTERVAL '24 hours'
            )
        """
        result = await self.postgres.fetchval(query, repo_id, snapshot_id, file_path, head_sha)
        return bool(result)

    async def filter_already_indexed(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        head_sha: str,
    ) -> tuple[list[str], list[str]]:
        """
        파일 목록 필터링 (24시간 이내 인덱싱 기록 확인).

        Returns:
            (to_index, already_indexed) tuple
        """
        if not file_paths:
            return [], []

        query = """
            SELECT file_path FROM indexing_history
            WHERE repo_id = $1 AND snapshot_id = $2
              AND file_path = ANY($3) AND head_sha = $4
              AND indexed_at > NOW() - INTERVAL '24 hours'
        """
        rows = await self.postgres.fetch(query, repo_id, snapshot_id, file_paths, head_sha)
        already_indexed = {row["file_path"] for row in rows}

        to_index = [fp for fp in file_paths if fp not in already_indexed]

        logger.debug(
            "idempotency_filter",
            total=len(file_paths),
            to_index=len(to_index),
            already_indexed=len(already_indexed),
        )

        return to_index, list(already_indexed)
