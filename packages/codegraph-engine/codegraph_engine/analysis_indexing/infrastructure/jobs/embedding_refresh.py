"""
Embedding Refresh Job

오래된 embedding을 재생성하는 백그라운드 작업.
"""

from datetime import datetime, timedelta, timezone

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class EmbeddingRefreshJob:
    """Embedding 재생성 작업"""

    def __init__(
        self,
        postgres_store,
        embedding_queue,
        chunk_store,
        stale_threshold_days: int = 7,
    ):
        """
        Initialize embedding refresh job.

        Args:
            postgres_store: PostgreSQL store
            embedding_queue: EmbeddingQueue instance
            chunk_store: ChunkStore instance
            stale_threshold_days: Embedding이 오래된 것으로 간주할 일 수
        """
        self.postgres = postgres_store
        self.embedding_queue = embedding_queue
        self.chunk_store = chunk_store
        self.stale_threshold_days = stale_threshold_days

    async def run(self, repo_id: str | None = None) -> dict:
        """
        Embedding refresh 작업 실행.

        Args:
            repo_id: 특정 repo만 처리 (None이면 전체)

        Returns:
            실행 결과 dict
        """
        logger.info("embedding_refresh_job_started", repo_id=repo_id)

        # 1. 오래된 embedding 찾기
        stale_chunks = await self._find_stale_embeddings(repo_id)

        if not stale_chunks:
            logger.info("embedding_refresh_no_stale_chunks")
            return {
                "status": "success",
                "stale_count": 0,
                "enqueued": 0,
            }

        # 2. Embedding queue에 재등록
        enqueued_count = 0

        for chunk_data in stale_chunks:
            chunk_id = chunk_data["chunk_id"]
            chunk_repo_id = chunk_data["repo_id"]
            snapshot_id = chunk_data["snapshot_id"]

            try:
                # Load chunk from store
                chunk = await self.chunk_store.get_chunk_by_id(chunk_id)

                if chunk:
                    # Re-enqueue for embedding
                    await self.embedding_queue.enqueue(
                        [chunk],
                        chunk_repo_id,
                        snapshot_id,
                    )
                    enqueued_count += 1

            except Exception as e:
                logger.warning(
                    "embedding_refresh_enqueue_failed",
                    chunk_id=chunk_id,
                    error=str(e),
                )

        logger.info(
            "embedding_refresh_job_completed",
            repo_id=repo_id,
            stale_count=len(stale_chunks),
            enqueued=enqueued_count,
        )

        return {
            "status": "success",
            "stale_count": len(stale_chunks),
            "enqueued": enqueued_count,
        }

    async def _find_stale_embeddings(self, repo_id: str | None = None) -> list[dict]:
        """
        오래된 embedding 찾기.

        Args:
            repo_id: 특정 repo만 (None이면 전체)

        Returns:
            {chunk_id, repo_id, snapshot_id, last_embedding_ts} 리스트
        """
        pool = await self.postgres._ensure_pool()

        threshold_date = datetime.now(timezone.utc) - timedelta(days=self.stale_threshold_days)

        where_clause = "TRUE"
        params = [threshold_date]

        if repo_id:
            where_clause = "repo_id = $2"
            params.append(repo_id)

        query = f"""
        SELECT chunk_id, repo_id, snapshot_id, last_embedding_ts
        FROM embedding_queue
        WHERE state = 'done'
          AND last_embedding_ts < $1
          AND {where_clause}
        ORDER BY last_embedding_ts ASC
        LIMIT 1000
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]

    async def get_stats(self, repo_id: str | None = None) -> dict:
        """
        Embedding 통계.

        Args:
            repo_id: 특정 repo만 (None이면 전체)

        Returns:
            통계 dict
        """
        pool = await self.postgres._ensure_pool()

        threshold_date = datetime.now(timezone.utc) - timedelta(days=self.stale_threshold_days)

        where_clause = "TRUE"
        params = [threshold_date]

        if repo_id:
            where_clause = "repo_id = $2"
            params.append(repo_id)

        query = f"""
        SELECT
            COUNT(*) FILTER (WHERE state = 'done' AND last_embedding_ts >= $1) as fresh,
            COUNT(*) FILTER (WHERE state = 'done' AND last_embedding_ts < $1) as stale,
            COUNT(*) FILTER (WHERE state = 'pending') as pending,
            COUNT(*) FILTER (WHERE state = 'failed') as failed
        FROM embedding_queue
        WHERE {where_clause}
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        return {
            "fresh": row["fresh"] or 0,
            "stale": row["stale"] or 0,
            "pending": row["pending"] or 0,
            "failed": row["failed"] or 0,
            "threshold_days": self.stale_threshold_days,
        }
