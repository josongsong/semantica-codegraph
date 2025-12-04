"""
Golden Set Service

Manages golden set queries for retrieval evaluation.

Responsibilities:
- Add/update/delete golden set queries
- Load queries by intent, difficulty, repo
- Track usage statistics
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from src.common.observability import get_logger
from src.contexts.retrieval_search.infrastructure.evaluation.models import (
    AnnotationQuality,
    GoldenSetQuery,
    QueryDifficulty,
    QueryIntent,
    QuerySource,
)
from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class GoldenSetService:
    """
    Service for managing golden set queries.

    Uses PostgreSQL (golden_set_queries table) for persistence.
    """

    def __init__(self, postgres: PostgresStore):
        """
        Initialize golden set service.

        Args:
            postgres: PostgreSQL storage instance
        """
        self.postgres = postgres

    async def add_query(
        self,
        query: str,
        intent: QueryIntent,
        relevant_chunk_ids: list[str],
        difficulty: QueryDifficulty = QueryDifficulty.MEDIUM,
        source: QuerySource = QuerySource.MANUAL,
        repo_id: str | None = None,
        annotator_id: str | None = None,
        annotation_quality: AnnotationQuality = AnnotationQuality.UNVERIFIED,
        review_notes: str | None = None,
    ) -> GoldenSetQuery:
        """
        Add a new golden set query.

        Args:
            query: Natural language query text
            intent: Query intent category
            relevant_chunk_ids: Ground truth chunk IDs
            difficulty: Query difficulty level
            source: How query was created
            repo_id: Optional repository ID
            annotator_id: Who annotated this query
            annotation_quality: Quality level
            review_notes: Optional review notes

        Returns:
            Created GoldenSetQuery
        """
        golden_query = GoldenSetQuery(
            query=query,
            intent=intent,
            relevant_chunk_ids=relevant_chunk_ids,
            difficulty=difficulty,
            source=source,
            repo_id=repo_id,
            annotator_id=annotator_id,
            annotation_quality=annotation_quality,
            review_notes=review_notes,
        )

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO golden_set_queries (
                    query_id, query, intent, relevant_chunk_ids,
                    difficulty, source, repo_id,
                    annotation_quality, annotator_id, review_notes,
                    created_at, updated_at,
                    evaluation_count, last_evaluated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 0, NULL
                )
                """,
                str(golden_query.query_id),
                golden_query.query,
                golden_query.intent,  # Already string due to use_enum_values
                json.dumps(golden_query.relevant_chunk_ids),
                golden_query.difficulty,  # Already string due to use_enum_values
                golden_query.source,  # Already string due to use_enum_values
                golden_query.repo_id,
                golden_query.annotation_quality,  # Already string due to use_enum_values
                golden_query.annotator_id,
                golden_query.review_notes,
                golden_query.created_at,
                golden_query.updated_at,
            )

        logger.info(
            f"Added golden set query: {golden_query.query_id} ({golden_query.intent}, {golden_query.difficulty})"
        )
        return golden_query

    async def get_query(self, query_id: UUID | str) -> GoldenSetQuery | None:
        """
        Get a golden set query by ID.

        Args:
            query_id: Query UUID

        Returns:
            GoldenSetQuery if found, None otherwise
        """
        query_id_str = str(query_id)

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM golden_set_queries
                WHERE query_id = $1
                """,
                query_id_str,
            )

        if not row:
            return None

        return self._golden_query_from_row(row)

    async def list_queries(
        self,
        intent: QueryIntent | None = None,
        difficulty: QueryDifficulty | None = None,
        repo_id: str | None = None,
        annotation_quality: AnnotationQuality | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GoldenSetQuery]:
        """
        List golden set queries with filtering.

        Args:
            intent: Filter by intent
            difficulty: Filter by difficulty
            repo_id: Filter by repository
            annotation_quality: Filter by quality
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of GoldenSetQuery objects
        """
        # Build WHERE clauses
        conditions = []
        params = []
        param_idx = 1

        if intent:
            conditions.append(f"intent = ${param_idx}")
            params.append(intent.value)
            param_idx += 1

        if difficulty:
            conditions.append(f"difficulty = ${param_idx}")
            params.append(difficulty.value)
            param_idx += 1

        if repo_id:
            conditions.append(f"repo_id = ${param_idx}")
            params.append(repo_id)
            param_idx += 1

        if annotation_quality:
            conditions.append(f"annotation_quality = ${param_idx}")
            params.append(annotation_quality.value)
            param_idx += 1

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # Add pagination
        params.extend([limit, offset])
        limit_clause = f"LIMIT ${param_idx} OFFSET ${param_idx + 1}"

        query = f"""
            SELECT * FROM golden_set_queries
            {where_clause}
            ORDER BY created_at DESC
            {limit_clause}
        """

        async with self.postgres.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._golden_query_from_row(row) for row in rows]

    async def update_query(
        self,
        query_id: UUID | str,
        **updates: Any,
    ) -> GoldenSetQuery | None:
        """
        Update a golden set query.

        Args:
            query_id: Query UUID
            **updates: Fields to update

        Returns:
            Updated GoldenSetQuery if found, None otherwise
        """
        query_id_str = str(query_id)

        # Build UPDATE SET clause
        set_clauses = []
        params = []
        param_idx = 1

        allowed_fields = {
            "query",
            "intent",
            "relevant_chunk_ids",
            "difficulty",
            "source",
            "repo_id",
            "annotation_quality",
            "annotator_id",
            "review_notes",
        }

        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ${param_idx}")

                # Handle special serialization
                if field == "relevant_chunk_ids":
                    params.append(json.dumps(value))
                elif field in ["intent", "difficulty", "source", "annotation_quality"]:
                    params.append(value.value if hasattr(value, "value") else value)
                else:
                    params.append(value)

                param_idx += 1

        if not set_clauses:
            # No valid updates
            return await self.get_query(query_id)

        # Always update updated_at
        set_clauses.append(f"updated_at = ${param_idx}")
        params.append(datetime.now())
        param_idx += 1

        # Add query_id as last parameter
        params.append(query_id_str)

        update_query = f"""
            UPDATE golden_set_queries
            SET {", ".join(set_clauses)}
            WHERE query_id = ${param_idx}
            RETURNING *
        """

        async with self.postgres.pool.acquire() as conn:
            row = await conn.fetchrow(update_query, *params)

        if not row:
            return None

        logger.info(f"Updated golden set query: {query_id_str}")
        return self._golden_query_from_row(row)

    async def delete_query(self, query_id: UUID | str) -> bool:
        """
        Delete a golden set query.

        Args:
            query_id: Query UUID

        Returns:
            True if deleted, False if not found
        """
        query_id_str = str(query_id)

        async with self.postgres.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM golden_set_queries
                WHERE query_id = $1
                """,
                query_id_str,
            )

        deleted = result.split()[-1] == "1"  # "DELETE 1"

        if deleted:
            logger.info(f"Deleted golden set query: {query_id_str}")

        return deleted

    async def increment_usage(self, query_id: UUID | str):
        """
        Increment usage count for a query.

        Args:
            query_id: Query UUID
        """
        query_id_str = str(query_id)

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE golden_set_queries
                SET evaluation_count = evaluation_count + 1,
                    last_evaluated_at = NOW()
                WHERE query_id = $1
                """,
                query_id_str,
            )

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get golden set statistics.

        Returns:
            Dict with statistics:
            - total_queries
            - by_intent
            - by_difficulty
            - by_quality
            - by_source
        """
        async with self.postgres.pool.acquire() as conn:
            # Total count
            total_row = await conn.fetchrow("SELECT COUNT(*) as count FROM golden_set_queries")
            total = total_row["count"]

            # By intent
            intent_rows = await conn.fetch(
                """
                SELECT intent, COUNT(*) as count
                FROM golden_set_queries
                GROUP BY intent
                ORDER BY count DESC
                """
            )
            by_intent = {row["intent"]: row["count"] for row in intent_rows}

            # By difficulty
            difficulty_rows = await conn.fetch(
                """
                SELECT difficulty, COUNT(*) as count
                FROM golden_set_queries
                GROUP BY difficulty
                ORDER BY count DESC
                """
            )
            by_difficulty = {row["difficulty"]: row["count"] for row in difficulty_rows}

            # By quality
            quality_rows = await conn.fetch(
                """
                SELECT annotation_quality, COUNT(*) as count
                FROM golden_set_queries
                GROUP BY annotation_quality
                ORDER BY count DESC
                """
            )
            by_quality = {row["annotation_quality"]: row["count"] for row in quality_rows}

            # By source
            source_rows = await conn.fetch(
                """
                SELECT source, COUNT(*) as count
                FROM golden_set_queries
                GROUP BY source
                ORDER BY count DESC
                """
            )
            by_source = {row["source"]: row["count"] for row in source_rows}

        return {
            "total_queries": total,
            "by_intent": by_intent,
            "by_difficulty": by_difficulty,
            "by_quality": by_quality,
            "by_source": by_source,
        }

    def _golden_query_from_row(self, row) -> GoldenSetQuery:
        """Convert database row to GoldenSetQuery model."""
        # asyncpg returns UUID objects, convert to str first
        query_id_val = row["query_id"]
        if not isinstance(query_id_val, UUID):
            query_id_val = UUID(str(query_id_val))

        return GoldenSetQuery(
            query_id=query_id_val,
            query=row["query"],
            intent=QueryIntent(row["intent"]),
            relevant_chunk_ids=json.loads(row["relevant_chunk_ids"])
            if isinstance(row["relevant_chunk_ids"], str)
            else row["relevant_chunk_ids"],
            difficulty=QueryDifficulty(row["difficulty"]),
            source=QuerySource(row["source"]),
            repo_id=row["repo_id"],
            annotation_quality=AnnotationQuality(row["annotation_quality"]),
            annotator_id=row["annotator_id"],
            review_notes=row["review_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            evaluation_count=row["evaluation_count"],
            last_evaluated_at=row["last_evaluated_at"],
        )
