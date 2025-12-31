"""Search logger for ML tuning."""

import json
import uuid
from typing import Any

from codegraph_shared.infra.observability import get_logger

from .models import SearchLog

logger = get_logger(__name__)


class SearchLogger:
    """검색 로그 수집기.

    Usage:
        logger = SearchLogger(db_pool)

        # 검색 실행 시
        log_id = await logger.log_search(
            query="find authentication",
            intent="symbol",
            results=results,
            repo_id=repo_id,
        )

        # 사용자 피드백 시
        await logger.log_feedback(
            log_id=log_id,
            clicked_rank=3,
            was_helpful=True,
        )
    """

    def __init__(
        self,
        db_pool,
        enable_async: bool = True,
        buffer_size: int = 100,
    ):
        """Initialize search logger.

        Args:
            db_pool: PostgresStore instance (must be initialized with pool)
            enable_async: Enable async buffering (recommended)
            buffer_size: Buffer size before flush
        """
        self.db_store = db_pool
        self.enable_async = enable_async
        self.buffer_size = buffer_size
        self.buffer: list[SearchLog] = []

    async def log_search(
        self,
        query: str,
        repo_id: str,
        results: list[dict],
        intent: str | None = None,
        candidates: list[dict] | None = None,
        late_interaction_scores: dict[str, Any] | None = None,
        fusion_strategy: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        **metadata,
    ) -> str:
        """검색 실행 로그 기록.

        Args:
            query: User query
            repo_id: Repository ID
            results: Final results (list of dicts with chunk_id, score)
            intent: Query intent (symbol, flow, concept, etc)
            candidates: Candidate chunks before final ranking
            late_interaction_scores: Late interaction metadata (max_sims, etc)
            fusion_strategy: Fusion strategy used
            user_id: User ID (optional)
            session_id: Session ID (optional)
            **metadata: Additional metadata

        Returns:
            log_id for feedback updates
        """
        log_id = str(uuid.uuid4())

        search_log = SearchLog(
            log_id=log_id,
            query=query,
            intent=intent,
            repo_id=repo_id,
            user_id=user_id,
            session_id=session_id,
            candidate_count=len(candidates) if candidates else None,
            fusion_strategy=fusion_strategy,
            late_interaction_enabled=late_interaction_scores is not None,
            max_sim_scores=late_interaction_scores.get("max_sims") if late_interaction_scores else None,
            top_k=len(results),
            result_chunk_ids=[r.get("chunk_id", "") for r in results],
            result_scores=[r.get("score", 0.0) for r in results],
            metadata=metadata if metadata else None,
        )

        # 비동기 버퍼링 또는 즉시 저장
        if self.enable_async:
            self.buffer.append(search_log)
            if len(self.buffer) >= self.buffer_size:
                await self._flush()
        else:
            await self._save(search_log)

        logger.debug(f"Search logged: {log_id} (query='{query[:50]}...')")
        return log_id

    async def log_feedback(
        self,
        log_id: str,
        clicked_rank: int | None = None,
        clicked_chunk_id: str | None = None,
        dwell_time: float | None = None,
        was_helpful: bool | None = None,
    ):
        """사용자 피드백 로그 업데이트.

        Args:
            log_id: Search log ID (from log_search)
            clicked_rank: Rank of clicked result (1-indexed)
            clicked_chunk_id: Chunk ID of clicked result
            dwell_time: Time spent on result page (seconds)
            was_helpful: Explicit user feedback
        """
        update_query = """
            UPDATE search_logs
            SET
                clicked_rank = COALESCE($2, clicked_rank),
                clicked_chunk_id = COALESCE($3, clicked_chunk_id),
                dwell_time = COALESCE($4, dwell_time),
                was_helpful = COALESCE($5, was_helpful)
            WHERE log_id = $1
        """

        async with self.db_store.pool.acquire() as conn:
            await conn.execute(
                update_query,
                log_id,
                clicked_rank,
                clicked_chunk_id,
                dwell_time,
                was_helpful,
            )

        logger.debug(f"Feedback logged: {log_id} (clicked_rank={clicked_rank}, helpful={was_helpful})")

    async def _save(self, search_log: SearchLog):
        """Save single log to database."""
        insert_query = """
            INSERT INTO search_logs (
                log_id, timestamp, query, intent, repo_id, user_id, session_id,
                candidate_count, fusion_strategy,
                late_interaction_enabled, max_sim_scores,
                top_k, result_chunk_ids, result_scores,
                metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                $8, $9,
                $10, $11,
                $12, $13, $14,
                $15
            )
        """

        async with self.db_store.pool.acquire() as conn:
            await conn.execute(
                insert_query,
                search_log.log_id,
                search_log.timestamp,
                search_log.query,
                search_log.intent,
                search_log.repo_id,
                search_log.user_id,
                search_log.session_id,
                search_log.candidate_count,
                search_log.fusion_strategy,
                search_log.late_interaction_enabled,
                json.dumps(search_log.max_sim_scores) if search_log.max_sim_scores else None,
                search_log.top_k,
                search_log.result_chunk_ids,
                search_log.result_scores,
                json.dumps(search_log.metadata) if search_log.metadata else None,
            )

    async def _flush(self):
        """Flush buffered logs to database."""
        if not self.buffer:
            return

        logger.info(f"Flushing {len(self.buffer)} search logs to database")

        for search_log in self.buffer:
            try:
                await self._save(search_log)
            except Exception as e:
                logger.error(f"Failed to save search log {search_log.log_id}: {e}")

        self.buffer.clear()

    async def close(self):
        """Flush remaining logs and close."""
        await self._flush()
