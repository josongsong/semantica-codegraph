"""
Embedding Priority Queue

우선순위 기반 점진적 embedding 처리 큐.
대형 레포에서 핵심 코드만 즉시 embedding하고 나머지는 백그라운드 처리.
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
from codegraph_engine.multi_index.infrastructure.vector.priority import get_chunk_priority

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.vector.worker_pool import EmbeddingWorkerPool
    from codegraph_shared.infra.storage.postgres import PostgresStore


# ============================================================
# Protocol Definitions (Dependency Inversion)
# ============================================================


@runtime_checkable
class EmbeddingProviderProtocol(Protocol):
    """Embedding provider interface."""

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        ...


@runtime_checkable
class VectorIndexProtocol(Protocol):
    """Vector index interface."""

    async def index(self, repo_id: str, snapshot_id: str, docs: list[Any]) -> None:
        """Index documents."""
        ...


@runtime_checkable
class ChunkStoreProtocol(Protocol):
    """Chunk store interface."""

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Get single chunk by ID."""
        ...

    async def get_by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        """Get multiple chunks by IDs."""
        ...


logger = get_logger(__name__)


class EmbeddingQueue:
    """
    Priority 기반 embedding 큐.

    사용:
        queue = EmbeddingQueue(postgres_store, embedding_provider, vector_index, chunk_store)

        # Worker pool과 함께 사용 (권장)
        pool = EmbeddingWorkerPool(queue, worker_count=3)
        await pool.start()

        # 큐에 추가 → 자동 notify → worker 즉시 처리
        await queue.enqueue(chunks, repo_id, snapshot_id)

        # 또는 Legacy: 배치 처리 (deprecated)
        await queue.process_batch(batch_size=100)
    """

    def __init__(
        self,
        postgres_store: "PostgresStore",
        embedding_provider: EmbeddingProviderProtocol,
        vector_index: VectorIndexProtocol,
        chunk_store: ChunkStoreProtocol | None = None,
        worker_pool: "EmbeddingWorkerPool | None" = None,
    ):
        """
        Initialize embedding queue.

        Args:
            postgres_store: PostgreSQL store
            embedding_provider: Embedding provider (OpenAI, Ollama 등)
            vector_index: Vector index (Qdrant)
            chunk_store: Chunk store for loading chunk content
            worker_pool: Worker pool for event-driven processing (선택)
        """
        self.db = postgres_store
        self.embedding_provider = embedding_provider
        self.vector_index = vector_index
        self.chunk_store = chunk_store
        self.worker_pool = worker_pool

    async def enqueue(
        self,
        chunks: list[Chunk],
        repo_id: str,
        snapshot_id: str,
    ) -> int:
        """
        Chunk를 큐에 추가.

        Args:
            chunks: Chunk 리스트
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID

        Returns:
            추가된 개수
        """
        if not chunks:
            return 0

        if self.db is None:
            logger.error("postgres_store_not_initialized")
            raise RuntimeError("PostgresStore not initialized")

        pool = await self.db._ensure_pool()

        inserted_count = 0

        async with pool.acquire() as conn:
            for chunk in chunks:
                priority = get_chunk_priority(chunk)

                try:
                    await conn.execute(
                        """
                        INSERT INTO embedding_queue (
                            chunk_id, repo_id, snapshot_id, priority,
                            state, chunk_kind, file_path
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            priority = EXCLUDED.priority
                        WHERE embedding_queue.state != 'done'
                        """,
                        chunk.chunk_id,
                        repo_id,
                        snapshot_id,
                        priority,
                        "pending",
                        chunk.kind,
                        chunk.file_path,
                    )
                    inserted_count += 1

                except Exception as e:
                    logger.error(
                        "embedding_queue_insert_failed",
                        chunk_id=chunk.chunk_id,
                        error=str(e),
                    )

        logger.info(
            "chunks_enqueued",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            count=inserted_count,
        )

        # Worker pool에 notify (즉시 처리 시작)
        if self.worker_pool:
            # Worker 개수보다 많으면 모두 깨우기
            if inserted_count >= self.worker_pool.worker_count:
                await self.worker_pool.notify_all()
            else:
                # 소량이면 필요한 만큼만
                for _ in range(min(inserted_count, self.worker_pool.worker_count)):
                    await self.worker_pool.notify()

        return inserted_count

    async def pop_one(self) -> dict | None:
        """
        우선순위 가장 높은 item 1개 가져오기 (worker pool용).

        Returns:
            {chunk_id, repo_id, snapshot_id, priority} 또는 None
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="pop_one")
            return None

        pool = await self.db._ensure_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE embedding_queue
                SET state = 'processing',
                    started_at = NOW()
                WHERE chunk_id = (
                    SELECT chunk_id
                    FROM embedding_queue
                    WHERE state = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING chunk_id, repo_id, snapshot_id, priority
                """
            )

        return dict(row) if row else None

    async def process_single_item(
        self,
        chunk_id: str,
        repo_id: str,
        snapshot_id: str,
    ) -> bool:
        """
        단일 chunk 처리 (worker pool에서 호출).

        Args:
            chunk_id: Chunk ID
            repo_id: Repo ID
            snapshot_id: Snapshot ID

        Returns:
            성공 여부
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="process_single_item")
            return False

        pool = await self.db._ensure_pool()

        try:
            # 1. ChunkStore에서 로드
            if not self.chunk_store:
                logger.error("chunk_store_not_available")
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE embedding_queue
                        SET state = 'failed',
                            attempts = attempts + 1,
                            error = 'ChunkStore not available'
                        WHERE chunk_id = $1
                        """,
                        chunk_id,
                    )
                return False

            chunk = await self.chunk_store.get_chunk(chunk_id)
            if not chunk:
                logger.warning("chunk_not_found", chunk_id=chunk_id)
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE embedding_queue
                        SET state = 'failed',
                            attempts = attempts + 1,
                            error = 'Chunk not found'
                        WHERE chunk_id = $1
                        """,
                        chunk_id,
                    )
                return False

            # 2. Embedding 생성
            await self.embedding_provider.embed(chunk.content or "")

            # 3. IndexDocument 생성
            from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

            doc = IndexDocument(
                id=chunk.chunk_id,
                chunk_id=chunk.chunk_id,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=chunk.file_path or "",
                content=chunk.content or "",
                language=chunk.language or "unknown",
                symbol_id=chunk.symbol_id or "",
                fqn=chunk.fqn or "",
            )

            # 4. Qdrant upsert
            await self.vector_index.index(repo_id, snapshot_id, [doc])

            # 5. State를 done으로
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE embedding_queue
                    SET state = 'done',
                        completed_at = NOW(),
                        last_embedding_ts = NOW()
                    WHERE chunk_id = $1
                    """,
                    chunk_id,
                )

            return True

        except Exception as e:
            logger.error(
                "single_item_processing_failed",
                chunk_id=chunk_id,
                error=str(e),
            )

            # failed 상태로
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE embedding_queue
                    SET state = 'failed',
                        attempts = attempts + 1,
                        error = $1
                    WHERE chunk_id = $2
                    """,
                    str(e)[:500],
                    chunk_id,
                )

            return False

    async def has_pending(self) -> bool:
        """큐에 pending 항목 있는지."""
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="has_pending")
            return False

        pool = await self.db._ensure_pool()

        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM embedding_queue WHERE state = 'pending'")

        return (count or 0) > 0

    async def process_batch(self, batch_size: int = 100) -> int:
        """
        큐에서 우선순위 높은 chunk부터 처리.

        Args:
            batch_size: 한 번에 처리할 개수

        Returns:
            처리된 개수
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="process_batch")
            return 0

        pool = await self.db._ensure_pool()

        # 1. 우선순위 높은 pending chunk 가져오기
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, repo_id, snapshot_id, priority
                FROM embedding_queue
                WHERE state = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                batch_size,
            )

        if not rows:
            logger.debug("embedding_queue_empty")
            return 0

        # Repo별로 그룹핑
        from collections import defaultdict

        by_repo = defaultdict(list)
        for row in rows:
            key = (row["repo_id"], row["snapshot_id"])
            by_repo[key].append(row)

        total_processed = 0

        # Repo별로 처리
        for (repo_id, snapshot_id), repo_rows in by_repo.items():
            processed = await self._process_repo_batch(repo_rows, repo_id, snapshot_id)
            total_processed += processed

        return total_processed

    async def _process_repo_batch(self, rows: list, repo_id: str, snapshot_id: str) -> int:
        """단일 repo의 배치 처리."""
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="_process_repo_batch")
            return 0

        chunk_ids = [row["chunk_id"] for row in rows]

        pool = await self.db._ensure_pool()

        logger.info(
            "embedding_batch_processing",
            count=len(chunk_ids),
            highest_priority=rows[0]["priority"],
        )

        # 2. State를 processing으로 변경
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE embedding_queue
                SET state = 'processing', started_at = NOW()
                WHERE chunk_id = ANY($1::text[])
                """,
                chunk_ids,
            )

        # 2.5. chunk_store에서 chunk 데이터 가져오기
        if not self.chunk_store:
            logger.warning("chunk_store_not_configured")
            return 0

        chunks = await self.chunk_store.get_by_ids(chunk_ids)
        if not chunks:
            logger.warning("chunks_not_found", chunk_ids=chunk_ids)
            return 0

        # 3. 개별 chunk별로 embedding 생성 (에러 처리 강화)
        succeeded = []
        failed = []

        for chunk in chunks:
            try:
                # 3-1. Embedding 생성
                await self.embedding_provider.embed(chunk.content or "")

                # 3-2. IndexDocument 생성
                from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument

                doc = IndexDocument(
                    id=chunk.chunk_id,
                    chunk_id=chunk.chunk_id,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    file_path=chunk.file_path,
                    content=chunk.content,
                    language=chunk.language,
                    symbol_id=chunk.symbol_id,
                    fqn=chunk.fqn,
                )

                # 3-3. Qdrant upsert
                await self.vector_index.index(repo_id, snapshot_id, [doc])

                # 3-4. State를 done으로
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE embedding_queue
                        SET state = 'done',
                            completed_at = NOW(),
                            last_embedding_ts = NOW()
                        WHERE chunk_id = $1
                        """,
                        chunk.chunk_id,
                    )

                succeeded.append(chunk.chunk_id)

            except Exception as e:
                # 개별 chunk 실패 처리
                logger.error(
                    "single_chunk_embedding_failed",
                    chunk_id=chunk.chunk_id,
                    error=str(e),
                )

                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE embedding_queue
                        SET state = 'failed',
                            attempts = attempts + 1,
                            error = $1
                        WHERE chunk_id = $2
                        """,
                        str(e)[:500],  # 에러 메시지 길이 제한
                        chunk.chunk_id,
                    )

                failed.append(chunk.chunk_id)

        logger.info(
            "repo_batch_completed",
            repo_id=repo_id,
            succeeded=len(succeeded),
            failed=len(failed),
        )

        return len(succeeded)

    async def retry_failed(self, max_attempts: int = 3) -> int:
        """
        실패한 항목 재시도.

        Args:
            max_attempts: 최대 재시도 횟수

        Returns:
            재시도 성공 개수
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="retry_failed")
            return 0

        pool = await self.db._ensure_pool()

        # Exponential backoff: attempts에 따라 대기 시간 증가
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE embedding_queue
                SET state = 'pending', error = NULL
                WHERE state = 'failed'
                  AND attempts < $1
                  AND completed_at < NOW() - (attempts * INTERVAL '5 minutes')
                """,
                max_attempts,
            )

            retry_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM embedding_queue
                WHERE state = 'pending' AND attempts > 0
                """
            )

        if retry_count > 0:
            logger.info("embedding_retry_scheduled", count=retry_count)

        return retry_count or 0

    async def get_stats(self, repo_id: str | None = None, snapshot_id: str | None = None) -> dict:
        """
        큐 통계.

        Args:
            repo_id: 특정 repo (None이면 전체)
            snapshot_id: 특정 snapshot (None이면 전체)

        Returns:
            통계 dict
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="get_stats")
            return {"total": 0, "pending": 0, "processing": 0, "done": 0, "failed": 0, "avg_priority": 0.0}

        pool = await self.db._ensure_pool()

        # Use NULL-safe parameter binding (no f-string injection risk)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN state = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN state = 'processing' THEN 1 ELSE 0 END) as processing,
                    SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) as done,
                    SUM(CASE WHEN state = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(priority) as avg_priority
                FROM embedding_queue
                WHERE ($1::text IS NULL OR repo_id = $1)
                  AND ($2::text IS NULL OR snapshot_id = $2)
                """,
                repo_id,
                snapshot_id,
            )

        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "processing": row["processing"] or 0,
            "done": row["done"] or 0,
            "failed": row["failed"] or 0,
            "avg_priority": float(row["avg_priority"]) if row["avg_priority"] else 0.0,
        }

    async def cleanup_completed(self, older_than_days: int = 7) -> int:
        """
        완료된 항목 정리.

        Args:
            older_than_days: N일 이상 된 완료 항목 삭제

        Returns:
            삭제된 개수
        """
        if self.db is None:
            logger.error("postgres_store_not_initialized", method="cleanup_completed")
            return 0

        pool = await self.db._ensure_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM embedding_queue
                WHERE state = 'done'
                  AND completed_at < NOW() - ($1 || ' days')::INTERVAL
                """,
                older_than_days,
            )

            deleted = int(result.split()[-1]) if result else 0

        if deleted > 0:
            logger.info("embedding_queue_cleaned", deleted=deleted)

        return deleted
