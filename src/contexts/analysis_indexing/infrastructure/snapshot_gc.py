"""
Snapshot Garbage Collection Service

스냅샷 정리 정책:
- 최근 N개의 스냅샷만 유지
- 오래된 스냅샷 자동 삭제
- 관련 데이터 cascade 삭제 (chunks, mappings, graph nodes)
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from src.common.observability import get_logger, record_counter

if TYPE_CHECKING:
    from src.infra.graph.memgraph import MemgraphGraphStore
    from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class SnapshotRetentionPolicy:
    """스냅샷 보관 정책"""

    def __init__(
        self,
        keep_latest_count: int = 10,
        keep_days: int = 30,
        keep_tagged: bool = True,
    ):
        """
        Args:
            keep_latest_count: 최소 유지할 최신 스냅샷 개수
            keep_days: 최소 유지 기간 (일)
            keep_tagged: 태그된 스냅샷 영구 보관 여부
        """
        self.keep_latest_count = keep_latest_count
        self.keep_days = keep_days
        self.keep_tagged = keep_tagged

    def should_delete(
        self,
        snapshot_id: str,
        created_at: datetime,
        is_tagged: bool,
        rank: int,
    ) -> bool:
        """
        스냅샷 삭제 여부 판단.

        Args:
            snapshot_id: 스냅샷 ID
            created_at: 생성 시간
            is_tagged: 태그 여부
            rank: 최신순 순위 (1부터 시작)

        Returns:
            True if should delete
        """
        # 태그된 스냅샷은 유지
        if is_tagged and self.keep_tagged:
            return False

        # 최신 N개는 유지
        if rank <= self.keep_latest_count:
            return False

        # 최근 N일 이내는 유지
        age_days = (datetime.now() - created_at).days
        if age_days < self.keep_days:
            return False

        return True


class SnapshotGarbageCollector:
    """
    스냅샷 자동 정리 서비스.

    주요 기능:
    - 오래된 스냅샷 자동 삭제
    - 관련 데이터 cascade 삭제
    - 정리 통계 수집
    - 백그라운드 스케줄링

    Usage:
        gc = SnapshotGarbageCollector(
            postgres_store=postgres,
            graph_store=graph_store,
            policy=SnapshotRetentionPolicy(keep_latest_count=10, keep_days=30)
        )

        # 수동 실행
        result = await gc.cleanup_repo(repo_id="my-repo")
        print(f"Deleted {result['snapshots_deleted']} snapshots")

        # 자동 스케줄링
        task = gc.start_background_cleanup(interval_hours=24)
    """

    def __init__(
        self,
        postgres_store: "PostgresStore",
        graph_store: "MemgraphGraphStore | None" = None,
        policy: SnapshotRetentionPolicy | None = None,
    ):
        """
        Args:
            postgres_store: PostgreSQL 저장소
            graph_store: Memgraph 저장소 (optional)
            policy: 보관 정책 (default: 최근 10개, 30일)
        """
        self.postgres = postgres_store
        self.graph_store = graph_store
        self.policy = policy or SnapshotRetentionPolicy()
        self._cleanup_task: asyncio.Task | None = None

    async def cleanup_repo(self, repo_id: str, dry_run: bool = False) -> dict:
        """
        레포지토리의 오래된 스냅샷 정리.

        Args:
            repo_id: 레포지토리 ID
            dry_run: True면 실제 삭제 안 하고 통계만 반환

        Returns:
            정리 통계 딕셔너리
        """
        logger.info("snapshot_gc_started", repo_id=repo_id, dry_run=dry_run)

        # 스냅샷 목록 조회 (최신순)
        snapshots = await self._list_snapshots(repo_id)

        if not snapshots:
            logger.info("snapshot_gc_no_snapshots", repo_id=repo_id)
            return {"snapshots_deleted": 0, "chunks_deleted": 0, "nodes_deleted": 0}

        # 삭제 대상 결정
        to_delete = []
        for rank, snapshot in enumerate(snapshots, start=1):
            if self.policy.should_delete(
                snapshot_id=snapshot["snapshot_id"],
                created_at=snapshot["created_at"],
                is_tagged=snapshot.get("is_tagged", False),
                rank=rank,
            ):
                to_delete.append(snapshot["snapshot_id"])

        logger.info(
            "snapshot_gc_candidates",
            repo_id=repo_id,
            total_snapshots=len(snapshots),
            to_delete_count=len(to_delete),
        )

        if not to_delete:
            return {"snapshots_deleted": 0, "chunks_deleted": 0, "nodes_deleted": 0}

        if dry_run:
            return {
                "snapshots_deleted": len(to_delete),
                "snapshot_ids": to_delete,
                "dry_run": True,
            }

        # 실제 삭제
        chunks_deleted = 0
        nodes_deleted = 0

        for snapshot_id in to_delete:
            result = await self._delete_snapshot(repo_id, snapshot_id)
            chunks_deleted += result["chunks_deleted"]
            nodes_deleted += result["nodes_deleted"]

        logger.info(
            "snapshot_gc_completed",
            repo_id=repo_id,
            snapshots_deleted=len(to_delete),
            chunks_deleted=chunks_deleted,
            nodes_deleted=nodes_deleted,
        )

        record_counter("snapshot_gc_runs_total", 1)
        record_counter("snapshot_gc_snapshots_deleted_total", len(to_delete))

        return {
            "snapshots_deleted": len(to_delete),
            "snapshot_ids": to_delete,
            "chunks_deleted": chunks_deleted,
            "nodes_deleted": nodes_deleted,
        }

    async def _list_snapshots(self, repo_id: str) -> list[dict]:
        """
        레포지토리의 모든 스냅샷 목록 조회 (최신순).

        Returns:
            List of {snapshot_id, created_at, is_tagged}
        """
        pool = await self.postgres._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT snapshot_id, created_at,
                       COALESCE((attrs->>'is_tagged')::boolean, FALSE) as is_tagged
                FROM chunks
                WHERE repo_id = $1 AND is_deleted = FALSE
                ORDER BY created_at DESC
                """,
                repo_id,
            )

            return [dict(row) for row in rows]

    async def _delete_snapshot(self, repo_id: str, snapshot_id: str) -> dict:
        """
        스냅샷 및 관련 데이터 삭제.

        Cascade 삭제 순서:
        1. Chunk mappings (IR, Graph)
        2. Chunks
        3. Graph nodes/edges (Memgraph)
        4. Pyright snapshots
        5. Indexing metadata (snapshot 기록)

        Args:
            repo_id: 레포지토리 ID
            snapshot_id: 스냅샷 ID

        Returns:
            삭제 통계
        """
        chunks_deleted = 0
        nodes_deleted = 0

        pool = await self.postgres._ensure_pool()
        async with pool.acquire() as conn:
            # 1. IR mappings 삭제
            try:
                await conn.execute(
                    """
                    DELETE FROM chunk_to_ir_mappings
                    WHERE chunk_id IN (
                        SELECT chunk_id FROM chunks
                        WHERE repo_id = $1 AND snapshot_id = $2
                    )
                    """,
                    repo_id,
                    snapshot_id,
                )
            except Exception as e:
                logger.warning("ir_mappings_delete_failed", error=str(e))

            # 2. Graph mappings 삭제
            try:
                await conn.execute(
                    """
                    DELETE FROM chunk_to_graph_mappings
                    WHERE chunk_id IN (
                        SELECT chunk_id FROM chunks
                        WHERE repo_id = $1 AND snapshot_id = $2
                    )
                    """,
                    repo_id,
                    snapshot_id,
                )
            except Exception as e:
                logger.warning("graph_mappings_delete_failed", error=str(e))

            # 3. Chunks 삭제 (soft delete)
            result = await conn.execute(
                """
                UPDATE chunks
                SET is_deleted = TRUE, updated_at = NOW()
                WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE
                """,
                repo_id,
                snapshot_id,
            )
            chunks_deleted = int(result.split()[-1]) if result else 0

            # 4. Pyright snapshots 삭제
            try:
                await conn.execute(
                    "DELETE FROM pyright_semantic_snapshots WHERE snapshot_id = $1",
                    snapshot_id,
                )
            except Exception as e:
                logger.warning("pyright_snapshot_delete_failed", error=str(e))

            # 5. RepoMap nodes 삭제
            try:
                await conn.execute(
                    "DELETE FROM repomap_nodes WHERE repo_id = $1 AND snapshot_id = $2",
                    repo_id,
                    snapshot_id,
                )
            except Exception as e:
                logger.warning("repomap_nodes_delete_failed", error=str(e))

        # 6. Graph DB 삭제 (Memgraph)
        if self.graph_store:
            try:
                result = await self.graph_store.delete_snapshot(repo_id, snapshot_id)
                nodes_deleted = result.get("nodes", 0)
            except Exception as e:
                logger.warning("graph_snapshot_delete_failed", error=str(e))

        logger.info(
            "snapshot_deleted",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            chunks_deleted=chunks_deleted,
            nodes_deleted=nodes_deleted,
        )

        return {"chunks_deleted": chunks_deleted, "nodes_deleted": nodes_deleted}

    def start_background_cleanup(self, interval_hours: int = 24) -> asyncio.Task:
        """
        백그라운드에서 주기적으로 스냅샷 정리.

        Args:
            interval_hours: 정리 주기 (시간)

        Returns:
            asyncio.Task
        """
        if self._cleanup_task and not self._cleanup_task.done():
            logger.warning("background_cleanup_already_running")
            return self._cleanup_task

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)

                    # 모든 레포지토리 정리
                    repos = await self._list_repos()
                    for repo_id in repos:
                        try:
                            await self.cleanup_repo(repo_id)
                        except Exception as e:
                            logger.error(
                                "snapshot_gc_failed",
                                repo_id=repo_id,
                                error=str(e),
                                exc_info=True,
                            )

                except asyncio.CancelledError:
                    logger.info("background_cleanup_cancelled")
                    break
                except Exception as e:
                    logger.error("background_cleanup_error", error=str(e), exc_info=True)

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("background_cleanup_started", interval_hours=interval_hours)
        return self._cleanup_task

    def stop_background_cleanup(self):
        """백그라운드 정리 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("background_cleanup_stopped")

    async def _list_repos(self) -> list[str]:
        """모든 레포지토리 ID 목록 조회"""
        pool = await self.postgres._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT repo_id
                FROM chunks
                WHERE is_deleted = FALSE
                """
            )
            return [row["repo_id"] for row in rows]

    async def cleanup_all_repos(self, dry_run: bool = False) -> dict:
        """
        모든 레포지토리의 스냅샷 정리.

        Args:
            dry_run: True면 실제 삭제 안 함

        Returns:
            전체 통계
        """
        repos = await self._list_repos()
        total_stats = {
            "repos_processed": 0,
            "snapshots_deleted": 0,
            "chunks_deleted": 0,
            "nodes_deleted": 0,
        }

        for repo_id in repos:
            try:
                result = await self.cleanup_repo(repo_id, dry_run=dry_run)
                total_stats["repos_processed"] += 1
                total_stats["snapshots_deleted"] += result.get("snapshots_deleted", 0)
                total_stats["chunks_deleted"] += result.get("chunks_deleted", 0)
                total_stats["nodes_deleted"] += result.get("nodes_deleted", 0)
            except Exception as e:
                logger.error("snapshot_gc_repo_failed", repo_id=repo_id, error=str(e))

        logger.info("snapshot_gc_all_completed", **total_stats)
        return total_stats
