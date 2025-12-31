"""
Background Jobs Scheduler

백그라운드 작업 스케줄링 및 실행 관리.
"""

import asyncio
from datetime import datetime, timezone

from codegraph_shared.common.observability import get_logger
from codegraph_engine.analysis_indexing.infrastructure.jobs.embedding_refresh import EmbeddingRefreshJob
from codegraph_engine.analysis_indexing.infrastructure.jobs.repomap_rebuild import RepoMapRebuildJob

logger = get_logger(__name__)


class BackgroundJobsScheduler:
    """
    백그라운드 작업 스케줄러.

    실행 시점:
    - Embedding Refresh: 매주 일요일 02:00 (주간)
    - RepoMap Rebuild: 매일 03:00 (Nightly)
    - Orphan Cleanup: 매시간 (hourly) - 별도 서비스
    - Consistency Check: 매주 월요일 04:00 (주간)
    """

    def __init__(
        self,
        embedding_refresh_job: EmbeddingRefreshJob | None = None,
        repomap_rebuild_job: RepoMapRebuildJob | None = None,
        consistency_checker=None,
    ):
        self.embedding_refresh_job = embedding_refresh_job
        self.repomap_rebuild_job = repomap_rebuild_job
        self.consistency_checker = consistency_checker

        self.running = False
        self.tasks: list[asyncio.Task] = []

    async def start(self):
        """스케줄러 시작"""
        if self.running:
            logger.warning("background_jobs_scheduler_already_running")
            return

        self.running = True
        logger.info("background_jobs_scheduler_started")

        # 각 작업별 스케줄 태스크 시작
        if self.embedding_refresh_job:
            task = asyncio.create_task(
                self._run_weekly(
                    self.embedding_refresh_job.run,
                    day_of_week=6,  # Sunday (0=Monday, 6=Sunday)
                    hour=2,
                    minute=0,
                    job_name="embedding_refresh",
                )
            )
            self.tasks.append(task)

        if self.repomap_rebuild_job:
            task = asyncio.create_task(
                self._run_daily(self.repomap_rebuild_job.run, hour=3, minute=0, job_name="repomap_rebuild")
            )
            self.tasks.append(task)

        if self.consistency_checker:
            task = asyncio.create_task(
                self._run_weekly(
                    self.consistency_checker.check_all,
                    day_of_week=0,  # Monday
                    hour=4,
                    minute=0,
                    job_name="consistency_check",
                )
            )
            self.tasks.append(task)

    async def stop(self):
        """스케줄러 중지"""
        if not self.running:
            return

        self.running = False
        logger.info("background_jobs_scheduler_stopping")

        # 모든 태스크 취소
        for task in self.tasks:
            task.cancel()

        # 태스크 완료 대기
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks = []
        logger.info("background_jobs_scheduler_stopped")

    async def _run_daily(self, job_func, hour: int, minute: int, job_name: str):
        """
        매일 특정 시간에 작업 실행.

        Args:
            job_func: 실행할 함수
            hour: 실행 시간 (0-23)
            minute: 실행 분 (0-59)
            job_name: 작업 이름 (로깅용)
        """
        while self.running:
            try:
                # 다음 실행 시간 계산
                now = datetime.now(timezone.utc)
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # 오늘 시간이 이미 지났으면 내일로
                if now >= target_time:
                    target_time = target_time.replace(day=target_time.day + 1)

                # 대기
                wait_seconds = (target_time - now).total_seconds()
                logger.info(
                    f"{job_name}_scheduled",
                    next_run=target_time.isoformat(),
                    wait_seconds=int(wait_seconds),
                )

                await asyncio.sleep(wait_seconds)

                # 실행
                if self.running:
                    logger.info(f"{job_name}_started")
                    start_time = datetime.now(timezone.utc)

                    try:
                        await job_func()
                        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(
                            f"{job_name}_completed",
                            duration_seconds=int(duration),
                        )
                    except Exception as e:
                        logger.error(
                            f"{job_name}_failed",
                            error=str(e),
                            exc_info=True,
                        )

            except asyncio.CancelledError:
                logger.info(f"{job_name}_cancelled")
                break
            except Exception as e:
                logger.error(f"{job_name}_error", error=str(e), exc_info=True)
                # 에러 발생 시 1시간 대기 후 재시도
                await asyncio.sleep(3600)

    async def _run_weekly(self, job_func, day_of_week: int, hour: int, minute: int, job_name: str):
        """
        매주 특정 요일/시간에 작업 실행.

        Args:
            job_func: 실행할 함수
            day_of_week: 요일 (0=Monday, 6=Sunday)
            hour: 실행 시간 (0-23)
            minute: 실행 분 (0-59)
            job_name: 작업 이름 (로깅용)
        """
        while self.running:
            try:
                # 다음 실행 시간 계산
                now = datetime.now(timezone.utc)
                current_day = now.weekday()

                # 목표 요일까지 남은 일 수
                days_ahead = day_of_week - current_day
                if days_ahead < 0:  # 이번 주 요일이 지났으면
                    days_ahead += 7
                elif days_ahead == 0:  # 오늘이 목표 요일
                    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if now >= target_time:  # 오늘 시간이 지났으면
                        days_ahead = 7

                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                target_time = target_time.replace(day=target_time.day + days_ahead)

                # 대기
                wait_seconds = (target_time - now).total_seconds()
                logger.info(
                    f"{job_name}_scheduled",
                    next_run=target_time.isoformat(),
                    day_of_week=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day_of_week],
                    wait_seconds=int(wait_seconds),
                )

                await asyncio.sleep(wait_seconds)

                # 실행
                if self.running:
                    logger.info(f"{job_name}_started")
                    start_time = datetime.now(timezone.utc)

                    try:
                        await job_func()
                        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(
                            f"{job_name}_completed",
                            duration_seconds=int(duration),
                        )
                    except Exception as e:
                        logger.error(
                            f"{job_name}_failed",
                            error=str(e),
                            exc_info=True,
                        )

            except asyncio.CancelledError:
                logger.info(f"{job_name}_cancelled")
                break
            except Exception as e:
                logger.error(f"{job_name}_error", error=str(e), exc_info=True)
                # 에러 발생 시 1시간 대기 후 재시도
                await asyncio.sleep(3600)

    async def run_now(self, job_name: str) -> dict:
        """
        특정 작업 즉시 실행 (수동 트리거).

        Args:
            job_name: "embedding_refresh", "repomap_rebuild", "consistency_check"

        Returns:
            실행 결과
        """
        logger.info(f"{job_name}_manual_trigger")

        try:
            if job_name == "embedding_refresh" and self.embedding_refresh_job:
                return await self.embedding_refresh_job.run()

            elif job_name == "repomap_rebuild" and self.repomap_rebuild_job:
                return await self.repomap_rebuild_job.run()

            elif job_name == "consistency_check" and self.consistency_checker:
                return await self.consistency_checker.check_all()

            else:
                return {
                    "status": "error",
                    "message": f"Unknown or disabled job: {job_name}",
                }

        except Exception as e:
            logger.error(f"{job_name}_manual_run_failed", error=str(e), exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }
