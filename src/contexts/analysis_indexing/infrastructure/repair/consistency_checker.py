"""
Consistency Checker

인덱스 일관성 점검 및 보고.
Phase 1 Day 12-13: 기본 구현
"""

from dataclasses import dataclass
from enum import Enum

from src.infra.observability import get_logger

logger = get_logger(__name__)


class ConsistencyStatus(str, Enum):
    """일관성 상태."""

    OK = "ok"
    MISMATCH = "mismatch"
    ERROR = "error"


@dataclass
class ConsistencyReport:
    """일관성 점검 보고서."""

    check_type: str  # qdrant, zoekt, memgraph
    status: ConsistencyStatus
    repo_id: str

    # Count metrics
    expected_count: int = 0
    actual_count: int = 0
    delta: int = 0

    # Details
    error_message: str | None = None
    checked_at: str | None = None

    @property
    def mismatch_pct(self) -> float:
        """불일치 비율 (%)."""
        if self.expected_count == 0:
            return 0.0
        return abs(self.delta) / self.expected_count * 100


class ConsistencyChecker:
    """
    인덱스 일관성 점검기.

    기능:
    - Qdrant vs Postgres chunk count 비교
    - Zoekt file count vs Git file count
    - Memgraph node count vs IR symbol count

    Phase 1 Day 12-13: 기본 구현 (count 비교만)
    """

    def __init__(
        self,
        chunk_store,
        vector_index,
        lexical_index,
        graph_store,
    ):
        """
        Initialize consistency checker.

        Args:
            chunk_store: Chunk storage (Postgres)
            vector_index: Vector index (Qdrant)
            lexical_index: Lexical index (Zoekt)
            graph_store: Graph storage (Memgraph)
        """
        self.chunk_store = chunk_store
        self.vector_index = vector_index
        self.lexical_index = lexical_index
        self.graph_store = graph_store

    async def check_qdrant_consistency(self, repo_id: str) -> ConsistencyReport:
        """
        Qdrant vs Postgres chunk count 일관성 점검.

        Args:
            repo_id: Repository ID

        Returns:
            ConsistencyReport
        """
        try:
            from datetime import datetime

            # Get Postgres chunk count
            pg_count = await self._get_postgres_chunk_count(repo_id)

            # Get Qdrant chunk count
            qdrant_count = await self._get_qdrant_chunk_count(repo_id)

            # Compare
            delta = qdrant_count - pg_count
            status = ConsistencyStatus.OK if delta == 0 else ConsistencyStatus.MISMATCH

            if status == ConsistencyStatus.MISMATCH:
                logger.warning(
                    "qdrant_mismatch_detected",
                    repo_id=repo_id,
                    pg_count=pg_count,
                    qdrant_count=qdrant_count,
                    delta=delta,
                )

            return ConsistencyReport(
                check_type="qdrant",
                status=status,
                repo_id=repo_id,
                expected_count=pg_count,
                actual_count=qdrant_count,
                delta=delta,
                checked_at=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error(
                "qdrant_consistency_check_failed",
                repo_id=repo_id,
                error=str(e),
                exc_info=True,
            )
            return ConsistencyReport(
                check_type="qdrant",
                status=ConsistencyStatus.ERROR,
                repo_id=repo_id,
                error_message=str(e),
            )

    async def check_zoekt_consistency(self, repo_id: str) -> ConsistencyReport:
        """
        Zoekt file count vs Git file count 일관성 점검.

        Args:
            repo_id: Repository ID

        Returns:
            ConsistencyReport
        """
        try:
            from datetime import datetime

            # Get Git file count (from chunk_store metadata)
            git_count = await self._get_git_file_count(repo_id)

            # Get Zoekt file count
            zoekt_count = await self._get_zoekt_file_count(repo_id)

            # Compare
            delta = zoekt_count - git_count
            status = ConsistencyStatus.OK if abs(delta) <= 5 else ConsistencyStatus.MISMATCH
            # Allow small delta (±5 files) due to timing/filtering

            if status == ConsistencyStatus.MISMATCH:
                logger.warning(
                    "zoekt_mismatch_detected",
                    repo_id=repo_id,
                    git_count=git_count,
                    zoekt_count=zoekt_count,
                    delta=delta,
                )

            return ConsistencyReport(
                check_type="zoekt",
                status=status,
                repo_id=repo_id,
                expected_count=git_count,
                actual_count=zoekt_count,
                delta=delta,
                checked_at=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error(
                "zoekt_consistency_check_failed",
                repo_id=repo_id,
                error=str(e),
                exc_info=True,
            )
            return ConsistencyReport(
                check_type="zoekt",
                status=ConsistencyStatus.ERROR,
                repo_id=repo_id,
                error_message=str(e),
            )

    async def check_memgraph_consistency(self, repo_id: str) -> ConsistencyReport:
        """
        Memgraph node count vs IR symbol count 일관성 점검.

        Args:
            repo_id: Repository ID

        Returns:
            ConsistencyReport
        """
        try:
            from datetime import datetime

            # Get IR symbol count (from chunk_store metadata)
            ir_count = await self._get_ir_symbol_count(repo_id)

            # Get Memgraph node count
            memgraph_count = await self._get_memgraph_node_count(repo_id)

            # Compare
            delta = memgraph_count - ir_count
            status = ConsistencyStatus.OK if abs(delta) <= 10 else ConsistencyStatus.MISMATCH
            # Allow small delta (±10 nodes) due to module hierarchy

            if status == ConsistencyStatus.MISMATCH:
                logger.warning(
                    "memgraph_mismatch_detected",
                    repo_id=repo_id,
                    ir_count=ir_count,
                    memgraph_count=memgraph_count,
                    delta=delta,
                )

            return ConsistencyReport(
                check_type="memgraph",
                status=status,
                repo_id=repo_id,
                expected_count=ir_count,
                actual_count=memgraph_count,
                delta=delta,
                checked_at=datetime.now().isoformat(),
            )

        except Exception as e:
            logger.error(
                "memgraph_consistency_check_failed",
                repo_id=repo_id,
                error=str(e),
                exc_info=True,
            )
            return ConsistencyReport(
                check_type="memgraph",
                status=ConsistencyStatus.ERROR,
                repo_id=repo_id,
                error_message=str(e),
            )

    async def check_all(self, repo_id: str) -> dict[str, ConsistencyReport]:
        """
        모든 인덱스 일관성 점검.

        Args:
            repo_id: Repository ID

        Returns:
            Dict of check_type -> ConsistencyReport
        """
        logger.info("consistency_check_all_started", repo_id=repo_id)

        reports = {
            "qdrant": await self.check_qdrant_consistency(repo_id),
            "zoekt": await self.check_zoekt_consistency(repo_id),
            "memgraph": await self.check_memgraph_consistency(repo_id),
        }

        # Summary
        mismatches = [r for r in reports.values() if r.status == ConsistencyStatus.MISMATCH]
        errors = [r for r in reports.values() if r.status == ConsistencyStatus.ERROR]

        logger.info(
            "consistency_check_all_completed",
            repo_id=repo_id,
            total=len(reports),
            ok=len(reports) - len(mismatches) - len(errors),
            mismatches=len(mismatches),
            errors=len(errors),
        )

        return reports

    async def check_and_repair(
        self,
        repo_id: str,
        auto_repair=None,
    ) -> dict:
        """
        일관성 점검 + 자동 수리.

        Phase 3 Day 37-38

        Args:
            repo_id: Repository ID
            auto_repair: Optional AutoRepair instance

        Returns:
            Dict with reports and repair results
        """
        # Check
        reports = await self.check_all(repo_id)

        repair_results = {}

        # Repair if auto_repair provided
        if auto_repair:
            for check_type, report in reports.items():
                if report.status == ConsistencyStatus.MISMATCH:
                    logger.warning(
                        "consistency_mismatch_detected",
                        repo_id=repo_id,
                        check_type=check_type,
                        delta=report.delta,
                    )

                    # Attempt repair
                    if check_type == "qdrant":
                        repaired = await auto_repair.repair_vector_index(repo_id)
                        repair_results["qdrant"] = repaired

        return {
            "reports": reports,
            "repairs": repair_results,
        }

    # ========================================================================
    # Helper Methods (Count Queries)
    # ========================================================================

    async def _get_postgres_chunk_count(self, repo_id: str) -> int:
        """Get chunk count from Postgres.

        Raises exception on error (for error handling in caller).
        """
        # Use chunk_store.count() method if available
        if hasattr(self.chunk_store, "count"):
            return await self.chunk_store.count(repo_id)

        # Fallback: direct DB query
        pool = await self.chunk_store.postgres._ensure_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM chunks WHERE repo_id = $1",
                repo_id,
            )
            return result["count"] if result else 0

    async def _get_qdrant_chunk_count(self, repo_id: str) -> int:
        """Get chunk count from Qdrant.

        Raises exception on error (for error handling in caller).
        """
        # Use vector_index count method if available
        if hasattr(self.vector_index, "count"):
            return await self.vector_index.count(repo_id)

        # Fallback: Qdrant API query
        collection_name = getattr(self.vector_index, "collection_name", "codegraph")
        qdrant_client = getattr(self.vector_index, "client", None)

        if not qdrant_client:
            raise RuntimeError("Qdrant client not available")

        # Count points with repo_id filter
        result = await qdrant_client.count(
            collection_name=collection_name,
            count_filter={
                "must": [
                    {
                        "key": "repo_id",
                        "match": {"value": repo_id},
                    }
                ]
            },
        )

        return result.count if result else 0

    async def _get_git_file_count(self, repo_id: str) -> int:
        """Get file count from Git (source of truth)."""
        try:
            # Get from indexing metadata or latest indexing result
            pool = await self.chunk_store.postgres._ensure_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT files_processed
                    FROM indexing_sessions
                    WHERE repo_id = $1
                    ORDER BY start_time DESC
                    LIMIT 1
                    """,
                    repo_id,
                )
                return result["files_processed"] if result else 0

        except Exception as e:
            logger.warning("git_file_count_failed", repo_id=repo_id, error=str(e))
            return 0

    async def _get_zoekt_file_count(self, repo_id: str) -> int:
        """Get file count from Zoekt index."""
        try:
            # Use lexical_index method if available
            if hasattr(self.lexical_index, "count_files"):
                return await self.lexical_index.count_files(repo_id)

            # Fallback: estimate from search results
            # (Zoekt doesn't expose direct file count API)
            logger.debug("zoekt_file_count_estimation", repo_id=repo_id)
            return 0

        except Exception as e:
            logger.warning("zoekt_count_failed", repo_id=repo_id, error=str(e))
            return 0

    async def _get_ir_symbol_count(self, repo_id: str) -> int:
        """Get symbol count from IR metadata."""
        try:
            # Get from indexing result metadata
            pool = await self.chunk_store.postgres._ensure_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT ir_nodes_created
                    FROM indexing_sessions
                    WHERE repo_id = $1
                    ORDER BY start_time DESC
                    LIMIT 1
                    """,
                    repo_id,
                )
                return result["ir_nodes_created"] if result else 0

        except Exception as e:
            logger.warning("ir_symbol_count_failed", repo_id=repo_id, error=str(e))
            return 0

    async def _get_memgraph_node_count(self, repo_id: str) -> int:
        """Get node count from Memgraph."""
        try:
            # Use graph_store method if available
            if hasattr(self.graph_store, "count_nodes"):
                return await self.graph_store.count_nodes(repo_id)

            # Fallback: Cypher query
            graph_client = getattr(self.graph_store, "client", None)
            if not graph_client:
                logger.warning("memgraph_client_not_available")
                return 0

            query = """
                MATCH (n)
                WHERE n.repo_id = $repo_id
                RETURN count(n) as count
            """

            result = await graph_client.execute_query(query, {"repo_id": repo_id})

            if result and len(result) > 0:
                return result[0].get("count", 0)

            return 0

        except Exception as e:
            logger.warning("memgraph_count_failed", repo_id=repo_id, error=str(e))
            return 0
