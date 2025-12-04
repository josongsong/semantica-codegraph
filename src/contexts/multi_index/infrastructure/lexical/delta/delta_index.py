"""Delta Lexical Index - 파일 단위 증분 BM25 (PostgreSQL)."""

from typing import TYPE_CHECKING

from src.contexts.multi_index.infrastructure.lexical.delta.postgres_adapter import PostgresAdapter
from src.contexts.multi_index.infrastructure.lexical.delta.tombstone import TombstoneManager
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class DeltaLexicalIndex:
    """Delta Lexical Index.

    PostgreSQL tsvector 기반 파일 단위 증분 BM25 인덱스.
    Base (Zoekt)를 건드리지 않고 Delta만 업데이트합니다.
    """

    def __init__(
        self,
        db_pool: "PostgresStore",
        tombstone_manager: TombstoneManager,
    ):
        """
        Args:
            db_pool: PostgresStore 인스턴스
            tombstone_manager: TombstoneManager 인스턴스
        """
        self.postgres = PostgresAdapter(db_pool=db_pool)
        self.db = db_pool
        self.tombstone = tombstone_manager

    async def _get_pool(self):
        """Get pool with lazy initialization."""
        return await self.db._ensure_pool()

    async def index_file(
        self,
        repo_id: str,
        file_path: str,
        content: str,
        base_version_id: int | None = None,
    ) -> bool:
        """파일 인덱싱 (Delta).

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            content: 파일 내용
            base_version_id: Base snapshot ID

        Returns:
            성공 여부
        """
        # PostgreSQL tsvector 인덱싱
        success = await self.postgres.index_document(
            repo_id=repo_id,
            file_path=file_path,
            content=content,
            base_version_id=base_version_id,
        )

        if success:
            logger.info(f"Indexed to Delta: {file_path}")

        return success

    async def delete_file(
        self,
        repo_id: str,
        file_path: str,
        base_version_id: int | None = None,
    ) -> None:
        """파일 삭제 (Tombstone 생성).

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            base_version_id: Base snapshot ID
        """
        # PostgreSQL에서 삭제 (Tombstone)
        await self.postgres.delete_document(file_path, repo_id)

        logger.info(f"Deleted from Delta (tombstone): {file_path}")

    async def search(
        self,
        repo_id: str,
        query: str,
        limit: int = 50,
    ) -> list[dict]:
        """Delta 검색.

        Args:
            repo_id: 저장소 ID
            query: 검색 쿼리
            limit: 최대 결과 수

        Returns:
            검색 결과 리스트
        """
        # PostgreSQL full-text search
        results = await self.postgres.search(query, repo_id, limit)

        return [
            {
                "file_path": r.file_path,
                "score": r.score,
                "snippet": r.snippet,
                "source": "lexical",  # SearchHit은 'lexical' 사용
            }
            for r in results
        ]

    async def count(self, repo_id: str) -> int:
        """Delta 크기 조회.

        Args:
            repo_id: 저장소 ID

        Returns:
            Delta에 있는 파일 개수
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM delta_lexical_index
                WHERE repo_id = $1 AND deleted = FALSE
                """,
                repo_id,
            )
            return count or 0

    async def clear(self, repo_id: str) -> None:
        """Delta 초기화 (Compaction 후).

        Args:
            repo_id: 저장소 ID
        """
        # PostgreSQL 초기화
        await self.postgres.clear_all(repo_id)

        logger.info(f"Cleared Delta index: {repo_id}")
