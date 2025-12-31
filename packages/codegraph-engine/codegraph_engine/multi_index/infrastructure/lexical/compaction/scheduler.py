"""
Compaction Scheduler

주기적으로 Delta compaction 필요 여부를 체크하고 실행합니다.
Phase 1 Day 11: 백그라운드 스케줄러 연동
"""

import asyncio

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class CompactionScheduler:
    """
    주기적 Compaction 스케줄러.

    기능:
    - 주기적으로 should_compact() 체크
    - 조건 만족 시 compaction 실행
    - 백그라운드 실행 (non-blocking)
    """

    def __init__(
        self,
        compaction_manager,
        check_interval_seconds: int = 3600,  # 1시간
        repos_to_monitor: list[str] | None = None,
    ):
        """
        Initialize compaction scheduler.

        Args:
            compaction_manager: CompactionManager instance
            check_interval_seconds: Check interval (default: 3600 = 1 hour)
            repos_to_monitor: List of repo IDs to monitor (None = all)
        """
        self.compaction_manager = compaction_manager
        self.check_interval = check_interval_seconds
        self.repos = repos_to_monitor or []

        self.is_running = False
        self.should_stop = False
        self._task = None

    async def start(self) -> None:
        """Start background scheduler."""
        if self.is_running:
            logger.warning("compaction_scheduler_already_running")
            return

        self.is_running = True
        self.should_stop = False

        logger.info(
            "compaction_scheduler_started",
            check_interval=self.check_interval,
            repos=len(self.repos) if self.repos else "all",
        )

        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Background loop."""
        while not self.should_stop:
            try:
                await self._check_and_compact_all()
            except Exception as e:
                logger.error(
                    "compaction_scheduler_error",
                    error=str(e),
                    exc_info=True,
                )

            # Wait for next check interval
            await asyncio.sleep(self.check_interval)

        logger.info("compaction_scheduler_stopped")

    async def _check_and_compact_all(self) -> None:
        """Check and compact all monitored repositories."""
        repos_to_check = self.repos if self.repos else await self._get_all_repos()

        logger.debug(
            "compaction_check_started",
            repos_count=len(repos_to_check),
        )

        compacted_count = 0
        failed_count = 0

        for repo_id in repos_to_check:
            try:
                should_compact = await self.compaction_manager.should_compact(repo_id)

                if should_compact:
                    logger.info(
                        "compaction_starting",
                        repo_id=repo_id,
                    )

                    # Get snapshot_id (default to "main" or latest)
                    snapshot_id = await self._get_snapshot_id(repo_id)

                    success = await self.compaction_manager.compact(repo_id, snapshot_id)

                    if success:
                        compacted_count += 1
                        logger.info(
                            "compaction_completed",
                            repo_id=repo_id,
                        )
                    else:
                        failed_count += 1
                        logger.warning(
                            "compaction_failed",
                            repo_id=repo_id,
                        )

            except Exception as e:
                failed_count += 1
                logger.error(
                    "compaction_check_failed",
                    repo_id=repo_id,
                    error=str(e),
                )

        logger.info(
            "compaction_check_completed",
            total=len(repos_to_check),
            compacted=compacted_count,
            failed=failed_count,
        )

    async def _get_all_repos(self) -> list[str]:
        """
        Get all repository IDs from database.

        Returns:
            List of repo IDs
        """
        # Access delta index's database
        db = getattr(self.compaction_manager.delta, "db", None)
        if not db:
            return []

        try:
            query = """
                SELECT DISTINCT repo_id
                FROM delta_lexical_index
                WHERE NOT deleted
            """

            pool = await db._ensure_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(query)

            return [row["repo_id"] for row in rows]
        except Exception as e:
            logger.warning("failed_to_get_repos", error=str(e))
            return []

    async def _get_snapshot_id(self, repo_id: str) -> str:
        """
        Get latest snapshot ID for repository.

        Args:
            repo_id: Repository ID

        Returns:
            Snapshot ID (default: "main")
        """
        db = getattr(self.compaction_manager.delta, "db", None)
        if not db:
            return "main"

        try:
            query = """
                SELECT snapshot_id
                FROM delta_lexical_index
                WHERE repo_id = $1 AND NOT deleted
                ORDER BY indexed_at DESC
                LIMIT 1
            """
            pool = await db._ensure_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, repo_id)
                if row and row["snapshot_id"]:
                    return row["snapshot_id"]
        except Exception as e:
            logger.debug(f"snapshot_id_lookup_failed: {e}")

        return "main"

    async def stop(self) -> None:
        """Stop background scheduler."""
        logger.info("compaction_scheduler_stopping")

        self.should_stop = True

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("compaction_scheduler_stop_timeout")
                self._task.cancel()

        self.is_running = False
        logger.info("compaction_scheduler_stopped")

    def add_repo(self, repo_id: str) -> None:
        """Add repository to monitoring list."""
        if repo_id not in self.repos:
            self.repos.append(repo_id)
            logger.info("repo_added_to_compaction_monitor", repo_id=repo_id)

    def remove_repo(self, repo_id: str) -> None:
        """Remove repository from monitoring list."""
        if repo_id in self.repos:
            self.repos.remove(repo_id)
            logger.info("repo_removed_from_compaction_monitor", repo_id=repo_id)


# Global scheduler instance
_compaction_scheduler: CompactionScheduler | None = None


def get_compaction_scheduler() -> CompactionScheduler | None:
    """Get global compaction scheduler instance."""
    return _compaction_scheduler


def setup_compaction_scheduler(
    compaction_manager,
    check_interval_seconds: int = 3600,
    repos_to_monitor: list[str] | None = None,
) -> CompactionScheduler:
    """
    Setup global compaction scheduler.

    Args:
        compaction_manager: CompactionManager instance
        check_interval_seconds: Check interval (default: 1 hour)
        repos_to_monitor: List of repo IDs (None = all)

    Returns:
        CompactionScheduler instance
    """
    global _compaction_scheduler

    if _compaction_scheduler is not None:
        logger.warning("compaction_scheduler_already_setup")
        return _compaction_scheduler

    _compaction_scheduler = CompactionScheduler(
        compaction_manager=compaction_manager,
        check_interval_seconds=check_interval_seconds,
        repos_to_monitor=repos_to_monitor,
    )

    logger.info(
        "compaction_scheduler_setup_complete",
        check_interval=check_interval_seconds,
    )

    return _compaction_scheduler


async def start_compaction_scheduler() -> None:
    """Start global compaction scheduler."""
    if _compaction_scheduler:
        await _compaction_scheduler.start()
    else:
        logger.warning("compaction_scheduler_not_setup")


async def stop_compaction_scheduler() -> None:
    """Stop global compaction scheduler."""
    if _compaction_scheduler:
        await _compaction_scheduler.stop()
