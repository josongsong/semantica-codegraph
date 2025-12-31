"""
Event-Driven Embedding Worker Pool

asyncio.Condition 기반 즉시 처리 worker pool.
Redis notify로 worker를 깨워서 우선순위 높은 chunk부터 처리.
"""

import asyncio
import random

from codegraph_shared.common.observability import get_logger
from codegraph_engine.multi_index.infrastructure.vector.embedding_queue import EmbeddingQueue

logger = get_logger(__name__)


class EmbeddingWorkerPool:
    """
    Event-driven embedding worker pool.

    특징:
    - N개 worker 동시 처리
    - asyncio.Condition으로 즉시 notify
    - 우선순위 높은 것부터 개별 처리
    - 큐 비었을 때 대기 (리소스 절약)

    사용:
        pool = EmbeddingWorkerPool(
            queue=embedding_queue,
            worker_count=3,
        )

        await pool.start()
        # enqueue 시 자동으로 notify됨
        await pool.stop()
    """

    def __init__(
        self,
        queue: EmbeddingQueue,
        worker_count: int = 3,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
    ):
        """
        Initialize worker pool.

        Args:
            queue: EmbeddingQueue 인스턴스
            worker_count: Worker 개수 (동시 처리)
            max_retries: 최대 재시도 횟수
            base_backoff_seconds: 기본 백오프 시간 (초)
            max_backoff_seconds: 최대 백오프 시간 (초)
        """
        self.queue = queue
        self.worker_count = worker_count
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

        # asyncio.Condition for event notification
        self.has_items = asyncio.Condition()

        # Worker tasks
        self.workers: list[asyncio.Task] = []
        self.running = False

        # Stats (thread-safe with lock)
        self.stats_lock = asyncio.Lock()
        self.processed_count = 0
        self.failed_count = 0
        self.retry_count = 0

    async def notify(self):
        """
        큐에 새 항목 추가 시 호출.

        대기 중인 worker를 즉시 깨움.
        """
        async with self.has_items:
            self.has_items.notify()  # 1개 worker 깨우기

    async def notify_all(self):
        """모든 worker 깨우기 (대량 enqueue 시)."""
        async with self.has_items:
            self.has_items.notify_all()

    async def start(self):
        """Worker pool 시작."""
        if self.running:
            logger.warning("worker_pool_already_running")
            return

        self.running = True

        for i in range(self.worker_count):
            task = asyncio.create_task(self._worker(i))
            self.workers.append(task)

        logger.info(
            "embedding_worker_pool_started",
            worker_count=self.worker_count,
        )

    async def stop(self):
        """Worker pool 정지."""
        if not self.running:
            return

        self.running = False

        # 모든 worker 깨워서 종료하게 함
        async with self.has_items:
            self.has_items.notify_all()

        # Worker 종료 대기
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)
            self.workers = []

        logger.info(
            "embedding_worker_pool_stopped",
            processed=self.processed_count,
            failed=self.failed_count,
        )

    async def _worker(self, worker_id: int):
        """
        개별 worker.

        무한 루프:
        1. 큐에서 우선순위 가장 높은 것 1개 pop
        2. 없으면 notify 대기
        3. 있으면 즉시 처리
        """
        logger.info("worker_started", worker_id=worker_id)

        while self.running:
            try:
                # 1. 우선순위 높은 것 1개 가져오기
                item = await self.queue.pop_one()

                if not item:
                    # 큐 비었음 → notify 대기 또는 빠르게 종료
                    if not self.running:
                        break  # 종료 신호받으면 즉시 종료

                    async with self.has_items:
                        try:
                            # 짧은 timeout으로 빠른 종료 가능
                            await asyncio.wait_for(
                                self.has_items.wait(),
                                timeout=1.0,  # 1초 timeout
                            )
                        except asyncio.TimeoutError:
                            # Expected: 1초마다 running 체크를 위한 정상 timeout
                            # Debug level로 로깅 (프로덕션에서는 노출 안됨)
                            logger.debug(
                                "worker_wait_timeout",
                                worker_id=worker_id,
                                reason="checking_running_status",
                            )

                    continue

                # 2. 즉시 처리
                success = await self._process_item(item, worker_id)

                # Thread-safe 카운트 증가
                async with self.stats_lock:
                    if success:
                        self.processed_count += 1
                    else:
                        self.failed_count += 1

            except asyncio.CancelledError:
                logger.info("worker_cancelled", worker_id=worker_id)
                break

            except Exception as e:
                logger.error(
                    "worker_error",
                    worker_id=worker_id,
                    error=str(e),
                    exc_info=True,
                )
                # 에러 발생해도 계속 실행

        logger.info("worker_stopped", worker_id=worker_id)

    async def _process_item(self, item: dict, worker_id: int) -> bool:
        """
        단일 item 처리 (exponential backoff 재시도 포함).

        Args:
            item: Queue에서 가져온 row
            worker_id: Worker ID

        Returns:
            성공 여부
        """
        chunk_id = item["chunk_id"]
        repo_id = item["repo_id"]
        snapshot_id = item["snapshot_id"]

        logger.debug(
            "worker_processing",
            worker_id=worker_id,
            chunk_id=chunk_id,
            priority=item["priority"],
        )

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # EmbeddingQueue의 _process_single_item 호출
                success = await self.queue.process_single_item(
                    chunk_id,
                    repo_id,
                    snapshot_id,
                )

                if success:
                    if attempt > 0:
                        # 재시도 후 성공
                        async with self.stats_lock:
                            self.retry_count += attempt
                        logger.info(
                            "worker_retry_success",
                            worker_id=worker_id,
                            chunk_id=chunk_id,
                            attempts=attempt + 1,
                        )
                    else:
                        logger.debug(
                            "worker_success",
                            worker_id=worker_id,
                            chunk_id=chunk_id,
                        )

                    return True

                # success=False이지만 예외 없음 - 재시도하지 않음
                return False

            except Exception as e:
                last_error = e

                # 재시도 가능 여부 체크
                if attempt < self.max_retries - 1:
                    # 🔥 SOTA: Exponential backoff with jitter
                    backoff = min(
                        self.base_backoff_seconds * (2**attempt),
                        self.max_backoff_seconds,
                    )
                    # Add jitter (±25%)
                    jitter = backoff * 0.25 * (random.random() * 2 - 1)
                    wait_time = backoff + jitter

                    logger.warning(
                        "worker_retry_scheduled",
                        worker_id=worker_id,
                        chunk_id=chunk_id,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        wait_seconds=round(wait_time, 2),
                        error=str(e),
                    )

                    await asyncio.sleep(wait_time)
                else:
                    # 모든 재시도 실패
                    logger.error(
                        "worker_process_failed_all_retries",
                        worker_id=worker_id,
                        chunk_id=chunk_id,
                        attempts=self.max_retries,
                        error=str(last_error),
                    )

        return False

    async def get_stats(self) -> dict:
        """Worker pool 통계."""
        async with self.stats_lock:
            return {
                "worker_count": self.worker_count,
                "running": self.running,
                "processed": self.processed_count,
                "failed": self.failed_count,
                "retry_count": self.retry_count,
                "workers_alive": sum(1 for w in self.workers if not w.done()),
            }
