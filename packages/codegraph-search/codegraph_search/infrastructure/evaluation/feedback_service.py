"""
Feedback Service

Collects user feedback on retrieval results for:
1. Continuous improvement
2. Golden set candidate generation
3. Hard negative mining

Feedback Actions:
- Positive: clicked, copied, upvoted, marked_relevant
- Negative: dismissed, downvoted, marked_irrelevant
- Missing: reported_missing, reported_wrong
"""

import json
from typing import Any
from uuid import UUID

from codegraph_shared.common.observability import get_logger
from codegraph_search.infrastructure.evaluation.models import FeedbackAction, FeedbackInput, FeedbackLog
from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class FeedbackService:
    """
    Service for collecting and analyzing user feedback.

    Uses PostgreSQL (feedback_logs table) for persistence.
    """

    def __init__(self, postgres: PostgresStore):
        """
        Initialize feedback service.

        Args:
            postgres: PostgreSQL storage instance
        """
        self.postgres = postgres

    async def log_feedback(
        self,
        feedback_input: FeedbackInput | None = None,
        *,
        # Legacy parameters (backward compatible)
        query: str | None = None,
        retrieved_chunk_ids: list[str] | None = None,
        action: FeedbackAction | None = None,
        repo_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        query_intent: str | None = None,
        retrieval_scores: dict[str, float] | None = None,
        retrieval_metadata: dict[str, Any] | None = None,
        target_chunk_ids: list[str] | None = None,
        feedback_text: str | None = None,
        file_context: str | None = None,
        query_duration_ms: int | None = None,
    ) -> FeedbackLog:
        """
        Log user feedback on retrieval results.

        Supports two usage patterns:
        1. New style (recommended): Pass FeedbackInput object
        2. Legacy style: Pass individual parameters

        Args:
            feedback_input: FeedbackInput object (recommended)
            query: Natural language query (legacy)
            retrieved_chunk_ids: Chunk IDs returned by retriever (legacy)
            action: User action (clicked, upvoted, etc.) (legacy)
            repo_id: Repository ID (legacy)
            user_id: Optional user identifier
            session_id: Optional session identifier
            query_intent: Optional inferred query intent
            retrieval_scores: Optional scores for each chunk
            retrieval_metadata: Optional retriever metadata
            target_chunk_ids: Optional specific chunks feedback applies to
            feedback_text: Optional free-form feedback
            file_context: Optional file user was viewing
            query_duration_ms: Optional query duration

        Returns:
            Created FeedbackLog
        """
        # New style: use FeedbackInput
        if feedback_input is not None:
            feedback = feedback_input.to_feedback_log()
        # Legacy style: use individual parameters
        elif query is not None and retrieved_chunk_ids is not None and action is not None and repo_id is not None:
            feedback = FeedbackLog(
                query=query,
                retrieved_chunk_ids=retrieved_chunk_ids,
                action=action,
                repo_id=repo_id,
                user_id=user_id,
                session_id=session_id,
                query_intent=query_intent,
                retrieval_scores=retrieval_scores,
                retrieval_metadata=retrieval_metadata,
                target_chunk_ids=target_chunk_ids,
                feedback_text=feedback_text,
                file_context=file_context,
                query_duration_ms=query_duration_ms,
            )
        else:
            raise ValueError(
                "Either feedback_input or required parameters "
                "(query, retrieved_chunk_ids, action, repo_id) must be provided"
            )

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_logs (
                    feedback_id, user_id, session_id,
                    query, query_intent,
                    retrieved_chunk_ids, retrieval_scores, retrieval_metadata,
                    action, target_chunk_ids, feedback_text,
                    repo_id, file_context,
                    timestamp, query_duration_ms,
                    processed, processed_at, golden_set_candidate
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                )
                """,
                str(feedback.feedback_id),
                feedback.user_id,
                feedback.session_id,
                feedback.query,
                feedback.query_intent,
                json.dumps(feedback.retrieved_chunk_ids),
                json.dumps(feedback.retrieval_scores) if feedback.retrieval_scores else None,
                json.dumps(feedback.retrieval_metadata) if feedback.retrieval_metadata else None,
                feedback.action,  # Already string due to use_enum_values
                json.dumps(feedback.target_chunk_ids) if feedback.target_chunk_ids else None,
                feedback.feedback_text,
                feedback.repo_id,
                feedback.file_context,
                feedback.timestamp,
                feedback.query_duration_ms,
                feedback.processed,
                feedback.processed_at,
                feedback.golden_set_candidate,
            )

        logger.info(f"Logged feedback: {feedback.feedback_id} ({feedback.action})")
        return feedback

    async def get_feedback(self, feedback_id: UUID | str) -> FeedbackLog | None:
        """
        Get feedback by ID.

        Args:
            feedback_id: Feedback UUID

        Returns:
            FeedbackLog if found, None otherwise
        """
        feedback_id_str = str(feedback_id)

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM feedback_logs WHERE feedback_id = $1",
                feedback_id_str,
            )

        if not row:
            return None

        return self._feedback_from_row(row)

    async def list_unprocessed_feedback(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeedbackLog]:
        """
        List unprocessed feedback logs.

        Args:
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of unprocessed FeedbackLog objects
        """
        async with self.postgres.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM feedback_logs
                WHERE processed = FALSE
                ORDER BY timestamp DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        return [self._feedback_from_row(row) for row in rows]

    async def list_golden_set_candidates(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeedbackLog]:
        """
        List feedback marked as golden set candidates.

        Args:
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of FeedbackLog objects marked as candidates
        """
        async with self.postgres.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM feedback_logs
                WHERE golden_set_candidate = TRUE
                ORDER BY timestamp DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

        return [self._feedback_from_row(row) for row in rows]

    async def mark_as_processed(self, feedback_id: UUID | str):
        """
        Mark feedback as processed.

        Args:
            feedback_id: Feedback UUID
        """
        feedback_id_str = str(feedback_id)

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feedback_logs
                SET processed = TRUE, processed_at = NOW()
                WHERE feedback_id = $1
                """,
                feedback_id_str,
            )

    async def mark_as_golden_set_candidate(self, feedback_id: UUID | str):
        """
        Mark feedback as golden set candidate.

        Args:
            feedback_id: Feedback UUID
        """
        feedback_id_str = str(feedback_id)

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feedback_logs
                SET golden_set_candidate = TRUE
                WHERE feedback_id = $1
                """,
                feedback_id_str,
            )

    async def extract_golden_set_candidates(
        self,
        min_positive_actions: int = 2,
        action_threshold: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Extract golden set candidates from feedback logs.

        Heuristic: Queries with multiple positive interactions are good candidates.

        Positive actions:
        - clicked
        - copied
        - upvoted
        - marked_relevant

        Args:
            min_positive_actions: Minimum positive actions to be a candidate
            action_threshold: Minimum total actions on query

        Returns:
            List of candidate dicts with:
            {
                "query": str,
                "repo_id": str,
                "relevant_chunk_ids": list[str],
                "positive_action_count": int,
                "total_action_count": int,
                "confidence_score": float,
            }
        """
        positive_actions = ["clicked", "copied", "upvoted", "marked_relevant"]

        async with self.postgres.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH query_actions AS (
                    SELECT
                        query,
                        repo_id,
                        action,
                        target_chunk_ids,
                        COUNT(*) OVER (PARTITION BY query, repo_id) as total_actions,
                        SUM(CASE WHEN action = ANY($1) THEN 1 ELSE 0 END)
                            OVER (PARTITION BY query, repo_id) as positive_actions
                    FROM feedback_logs
                    WHERE processed = FALSE
                      AND target_chunk_ids IS NOT NULL
                ),
                expanded_chunks AS (
                    SELECT
                        query,
                        repo_id,
                        jsonb_array_elements(target_chunk_ids) as chunk_id,
                        positive_actions,
                        total_actions
                    FROM query_actions
                    WHERE total_actions >= $2
                      AND positive_actions >= $3
                )
                SELECT
                    query,
                    repo_id,
                    json_agg(DISTINCT chunk_id) as relevant_chunks,
                    MAX(positive_actions) as positive_count,
                    MAX(total_actions) as total_count
                FROM expanded_chunks
                GROUP BY query, repo_id
                ORDER BY positive_count DESC, total_count DESC
                """,
                positive_actions,
                action_threshold,
                min_positive_actions,
            )

        candidates = []
        for row in rows:
            relevant_chunk_ids = [chunk_id for chunk_id in row["relevant_chunks"] if chunk_id is not None]

            confidence_score = row["positive_count"] / row["total_count"] if row["total_count"] > 0 else 0

            candidates.append(
                {
                    "query": row["query"],
                    "repo_id": row["repo_id"],
                    "relevant_chunk_ids": relevant_chunk_ids,
                    "positive_action_count": row["positive_count"],
                    "total_action_count": row["total_count"],
                    "confidence_score": confidence_score,
                }
            )

        logger.info(f"Extracted {len(candidates)} golden set candidates")
        return candidates

    async def get_feedback_statistics(self) -> dict[str, Any]:
        """
        Get feedback statistics.

        Returns:
            Dict with statistics:
            - total_feedback
            - by_action
            - golden_set_candidates
            - unprocessed_count
        """
        async with self.postgres.pool.acquire() as conn:
            # Total count
            total_row = await conn.fetchrow("SELECT COUNT(*) as count FROM feedback_logs")
            total = total_row["count"]

            # By action
            action_rows = await conn.fetch(
                """
                SELECT action, COUNT(*) as count
                FROM feedback_logs
                GROUP BY action
                ORDER BY count DESC
                """
            )
            by_action = {row["action"]: row["count"] for row in action_rows}

            # Golden set candidates
            candidate_row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM feedback_logs WHERE golden_set_candidate = TRUE"
            )
            candidates = candidate_row["count"]

            # Unprocessed count
            unprocessed_row = await conn.fetchrow("SELECT COUNT(*) as count FROM feedback_logs WHERE processed = FALSE")
            unprocessed = unprocessed_row["count"]

        return {
            "total_feedback": total,
            "by_action": by_action,
            "golden_set_candidates": candidates,
            "unprocessed_count": unprocessed,
        }

    def _feedback_from_row(self, row) -> FeedbackLog:
        """Convert database row to FeedbackLog model."""
        # asyncpg returns UUID objects, convert to str first
        feedback_id_val = row["feedback_id"]
        if not isinstance(feedback_id_val, UUID):
            feedback_id_val = UUID(str(feedback_id_val))

        return FeedbackLog(
            feedback_id=feedback_id_val,
            user_id=row["user_id"],
            session_id=row["session_id"],
            query=row["query"],
            query_intent=row["query_intent"],
            retrieved_chunk_ids=json.loads(row["retrieved_chunk_ids"])
            if isinstance(row["retrieved_chunk_ids"], str)
            else row["retrieved_chunk_ids"],
            retrieval_scores=json.loads(row["retrieval_scores"])
            if row["retrieval_scores"] and isinstance(row["retrieval_scores"], str)
            else row["retrieval_scores"],
            retrieval_metadata=json.loads(row["retrieval_metadata"])
            if row["retrieval_metadata"] and isinstance(row["retrieval_metadata"], str)
            else row["retrieval_metadata"],
            action=FeedbackAction(row["action"]),
            target_chunk_ids=json.loads(row["target_chunk_ids"])
            if row["target_chunk_ids"] and isinstance(row["target_chunk_ids"], str)
            else row["target_chunk_ids"],
            feedback_text=row["feedback_text"],
            repo_id=row["repo_id"],
            file_context=row["file_context"],
            timestamp=row["timestamp"],
            query_duration_ms=row["query_duration_ms"],
            processed=row["processed"],
            processed_at=row["processed_at"],
            golden_set_candidate=row["golden_set_candidate"],
        )
