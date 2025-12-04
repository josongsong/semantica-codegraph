"""
File Indexing Queue

간단한 파일 단위 증분 인덱싱 큐.
현재는 인메모리 구현, 향후 Redis/DB로 확장 가능.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class FileIndexTask:
    """파일 인덱싱 태스크."""

    repo_id: str
    snapshot_id: str
    file_path: str
    reason: str | None = None
    priority: int = 0

    def __lt__(self, other: "FileIndexTask") -> bool:
        """우선순위 비교 (높은 값이 우선)."""
        return self.priority > other.priority


class FileIndexingQueue:
    """
    파일 단위 증분 인덱싱 큐.

    Features:
    - 우선순위 기반 처리
    - 중복 제거 (같은 파일은 한 번만)
    - 비동기 worker
    - 백그라운드 처리

    Usage:
        queue = FileIndexingQueue(index_func=indexing_service._index_single_file)

        # 파일 추가
        await queue.enqueue("repo1", "main", "src/main.py", priority=1)

        # Worker 시작
        await queue.start_worker()

        # 대기
        await queue.wait_until_idle()

        # Worker 종료
        await queue.stop_worker()
    """

    def __init__(
        self,
        index_func: Callable,
        max_concurrent: int = 3,
    ):
        """
        Initialize file indexing queue.

        Args:
            index_func: 파일 인덱싱 함수
                       Signature: async (repo_id, snapshot_id, file_path) -> None
            max_concurrent: 최대 동시 처리 개수
        """
        self.index_func = index_func
        self.max_concurrent = max_concurrent

        # 큐 (우선순위)
        self.queue: deque[FileIndexTask] = deque()
        self.queue_lock = asyncio.Lock()

        # 중복 제거용
        self.pending_keys: set[tuple[str, str, str]] = set()  # (repo_id, snapshot_id, file_path)

        # Worker 상태
        self.worker_task: asyncio.Task | None = None
        self.running = False

        # 현재 처리 중인 tasks
        self.active_tasks: set[asyncio.Task] = set()

    async def enqueue(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        reason: str | None = None,
        priority: int = 0,
    ) -> bool:
        """
        파일 인덱싱 태스크 추가.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            file_path: 파일 경로
            reason: 트리거 이유
            priority: 우선순위

        Returns:
            추가 여부 (중복이면 False)
        """
        async with self.queue_lock:
            # 중복 체크
            key = (repo_id, snapshot_id, file_path)
            if key in self.pending_keys:
                logger.debug(
                    "file_already_queued",
                    repo_id=repo_id,
                    file_path=file_path,
                )
                return False

            # 큐에 추가
            task = FileIndexTask(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=file_path,
                reason=reason,
                priority=priority,
            )

            self.queue.append(task)
            self.pending_keys.add(key)

            # 우선순위 정렬 (높은 priority가 앞으로)
            self.queue = deque(sorted(self.queue, reverse=True))

            logger.debug(
                "file_enqueued",
                repo_id=repo_id,
                file_path=file_path,
                priority=priority,
                queue_size=len(self.queue),
            )

            return True

    async def enqueue_batch(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
    ) -> int:
        """
        여러 파일 배치 추가.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            file_paths: 파일 경로 목록
            reason: 트리거 이유
            priority: 우선순위

        Returns:
            실제 추가된 개수 (중복 제외)
        """
        added_count = 0
        for file_path in file_paths:
            added = await self.enqueue(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_path=file_path,
                reason=reason,
                priority=priority,
            )
            if added:
                added_count += 1

        logger.info(
            "batch_enqueued",
            repo_id=repo_id,
            total_files=len(file_paths),
            added_count=added_count,
            duplicates=len(file_paths) - added_count,
        )

        return added_count

    async def start_worker(self):
        """백그라운드 worker 시작."""
        if self.running:
            logger.warning("worker_already_running")
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker_loop())
        logger.info("file_indexing_worker_started", max_concurrent=self.max_concurrent)

    async def stop_worker(self):
        """Worker 종료."""
        if not self.running:
            return

        self.running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

        # 진행 중인 tasks 대기
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        logger.info("file_indexing_worker_stopped")

    async def _worker_loop(self):
        """Worker loop (백그라운드)."""
        try:
            while self.running:
                # 큐에서 태스크 가져오기
                task = await self._dequeue()

                if not task:
                    # 큐가 비어있으면 잠시 대기
                    await asyncio.sleep(0.1)
                    continue

                # 동시 처리 제한 대기
                while len(self.active_tasks) >= self.max_concurrent:
                    await asyncio.sleep(0.05)

                # 태스크 실행
                async_task = asyncio.create_task(self._process_task(task))
                self.active_tasks.add(async_task)
                async_task.add_done_callback(self.active_tasks.discard)

        except asyncio.CancelledError:
            logger.info("worker_loop_cancelled")
        except Exception as e:
            logger.error("worker_loop_error", error=str(e), exc_info=True)

    async def _dequeue(self) -> FileIndexTask | None:
        """큐에서 태스크 꺼내기."""
        async with self.queue_lock:
            if not self.queue:
                return None

            task = self.queue.popleft()

            # pending_keys에서 제거
            key = (task.repo_id, task.snapshot_id, task.file_path)
            self.pending_keys.discard(key)

            return task

    async def _process_task(self, task: FileIndexTask):
        """태스크 처리."""
        try:
            logger.debug(
                "processing_file_index_task",
                repo_id=task.repo_id,
                file_path=task.file_path,
            )

            # 인덱싱 함수 호출
            await self.index_func(
                repo_id=task.repo_id,
                snapshot_id=task.snapshot_id,
                file_path=task.file_path,
            )

            logger.debug(
                "file_index_task_completed",
                repo_id=task.repo_id,
                file_path=task.file_path,
            )

        except Exception as e:
            logger.error(
                "file_index_task_failed",
                repo_id=task.repo_id,
                file_path=task.file_path,
                error=str(e),
            )

    async def is_idle(self, repo_id: str | None = None, snapshot_id: str | None = None) -> bool:
        """
        큐가 비어있고 처리 중인 작업이 없는지 확인.

        Args:
            repo_id: 특정 repo만 체크 (None이면 전체)
            snapshot_id: 특정 snapshot만 체크 (None이면 전체)

        Returns:
            idle 여부
        """
        async with self.queue_lock:
            # 큐 체크
            if repo_id and snapshot_id:
                # 특정 repo/snapshot만 체크
                has_pending = any(task.repo_id == repo_id and task.snapshot_id == snapshot_id for task in self.queue)
                if has_pending:
                    return False
            elif self.queue:
                # 전체 큐 체크
                return False

        # 진행 중인 작업 없음
        return len(self.active_tasks) == 0

    async def wait_until_idle(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        timeout: float = 5.0,
    ) -> bool:
        """
        idle 상태 될 때까지 대기.

        Args:
            repo_id: 특정 repo만 대기
            snapshot_id: 특정 snapshot만 대기
            timeout: 최대 대기 시간 (초)

        Returns:
            타임아웃 내 idle 달성 여부
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.is_idle(repo_id, snapshot_id):
                return True

            await asyncio.sleep(0.1)

        logger.warning(
            "wait_until_idle_timeout",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            timeout=timeout,
        )
        return False

    def get_queue_size(self) -> int:
        """큐 크기 반환."""
        return len(self.queue)
