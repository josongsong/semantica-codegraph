"""PostgreSQL tsvector Adapter - Delta Index 백엔드."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """검색 결과.

    Attributes:
        file_path: 파일 경로
        score: ts_rank_cd 점수
        snippet: 코드 스니펫
        repo_id: 저장소 ID
    """

    file_path: str
    score: float
    snippet: str
    repo_id: str


class PostgresAdapter:
    """PostgreSQL tsvector 어댑터.

    PostgreSQL의 full-text search를 사용하여
    Delta Index를 구현합니다.
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

    async def index_document(
        self,
        repo_id: str,
        file_path: str,
        content: str,
        base_version_id: int | None = None,
    ) -> bool:
        """문서 인덱싱.

        Args:
            repo_id: 저장소 ID
            file_path: 파일 경로
            content: 파일 내용
            base_version_id: Base snapshot ID

        Returns:
            성공 여부
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO delta_lexical_index (
                        repo_id, file_path, content, base_version_id, deleted
                    )
                    VALUES ($1, $2, $3, $4, FALSE)
                    ON CONFLICT (repo_id, file_path) DO UPDATE
                    SET content = EXCLUDED.content,
                        indexed_at = NOW(),
                        deleted = FALSE,
                        base_version_id = EXCLUDED.base_version_id
                    """,
                    repo_id,
                    file_path,
                    content,
                    base_version_id,
                )

            logger.debug(f"Indexed document: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Index failed: {file_path}, error={e}")
            return False

    async def search(
        self,
        query: str,
        repo_id: str,
        limit: int = 50,
    ) -> list[SearchResult]:
        """검색 (PostgreSQL full-text search).

        Args:
            query: 검색 쿼리
            repo_id: 저장소 ID
            limit: 최대 결과 수

        Returns:
            SearchResult 리스트
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        file_path,
                        repo_id,
                        ts_rank_cd(content_tsvector, plainto_tsquery('english', $1)) AS score,
                        left(content, 200) AS snippet
                    FROM delta_lexical_index
                    WHERE repo_id = $2
                      AND deleted = FALSE
                      AND content_tsvector @@ plainto_tsquery('english', $1)
                    ORDER BY score DESC
                    LIMIT $3
                    """,
                    query,
                    repo_id,
                    limit,
                )

            results = [
                SearchResult(
                    file_path=row["file_path"],
                    score=float(row["score"]),
                    snippet=row["snippet"],
                    repo_id=row["repo_id"],
                )
                for row in rows
            ]

            logger.debug(f"Search '{query}': {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Search failed: {query}, error={e}")
            return []

    async def delete_document(self, file_path: str, repo_id: str) -> bool:
        """문서 삭제 (Tombstone 생성).

        Args:
            file_path: 파일 경로
            repo_id: 저장소 ID

        Returns:
            성공 여부
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE delta_lexical_index
                    SET deleted = TRUE,
                        indexed_at = NOW()
                    WHERE repo_id = $1 AND file_path = $2
                    """,
                    repo_id,
                    file_path,
                )

            logger.debug(f"Deleted document: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Delete failed: {file_path}, error={e}")
            return False

    async def clear_all(self, repo_id: str) -> bool:
        """저장소의 모든 문서 삭제.

        Args:
            repo_id: 저장소 ID

        Returns:
            성공 여부
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    DELETE FROM delta_lexical_index
                    WHERE repo_id = $1
                    """,
                    repo_id,
                )

            logger.info(f"Cleared Delta index: {repo_id}")
            return True

        except Exception as e:
            logger.error(f"Clear failed: {repo_id}, error={e}")
            return False
