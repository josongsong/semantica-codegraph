"""백그라운드 인덱싱 스케줄러.

협력적 취소(cooperative cancellation) 패턴을 사용하여
graceful shutdown과 작업 일시중지를 지원합니다.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from src.contexts.analysis_indexing.infrastructure.models.job import JobProgress
from src.contexts.analysis_indexing.infrastructure.models.mode import IndexingMode, ModeTransitionConfig
from src.infra.observability import get_logger

logger = get_logger(__name__)


class Priority(int, Enum):
    """백그라운드 작업 우선순위."""

    HIGH = 1  # Repair
    MEDIUM = 2  # Balanced
    LOW = 3  # Deep


@dataclass
class BackgroundJob:
    """백그라운드 인덱싱 작업."""

    job_id: str
    repo_id: str
    mode: IndexingMode
    priority: Priority
    created_at: datetime
    checkpoint_data: dict | None = None  # 중단 시 체크포인트


class BackgroundScheduler:
    """백그라운드 인덱싱 스케줄러.

    협력적 취소 패턴을 사용하여 graceful shutdown을 지원합니다:
    - stop_event: 중단 요청 신호 (asyncio.Event)
    - current_progress: 실시간 진행상태 (JobProgress 참조)

    IndexingOrchestrator는 파일 처리 루프에서 stop_event를 체크하고,
    set되면 현재 파일 처리 완료 후 즉시 중단합니다.
    """

    def __init__(
        self,
        indexing_callback: Callable[
            [str, IndexingMode, JobProgress | None, asyncio.Event],
            Awaitable[None],
        ]
        | None = None,
    ):
        """
        Args:
            indexing_callback: 실제 인덱싱 실행 함수
                signature: async fn(repo_id, mode, progress, stop_event) -> result
        """
        self.indexing_callback = indexing_callback
        self.job_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.current_job: BackgroundJob | None = None
        self.is_running = False
        self.should_stop = False

        # 협력적 취소 지원
        self.stop_event: asyncio.Event = asyncio.Event()
        self.current_progress: JobProgress | None = None

    async def schedule(
        self,
        repo_id: str,
        mode: IndexingMode,
        checkpoint_data: dict | None = None,
    ) -> str:
        """
        백그라운드 작업 스케줄.

        Args:
            repo_id: 레포지토리 ID
            mode: 인덱싱 모드
            checkpoint_data: 재개용 체크포인트

        Returns:
            job_id
        """
        priority = self._get_priority(mode)
        job = BackgroundJob(
            job_id=f"{repo_id}_{mode.value}_{datetime.now(UTC).timestamp()}",
            repo_id=repo_id,
            mode=mode,
            priority=priority,
            created_at=datetime.now(UTC),
            checkpoint_data=checkpoint_data,
        )

        await self.job_queue.put((priority.value, job))
        logger.info(
            "background_job_scheduled",
            job_id=job.job_id,
            repo_id=repo_id,
            mode=mode.value,
            priority=priority.name,
        )

        return job.job_id

    def _get_priority(self, mode: IndexingMode) -> Priority:
        """모드별 우선순위 결정."""
        if mode == IndexingMode.REPAIR:
            return Priority.HIGH
        elif mode == IndexingMode.BALANCED:
            return Priority.MEDIUM
        elif mode == IndexingMode.DEEP:
            return Priority.LOW
        else:
            return Priority.MEDIUM

    async def start(self):
        """백그라운드 워커 시작."""
        if self.is_running:
            logger.warning("background_scheduler_already_running")
            return

        self.is_running = True
        self.should_stop = False
        self.stop_event.clear()
        logger.info("background_scheduler_started")

        while not self.should_stop:
            try:
                # 작업 대기 (타임아웃 1초)
                try:
                    priority, job = await asyncio.wait_for(self.job_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self.current_job = job
                self.stop_event.clear()  # 새 작업 시작 시 이벤트 초기화

                # 이전 체크포인트에서 JobProgress 복원 또는 새로 생성
                if job.checkpoint_data:
                    self.current_progress = JobProgress.from_dict(job.checkpoint_data)
                    self.current_progress.resume()  # 일시중지 해제
                    logger.info(
                        "background_job_resuming",
                        job_id=job.job_id,
                        completed_files=len(self.current_progress.completed_files),
                        progress_percent=f"{self.current_progress.progress_percent:.1f}%",
                    )
                else:
                    self.current_progress = JobProgress(job_id=job.job_id)

                logger.info(
                    "background_job_starting",
                    job_id=job.job_id,
                    mode=job.mode.value,
                    repo_id=job.repo_id,
                )

                # 인덱싱 실행 (stop_event와 progress 전달)
                if self.indexing_callback:
                    try:
                        await self.indexing_callback(
                            job.repo_id,
                            job.mode,
                            self.current_progress,
                            self.stop_event,
                        )

                        if self.stop_event.is_set():
                            # 중단됨 - 진행상태 저장됨
                            logger.info(
                                "background_job_paused",
                                job_id=job.job_id,
                                completed_files=len(self.current_progress.completed_files),
                                progress_percent=f"{self.current_progress.progress_percent:.1f}%",
                            )
                        else:
                            logger.info("background_job_completed", job_id=job.job_id)
                    except Exception as e:
                        logger.error(
                            "background_job_failed",
                            job_id=job.job_id,
                            error=str(e),
                            exc_info=True,
                        )
                else:
                    logger.warning("background_job_skipped_no_callback", job_id=job.job_id)

                self.current_job = None

            except Exception as e:
                logger.error("background_scheduler_error", error=str(e), exc_info=True)
                await asyncio.sleep(1)

        self.is_running = False
        self.current_progress = None
        logger.info("background_scheduler_stopped")

    async def stop(self, graceful: bool = True, timeout: float = 30.0):
        """
        백그라운드 워커 중단.

        Args:
            graceful: True면 현재 파일 처리 완료 후 중단
            timeout: graceful 중단 대기 최대 시간 (초)
        """
        logger.info("background_scheduler_stopping", graceful=graceful)

        if graceful and self.current_job:
            # 1. stop 신호 전달
            self.stop_event.set()
            logger.info("background_job_graceful_stop_requested", job_id=self.current_job.job_id)

            # 2. 현재 파일 처리 완료 대기
            try:
                await asyncio.wait_for(
                    self._wait_current_file_complete(),
                    timeout=timeout,
                )
                logger.info(
                    "background_job_graceful_stop_completed",
                    job_id=self.current_job.job_id,
                    completed_files=len(self.current_progress.completed_files) if self.current_progress else 0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "graceful_stop_timeout",
                    job_id=self.current_job.job_id,
                    timeout_seconds=timeout,
                )

        self.should_stop = True

    async def _wait_current_file_complete(self):
        """현재 처리 중인 파일 완료 대기."""
        while self.current_progress and self.current_progress.processing_file:
            await asyncio.sleep(0.1)

    def pause_current_job(self) -> JobProgress | None:
        """
        현재 실행 중인 작업 일시중지 (Fast 우선 처리용).

        Returns:
            JobProgress: 재개용 진행상태 (None이면 일시중지 불가)
        """
        if not self.current_job or not self.current_progress:
            return None

        # 일시중지 가능한 모드 체크 (BALANCED, DEEP만 가능)
        if self.current_job.mode not in (IndexingMode.BALANCED, IndexingMode.DEEP):
            logger.warning(
                "background_job_pause_not_allowed",
                job_id=self.current_job.job_id,
                mode=self.current_job.mode.value,
            )
            return None

        # stop 신호 전달
        self.stop_event.set()

        # 일시중지 상태로 표시
        self.current_progress.pause()

        logger.info(
            "background_job_pausing",
            job_id=self.current_job.job_id,
            mode=self.current_job.mode.value,
            completed_files=len(self.current_progress.completed_files),
            progress_percent=f"{self.current_progress.progress_percent:.1f}%",
        )

        return self.current_progress

    async def resume_paused_job(self) -> str | None:
        """
        일시중지된 작업 재개.

        Returns:
            job_id: 재개된 작업 ID (None이면 재개할 작업 없음)
        """
        if not self.current_job or not self.current_progress:
            return None

        if not self.current_progress.is_paused:
            return None

        # 작업 재스케줄 (checkpoint_data로 진행상태 전달)
        job_id = await self.schedule(
            repo_id=self.current_job.repo_id,
            mode=self.current_job.mode,
            checkpoint_data=self.current_progress.to_dict(),
        )

        logger.info(
            "background_job_resume_scheduled",
            original_job_id=self.current_job.job_id,
            new_job_id=job_id,
            completed_files=len(self.current_progress.completed_files),
        )

        return job_id

    def get_queue_size(self) -> int:
        """대기 중인 작업 개수."""
        return self.job_queue.qsize()

    def is_idle(self) -> bool:
        """백그라운드 작업 실행 중인지 확인."""
        return self.current_job is None and self.job_queue.empty()


class IdleDetector:
    """IDE idle 상태 감지."""

    def __init__(self):
        self.last_activity_time = datetime.now(UTC)

    def mark_activity(self):
        """사용자 활동 기록 (파일 저장, 편집 등)."""
        self.last_activity_time = datetime.now(UTC)

    def get_idle_minutes(self) -> float:
        """현재 idle 시간 (분)."""
        delta = datetime.now(UTC) - self.last_activity_time
        return delta.total_seconds() / 60

    def is_idle(self, threshold_minutes: float = ModeTransitionConfig.FAST_TO_BALANCED_IDLE_MINUTES) -> bool:
        """지정된 시간 이상 idle 상태인지."""
        return self.get_idle_minutes() >= threshold_minutes
