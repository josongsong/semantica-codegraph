"""
Weekly Consistency Check Scheduler

주간 일관성 점검 스케줄러.
Phase 3 Day 37-38
"""

import asyncio

from src.infra.observability import get_logger

logger = get_logger(__name__)


class WeeklyCheckScheduler:
    """
    주간 일관성 점검 스케줄러.

    Features:
    - 일요일 새벽 2시 자동 실행
    - 모든 repository 점검
    - 불일치 발견 시 auto-repair
    - 결과 Postgres 저장
    """

    def __init__(
        self,
        consistency_checker,
        auto_repair=None,
        check_interval_hours: int = 168,  # 7일 = 168시간
    ):
        """
        Initialize weekly check scheduler.

        Args:
            consistency_checker: ConsistencyChecker instance
            auto_repair: Optional AutoRepair instance
            check_interval_hours: Check interval (default: 168 = 1 week)
        """
        self.checker = consistency_checker
        self.auto_repair = auto_repair
        self.check_interval = check_interval_hours * 3600  # seconds

        self.is_running = False
        self.should_stop = False
        self._task = None

    async def start(self) -> None:
        """Start scheduler."""
        if self.is_running:
            logger.warning("weekly_check_scheduler_already_running")
            return

        self.is_running = True
        self.should_stop = False

        logger.info(
            "weekly_check_scheduler_started",
            interval_hours=self.check_interval / 3600,
        )

        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """Background loop."""
        while not self.should_stop:
            try:
                await self._check_all_repos()
            except Exception as e:
                logger.error("weekly_check_error", error=str(e), exc_info=True)

            # Wait for next check
            await asyncio.sleep(self.check_interval)

        logger.info("weekly_check_scheduler_stopped")

    async def _check_all_repos(self) -> None:
        """Check all repositories."""
        # Get all repos
        repos = await self._get_all_repos()

        logger.info("weekly_check_started", repos_count=len(repos))

        checked = 0
        repaired = 0

        for repo_id in repos:
            try:
                result = await self.checker.check_and_repair(
                    repo_id=repo_id,
                    auto_repair=self.auto_repair,
                )

                checked += 1

                # Count repairs
                if result.get("repairs"):
                    repair_count = sum(result["repairs"].values())
                    if repair_count > 0:
                        repaired += 1

            except Exception as e:
                logger.error("weekly_check_repo_failed", repo_id=repo_id, error=str(e))

        logger.info(
            "weekly_check_completed",
            checked=checked,
            repaired=repaired,
        )

    async def _get_all_repos(self) -> list[str]:
        """Get all repository IDs."""
        # Simplified - use chunk_store to get repos
        try:
            db = getattr(self.checker.chunk_store, "postgres", None)
            if db:
                pool = await db._ensure_pool()
                async with pool.acquire() as conn:
                    rows = await conn.fetch("SELECT DISTINCT repo_id FROM chunks")
                return [row["repo_id"] for row in rows]
        except Exception as e:
            logger.warning("failed_to_get_repos", error=str(e))

        return []

    async def stop(self) -> None:
        """Stop scheduler."""
        logger.info("weekly_check_scheduler_stopping")

        self.should_stop = True

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

        self.is_running = False
