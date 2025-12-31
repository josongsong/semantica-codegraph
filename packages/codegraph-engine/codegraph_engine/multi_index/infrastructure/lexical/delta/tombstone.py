"""Tombstone Manager - 삭제된 파일 추적."""

from typing import TYPE_CHECKING

from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class TombstoneManager:
    """Tombstone 관리자.

    Delta Index에서 삭제된 파일을 추적하여
    Base Index와 merge 시 필터링합니다.
    """

    def __init__(self, db_pool: "PostgresStore"):
        """
        Args:
            db_pool: PostgresStore 인스턴스
        """
        self._store = db_pool

    async def _get_pool(self):
        """Get pool with lazy initialization."""
        return await self._store._ensure_pool()

    async def _execute(self, query: str, *args) -> str:
        """Execute a query and return status (e.g., 'DELETE 5')."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def _fetch(self, query: str, *args):
        """Execute a query and return all rows."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def mark_deleted(
        self,
        repo_id: str,
        file_path: str,
        base_version_id: int | None = None,
    ) -> None:
        """파일을 삭제로 표시 (Tombstone).

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            base_version_id: Base snapshot ID
        """
        await self._execute(
            """
            INSERT INTO delta_lexical_index (
                repo_id, file_path, content, deleted, base_version_id
            )
            VALUES ($1, $2, '', TRUE, $3)
            ON CONFLICT (repo_id, file_path) DO UPDATE
            SET deleted = TRUE,
                indexed_at = NOW()
            """,
            repo_id,
            file_path,
            base_version_id,
        )
        logger.info(f"Marked file as deleted (tombstone): {file_path}")

    async def is_deleted(self, repo_id: str, file_path: str) -> bool:
        """파일이 삭제되었는지 확인.

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로

        Returns:
            삭제 여부
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT deleted
                FROM delta_lexical_index
                WHERE repo_id = $1 AND file_path = $2
                """,
                repo_id,
                file_path,
            )
            return result is True

    async def get_tombstones(
        self,
        repo_id: str,
        base_version_id: int | None = None,
    ) -> set[str]:
        """Tombstone 파일 목록 조회.

        Args:
            repo_id: 저장소 ID
            base_version_id: Base snapshot ID (옵션)

        Returns:
            삭제된 파일 경로 집합
        """
        if base_version_id is not None:
            rows = await self._fetch(
                """
                SELECT file_path
                FROM delta_lexical_index
                WHERE repo_id = $1
                  AND base_version_id = $2
                  AND deleted = TRUE
                """,
                repo_id,
                base_version_id,
            )
        else:
            rows = await self._fetch(
                """
                SELECT file_path
                FROM delta_lexical_index
                WHERE repo_id = $1 AND deleted = TRUE
                """,
                repo_id,
            )

        tombstones = {row["file_path"] for row in rows}
        logger.debug(f"Found {len(tombstones)} tombstones for repo: {repo_id}")
        return tombstones

    async def clear_tombstones(
        self,
        repo_id: str,
        base_version_id: int | None = None,
    ) -> int:
        """Tombstone 삭제 (Compaction 후).

        Args:
            repo_id: 저장소 ID
            base_version_id: Base snapshot ID (옵션)

        Returns:
            삭제된 tombstone 개수
        """
        if base_version_id is not None:
            status = await self._execute(
                """
                DELETE FROM delta_lexical_index
                WHERE repo_id = $1
                  AND base_version_id = $2
                  AND deleted = TRUE
                """,
                repo_id,
                base_version_id,
            )
        else:
            status = await self._execute(
                """
                DELETE FROM delta_lexical_index
                WHERE repo_id = $1 AND deleted = TRUE
                """,
                repo_id,
            )

        # Parse count from status (e.g., "DELETE 5" -> 5)
        count = int(status.split()[-1]) if status else 0
        logger.info(f"Cleared {count} tombstones for repo: {repo_id}")
        return count
