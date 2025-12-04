"""
PostgreSQL-based Correlation Index Adapter

Stores and queries symbol/file correlations:
- Co-change: Files that change together in git commits
- Co-occurrence: Symbols used together in same context

Schema:
    Table: symbol_correlations
        - id (serial primary key)
        - repo_id
        - source_id (file path or symbol FQN)
        - target_id (file path or symbol FQN)
        - correlation_type (co_change, co_occurrence, co_search)
        - strength (0.0 - 1.0)
        - count (observation count)
        - metadata (JSON)
        - updated_at
"""

import json
from pathlib import Path
from typing import Any

from src.common.observability import get_logger
from src.contexts.analysis_indexing.infrastructure.git_history.cochange import CoChangeAnalyzer
from src.contexts.multi_index.infrastructure.correlation.models import (
    CorrelationEntry,
    CorrelationSearchResult,
    CorrelationType,
)

logger = get_logger(__name__)


class CorrelationIndex:
    """
    Correlation index for tracking symbol/file relationships.

    Uses PostgreSQL for persistent storage of correlation data.

    Usage:
        correlation = CorrelationIndex(postgres_store, repo_path="/path/to/repo")

        # Build co-change correlations from git history
        await correlation.build_cochange_index(repo_id, days=90)

        # Build co-occurrence correlations from IR
        await correlation.build_cooccurrence_index(repo_id, snapshot_id, ir_docs)

        # Search for correlated entities
        results = await correlation.search(repo_id, "src/api.py", limit=10)
    """

    def __init__(self, postgres_store: Any, repo_path: str | Path | None = None):
        """
        Initialize correlation index.

        Args:
            postgres_store: PostgresStore instance with async connection pool
            repo_path: Path to git repository (for co-change analysis)
        """
        self.postgres = postgres_store
        self.repo_path = Path(repo_path) if repo_path else None
        self._table_name = "symbol_correlations"
        self._initialized = False

    # ============================================================
    # Co-change Index Building (from Git History)
    # ============================================================

    async def build_cochange_index(
        self,
        repo_id: str,
        days: int = 90,
        min_cochanges: int = 3,
        min_coupling: float = 0.2,
    ) -> int:
        """
        Build co-change correlations from git history.

        Uses CoChangeAnalyzer to find files that frequently change together.

        Args:
            repo_id: Repository identifier
            days: Number of days to analyze
            min_cochanges: Minimum co-change count to include
            min_coupling: Minimum coupling strength (0.0 - 1.0)

        Returns:
            Number of correlations created
        """
        if not self.repo_path:
            logger.warning("No repo_path configured, cannot build co-change index")
            return 0

        await self._ensure_schema()

        try:
            analyzer = CoChangeAnalyzer(self.repo_path)
            patterns = analyzer.find_strong_couples(
                days=days,
                min_cochanges=min_cochanges,
                min_coupling=min_coupling,
            )
        except ValueError as e:
            logger.error(f"Failed to analyze co-changes: {e}")
            return 0

        # Convert patterns to correlation entries
        entries = []
        for pattern in patterns:
            entry = CorrelationEntry(
                source_id=pattern.file_a,
                target_id=pattern.file_b,
                correlation_type=CorrelationType.CO_CHANGE,
                strength=pattern.coupling_strength,
                count=pattern.cochange_count,
                metadata={
                    "confidence_a_to_b": pattern.confidence_a_to_b,
                    "confidence_b_to_a": pattern.confidence_b_to_a,
                    "file_a_changes": pattern.file_a_changes,
                    "file_b_changes": pattern.file_b_changes,
                },
            )
            entries.append(entry)

        # Store correlations
        await self._upsert_correlations(repo_id, CorrelationType.CO_CHANGE, entries)

        logger.info(f"Built {len(entries)} co-change correlations for {repo_id}")
        return len(entries)

    # ============================================================
    # Co-occurrence Index Building (from IR/Graph)
    # ============================================================

    async def build_cooccurrence_index(
        self,
        repo_id: str,
        snapshot_id: str,
        references: list[dict[str, Any]],
        min_occurrences: int = 2,
    ) -> int:
        """
        Build co-occurrence correlations from symbol references.

        Tracks symbols that are used together in the same context
        (same file, same function, same class).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            references: List of reference records with:
                - source_fqn: FQN of the referencing symbol
                - target_fqn: FQN of the referenced symbol
                - context_fqn: FQN of the containing context
            min_occurrences: Minimum co-occurrences to store

        Returns:
            Number of correlations created
        """
        await self._ensure_schema()

        # Group references by context
        context_symbols: dict[str, set[str]] = {}
        for ref in references:
            context = ref.get("context_fqn") or ref.get("source_fqn", "")
            target = ref.get("target_fqn", "")
            if context and target:
                if context not in context_symbols:
                    context_symbols[context] = set()
                context_symbols[context].add(target)

        # Count co-occurrences
        pair_counts: dict[tuple[str, str], int] = {}
        for symbols in context_symbols.values():
            symbol_list = sorted(symbols)
            for i, sym_a in enumerate(symbol_list):
                for sym_b in symbol_list[i + 1 :]:
                    pair = (sym_a, sym_b)
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

        # Create correlation entries
        entries = []
        total_contexts = len(context_symbols)
        for (sym_a, sym_b), count in pair_counts.items():
            if count < min_occurrences:
                continue

            # Strength = Jaccard-like metric
            strength = count / total_contexts if total_contexts > 0 else 0.0

            entry = CorrelationEntry(
                source_id=sym_a,
                target_id=sym_b,
                correlation_type=CorrelationType.CO_OCCURRENCE,
                strength=min(strength * 10, 1.0),  # Scale up, cap at 1.0
                count=count,
                metadata={"snapshot_id": snapshot_id},
            )
            entries.append(entry)

        # Store correlations
        await self._upsert_correlations(repo_id, CorrelationType.CO_OCCURRENCE, entries)

        logger.info(f"Built {len(entries)} co-occurrence correlations for {repo_id}")
        return len(entries)

    # ============================================================
    # Search
    # ============================================================

    async def search(
        self,
        repo_id: str,
        entity_id: str,
        correlation_type: CorrelationType | None = None,
        limit: int = 20,
        min_strength: float = 0.0,
    ) -> list[CorrelationSearchResult]:
        """
        Find entities correlated with the given entity.

        Args:
            repo_id: Repository identifier
            entity_id: File path or symbol FQN to search for
            correlation_type: Filter by correlation type (optional)
            limit: Maximum results
            min_strength: Minimum correlation strength

        Returns:
            List of correlated entities sorted by strength
        """
        await self._ensure_schema()

        # Build query
        conditions = ["repo_id = $1", "(source_id = $2 OR target_id = $2)"]
        params: list[Any] = [repo_id, entity_id]
        param_idx = 3

        if correlation_type:
            conditions.append(f"correlation_type = ${param_idx}")
            params.append(correlation_type.value)
            param_idx += 1

        if min_strength > 0:
            conditions.append(f"strength >= ${param_idx}")
            params.append(min_strength)
            param_idx += 1

        sql = f"""
        SELECT
            source_id,
            target_id,
            correlation_type,
            strength,
            count,
            metadata
        FROM {self._table_name}
        WHERE {" AND ".join(conditions)}
        ORDER BY strength DESC, count DESC
        LIMIT ${param_idx}
        """
        params.append(limit)

        try:
            async with self.postgres.pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)

            results = []
            for row in rows:
                # Return the "other" entity
                other_id = row["target_id"] if row["source_id"] == entity_id else row["source_id"]
                result = CorrelationSearchResult(
                    entity_id=other_id,
                    correlation_type=CorrelationType(row["correlation_type"]),
                    strength=float(row["strength"]),
                    count=int(row["count"]),
                    metadata=row["metadata"] or {},
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Correlation search failed: {e}", exc_info=True)
            return []

    async def get_correlated_files(
        self,
        repo_id: str,
        file_path: str,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Get files correlated with the given file (convenience method).

        Args:
            repo_id: Repository identifier
            file_path: File path to search for
            limit: Maximum results

        Returns:
            List of (file_path, strength) tuples
        """
        results = await self.search(
            repo_id=repo_id,
            entity_id=file_path,
            correlation_type=CorrelationType.CO_CHANGE,
            limit=limit,
        )
        return [(r.entity_id, r.strength) for r in results]

    # ============================================================
    # Maintenance
    # ============================================================

    async def clear(self, repo_id: str, correlation_type: CorrelationType | None = None) -> int:
        """
        Clear correlations for a repository.

        Args:
            repo_id: Repository identifier
            correlation_type: Clear only this type (optional, clears all if None)

        Returns:
            Number of rows deleted
        """
        await self._ensure_schema()

        if correlation_type:
            sql = f"DELETE FROM {self._table_name} WHERE repo_id = $1 AND correlation_type = $2"
            params = [repo_id, correlation_type.value]
        else:
            sql = f"DELETE FROM {self._table_name} WHERE repo_id = $1"
            params = [repo_id]

        async with self.postgres.pool.acquire() as conn:
            result = await conn.execute(sql, *params)
            # Parse "DELETE n" result
            count = int(result.split()[-1]) if result else 0

        logger.info(f"Cleared {count} correlations for {repo_id}")
        return count

    # ============================================================
    # Private Helpers
    # ============================================================

    async def _ensure_schema(self) -> None:
        """Ensure correlation table exists."""
        if self._initialized:
            return

        await self.postgres._ensure_pool()

        async with self.postgres.pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_name} (
                    id SERIAL PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    correlation_type TEXT NOT NULL,
                    strength FLOAT DEFAULT 0.0,
                    count INTEGER DEFAULT 0,
                    metadata JSONB,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(repo_id, source_id, target_id, correlation_type)
                )
                """
            )

            # Create indexes
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_correlation_repo
                ON {self._table_name}(repo_id)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_correlation_source
                ON {self._table_name}(repo_id, source_id)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_correlation_target
                ON {self._table_name}(repo_id, target_id)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_correlation_type
                ON {self._table_name}(repo_id, correlation_type)
                """
            )
            await conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_correlation_strength
                ON {self._table_name}(repo_id, strength DESC)
                """
            )

        logger.info("Correlation index schema initialized")
        self._initialized = True

    async def _upsert_correlations(
        self,
        repo_id: str,
        correlation_type: CorrelationType,
        entries: list[CorrelationEntry],
    ) -> None:
        """Upsert correlation entries."""
        if not entries:
            return

        # Clear existing correlations of this type
        await self.clear(repo_id, correlation_type)

        # Prepare values
        values = [
            (
                repo_id,
                entry.source_id,
                entry.target_id,
                entry.correlation_type.value,
                entry.strength,
                entry.count,
                json.dumps(entry.metadata),
            )
            for entry in entries
        ]

        async with self.postgres.pool.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {self._table_name}
                (repo_id, source_id, target_id, correlation_type, strength, count, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (repo_id, source_id, target_id, correlation_type)
                DO UPDATE SET
                    strength = EXCLUDED.strength,
                    count = EXCLUDED.count,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                values,
            )


# ============================================================
# Factory
# ============================================================


def create_correlation_index(
    postgres_store: Any,
    repo_path: str | Path | None = None,
) -> CorrelationIndex:
    """
    Factory function for CorrelationIndex.

    Args:
        postgres_store: PostgresStore instance
        repo_path: Path to git repository (optional)

    Returns:
        Configured CorrelationIndex instance
    """
    return CorrelationIndex(postgres_store=postgres_store, repo_path=repo_path)
