"""
Background cleanup tasks for indexing system.

Periodic maintenance tasks:
- Stale edge cleanup (TTL-based)
- Orphan node removal
- Cache invalidation
"""

import asyncio
from typing import TYPE_CHECKING

from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.graph.edge_validator import EdgeValidator

logger = get_logger(__name__)


class BackgroundCleanupService:
    """
    Background cleanup service for indexing maintenance.

    주요 기능:
    - Stale edge 주기적 정리 (TTL 만료 edge 삭제)
    - Orphan node 정리
    - 통계 수집 및 로깅
    """

    def __init__(
        self,
        edge_validator: "EdgeValidator",
        cleanup_interval_seconds: int = 3600,  # 1 hour
        graph_store=None,
        snapshot_gc=None,  # NEW: SnapshotGarbageCollector
    ):
        """
        Initialize background cleanup service.

        Args:
            edge_validator: EdgeValidator instance
            cleanup_interval_seconds: Cleanup interval (default: 1 hour)
            graph_store: Optional graph store for loading graphs
            snapshot_gc: Optional SnapshotGarbageCollector (NEW)
        """
        self.edge_validator = edge_validator
        self.cleanup_interval = cleanup_interval_seconds
        self.graph_store = graph_store
        self.snapshot_gc = snapshot_gc  # NEW
        self._task = None
        self._running = False
        self._stop_event = asyncio.Event()

    async def start(self):
        """Start background cleanup task."""
        if self._running:
            logger.warning("background_cleanup_already_running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            "background_cleanup_started",
            interval_seconds=self.cleanup_interval,
        )

    async def stop(self):
        """Stop background cleanup task."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("background_cleanup_stop_timeout")
                self._task.cancel()

        logger.info("background_cleanup_stopped")

    async def _cleanup_loop(self):
        """Main cleanup loop."""
        logger.info("background_cleanup_loop_started")

        while self._running:
            try:
                # Wait for interval or stop event
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.cleanup_interval)
                    # Stop event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout reached, perform cleanup
                    pass

                if not self._running:
                    break

                # Perform cleanup
                await self._run_cleanup()

            except Exception as e:
                logger.error(
                    "background_cleanup_error",
                    error=str(e),
                    exc_info=True,
                )
                # Continue running despite errors
                await asyncio.sleep(60)  # Wait 1 minute before retry

        logger.info("background_cleanup_loop_finished")

    async def _run_cleanup(self):
        """
        Run cleanup operations.

        - Cleanup stale edges for all repositories
        - Remove TTL-expired edges
        - Snapshot GC (NEW)
        - Log statistics
        """
        logger.info("background_cleanup_run_started")
        start_time = asyncio.get_event_loop().time()

        total_removed = 0
        repos_cleaned = 0
        total_snapshots_deleted = 0  # NEW

        try:
            # Get all repos with stale edges
            repo_ids = self._get_repos_with_stale_edges()

            for repo_id in repo_ids:
                try:
                    # Load graph if available
                    graph = None
                    if self.graph_store:
                        try:
                            graph = await self.graph_store.load_graph(repo_id)
                        except Exception as e:
                            logger.warning(
                                "failed_to_load_graph_for_cleanup",
                                repo_id=repo_id,
                                error=str(e),
                            )

                    # Cleanup stale edges (TTL-based)
                    removed = self.edge_validator.cleanup_stale_edges(
                        repo_id=repo_id,
                        graph=graph,
                        force=False,  # Use TTL and validation
                    )

                    if removed > 0:
                        total_removed += removed
                        repos_cleaned += 1
                        logger.info(
                            "repo_stale_edges_cleaned",
                            repo_id=repo_id,
                            removed=removed,
                        )

                except Exception as e:
                    logger.error(
                        "repo_cleanup_failed",
                        repo_id=repo_id,
                        error=str(e),
                        exc_info=True,
                    )
                    # Continue with other repos

            # NEW: Snapshot GC
            if self.snapshot_gc:
                try:
                    gc_stats = await self.snapshot_gc.cleanup_all_repos(dry_run=False)
                    total_snapshots_deleted = gc_stats.get("snapshots_deleted", 0)
                    logger.info("snapshot_gc_background_completed", **gc_stats)
                except Exception as e:
                    logger.error(
                        "snapshot_gc_background_failed",
                        error=str(e),
                        exc_info=True,
                    )

            elapsed = asyncio.get_event_loop().time() - start_time

            logger.info(
                "background_cleanup_run_completed",
                total_removed=total_removed,
                repos_cleaned=repos_cleaned,
                total_repos=len(repo_ids),
                snapshots_deleted=total_snapshots_deleted,
                elapsed_seconds=round(elapsed, 2),
            )

        except Exception as e:
            logger.error(
                "background_cleanup_run_failed",
                error=str(e),
                exc_info=True,
            )

    def _get_repos_with_stale_edges(self) -> list[str]:
        """
        Get list of repository IDs that have stale edges.

        Returns:
            List of repo IDs
        """
        # Access internal cache of EdgeValidator
        if hasattr(self.edge_validator, "_stale_cache"):
            return list(self.edge_validator._stale_cache.keys())
        return []

    async def cleanup_now(self, repo_id: str | None = None):
        """
        Trigger immediate cleanup (for testing/manual trigger).

        Args:
            repo_id: Optional repo ID to clean (None = all repos)
        """
        if repo_id:
            logger.info("manual_cleanup_triggered", repo_id=repo_id)

            # 1. Stale edge cleanup
            graph = None
            if self.graph_store:
                try:
                    graph = await self.graph_store.load_graph(repo_id)
                except Exception as e:
                    logger.warning("failed_to_load_graph", error=str(e))

            removed = self.edge_validator.cleanup_stale_edges(
                repo_id=repo_id,
                graph=graph,
                force=False,
            )

            # 2. Snapshot GC (NEW)
            gc_result = {}
            if self.snapshot_gc:
                try:
                    gc_result = await self.snapshot_gc.cleanup_repo(repo_id)
                    logger.info("snapshot_gc_manual_completed", repo_id=repo_id, **gc_result)
                except Exception as e:
                    logger.error("snapshot_gc_manual_failed", repo_id=repo_id, error=str(e))

            logger.info("manual_cleanup_completed", edges_removed=removed, **gc_result)
            return {"edges_removed": removed, "gc_result": gc_result}
        else:
            logger.info("manual_cleanup_all_triggered")
            await self._run_cleanup()


# ============================================================
# DEPRECATED: Global instance pattern
# Use RuntimeManager (src/platform/runtime.py) instead
# ============================================================

_cleanup_service: BackgroundCleanupService | None = None


def get_cleanup_service() -> BackgroundCleanupService | None:
    """
    Get global cleanup service instance.

    DEPRECATED: Use RuntimeManager.get_worker("cleanup_service") instead.
    """
    return _cleanup_service


def set_cleanup_service(service: BackgroundCleanupService):
    """
    Set global cleanup service instance.

    DEPRECATED: Use RuntimeManager.register_worker() instead.
    """
    global _cleanup_service
    _cleanup_service = service


async def start_background_cleanup(
    edge_validator: "EdgeValidator",
    cleanup_interval_seconds: int = 3600,
    graph_store=None,
    snapshot_gc=None,  # NEW: SnapshotGarbageCollector
) -> BackgroundCleanupService:
    """
    Start background cleanup service.

    DEPRECATED: Use PlatformContainer.create_background_cleanup_service()
                + RuntimeManager instead.

    Args:
        edge_validator: EdgeValidator instance
        cleanup_interval_seconds: Cleanup interval (default: 1 hour)
        graph_store: Optional graph store
        snapshot_gc: Optional SnapshotGarbageCollector (NEW)

    Returns:
        BackgroundCleanupService instance
    """
    service = BackgroundCleanupService(
        edge_validator=edge_validator,
        cleanup_interval_seconds=cleanup_interval_seconds,
        graph_store=graph_store,
        snapshot_gc=snapshot_gc,  # NEW
    )

    await service.start()
    set_cleanup_service(service)

    return service


async def stop_background_cleanup():
    """
    Stop background cleanup service.

    DEPRECATED: Use RuntimeManager.stop_all() instead.
    """
    service = get_cleanup_service()
    if service:
        await service.stop()
        set_cleanup_service(None)
