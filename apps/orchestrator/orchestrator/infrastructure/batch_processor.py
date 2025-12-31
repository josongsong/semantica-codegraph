"""
Batch Processor (SOTA급)

특징:
1. Dynamic Batching (자동 배치 크기 조정)
2. Priority Queue (우선순위 기반 처리)
3. Backpressure Handling (과부하 방지)
4. Adaptive Timeout (상황별 타임아웃)
5. Metrics & Monitoring
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


# ============================================================
# Priority
# ============================================================


class Priority(Enum):
    """작업 우선순위"""

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


# ============================================================
# Batch Item
# ============================================================


@dataclass
class BatchItem(Generic[T]):
    """배치 아이템"""

    data: T
    priority: Priority = Priority.MEDIUM
    future: asyncio.Future = field(default_factory=asyncio.Future)
    created_at: float = field(default_factory=time.time)

    def __lt__(self, other: "BatchItem") -> bool:
        """Priority Queue 정렬용"""
        # 우선순위 높은 것 먼저, 같으면 생성 시간 빠른 것 먼저
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at


# ============================================================
# Batch Processor
# ============================================================


class BatchProcessor(Generic[T, R]):
    """
    SOTA급 Batch Processor.

    특징:
    - Dynamic Batching (자동 크기 조정)
    - Priority Queue
    - Backpressure Handling
    - Adaptive Timeout
    """

    def __init__(
        self,
        process_func: Callable[[list[T]], list[R]],
        min_batch_size: int = 1,
        max_batch_size: int = 10,
        max_wait_time: float = 0.1,  # 100ms
        max_queue_size: int = 1000,
        enable_adaptive_batching: bool = True,
    ):
        """
        Args:
            process_func: 배치 처리 함수 (async)
            min_batch_size: 최소 배치 크기
            max_batch_size: 최대 배치 크기
            max_wait_time: 최대 대기 시간 (초)
            max_queue_size: 최대 큐 크기 (Backpressure)
            enable_adaptive_batching: 동적 배치 크기 조정 여부
        """
        self.process_func = process_func
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.max_queue_size = max_queue_size
        self.enable_adaptive_batching = enable_adaptive_batching

        # Priority Queue
        self.queue: asyncio.PriorityQueue[BatchItem[T]] = asyncio.PriorityQueue(maxsize=max_queue_size)

        # Worker Task
        self.worker_task: asyncio.Task | None = None
        self.is_running = False

        # Adaptive Batching
        self.current_batch_size = min_batch_size
        self.latencies: list[float] = []
        self.max_latency_samples = 100

        # Metrics
        self.stats = {
            "total_items": 0,
            "total_batches": 0,
            "total_wait_time": 0.0,
            "total_process_time": 0.0,
            "queue_full_count": 0,
            "avg_batch_size": 0.0,
        }

    async def start(self):
        """Batch Processor 시작"""
        if self.is_running:
            return

        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        """Batch Processor 중지"""
        self.is_running = False
        if self.worker_task:
            await self.worker_task

    async def submit(self, data: T, priority: Priority = Priority.MEDIUM, timeout: float = 30.0) -> R:
        """
        작업 제출.

        Args:
            data: 처리할 데이터
            priority: 우선순위
            timeout: 타임아웃 (초)

        Returns:
            처리 결과

        Raises:
            asyncio.TimeoutError: 타임아웃
            asyncio.QueueFull: 큐 가득 참 (Backpressure)
        """
        if not self.is_running:
            await self.start()

        # 아이템 생성
        item = BatchItem(data=data, priority=priority)

        # 큐에 추가 (Backpressure: 큐 가득 차면 예외)
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull as e:
            self.stats["queue_full_count"] += 1
            raise asyncio.QueueFull("Batch queue is full (Backpressure)") from e

        # 결과 대기
        try:
            result = await asyncio.wait_for(item.future, timeout=timeout)
            return result
        except asyncio.TimeoutError as e:
            raise asyncio.TimeoutError(f"Batch processing timeout ({timeout}s)") from e

    async def _worker(self):
        """Worker: 배치 수집 및 처리"""
        while self.is_running:
            batch = await self._collect_batch()

            if not batch:
                await asyncio.sleep(0.01)  # 짧은 대기
                continue

            # 배치 처리
            await self._process_batch(batch)

    async def _collect_batch(self) -> list[BatchItem[T]]:
        """
        배치 수집.

        Returns:
            배치 아이템 리스트
        """
        batch: list[BatchItem[T]] = []
        start_time = time.time()

        while len(batch) < self.current_batch_size:
            # 대기 시간 초과 체크
            elapsed = time.time() - start_time
            if elapsed > self.max_wait_time and len(batch) >= self.min_batch_size:
                break

            # 큐에서 가져오기 (non-blocking)
            try:
                remaining_time = self.max_wait_time - elapsed
                if remaining_time <= 0:
                    break

                item = await asyncio.wait_for(self.queue.get(), timeout=remaining_time)
                batch.append(item)

            except asyncio.TimeoutError:
                # 타임아웃 → 배치 반환
                break

        return batch

    async def _process_batch(self, batch: list[BatchItem[T]]):
        """
        배치 처리.

        Args:
            batch: 배치 아이템 리스트
        """
        if not batch:
            return

        start_time = time.time()

        try:
            # 배치 데이터 추출
            batch_data = [item.data for item in batch]

            # 처리 함수 호출
            if asyncio.iscoroutinefunction(self.process_func):
                results = await self.process_func(batch_data)
            else:
                results = self.process_func(batch_data)

            # 결과 전달
            for item, result in zip(batch, results, strict=False):
                if not item.future.done():
                    item.future.set_result(result)

        except Exception as e:
            # 에러 전파
            for item in batch:
                if not item.future.done():
                    item.future.set_exception(e)

        finally:
            # 통계 업데이트
            process_time = time.time() - start_time
            wait_time = sum(start_time - item.created_at for item in batch) / len(batch)

            self.stats["total_items"] += len(batch)
            self.stats["total_batches"] += 1
            self.stats["total_wait_time"] += wait_time
            self.stats["total_process_time"] += process_time
            self.stats["avg_batch_size"] = self.stats["total_items"] / self.stats["total_batches"]

            # Adaptive Batching
            if self.enable_adaptive_batching:
                await self._adapt_batch_size(process_time, len(batch))

    async def _adapt_batch_size(self, latency: float, batch_size: int):
        """
        배치 크기 동적 조정.

        Args:
            latency: 처리 시간 (초)
            batch_size: 현재 배치 크기
        """
        # Latency 기록
        self.latencies.append(latency)
        if len(self.latencies) > self.max_latency_samples:
            self.latencies.pop(0)

        # 평균 Latency 계산
        avg_latency = sum(self.latencies) / len(self.latencies)

        # 목표 Latency (100ms)
        target_latency = 0.1

        # 배치 크기 조정
        if avg_latency < target_latency * 0.8:
            # Latency 낮음 → 배치 크기 증가
            self.current_batch_size = min(self.max_batch_size, self.current_batch_size + 1)
        elif avg_latency > target_latency * 1.2:
            # Latency 높음 → 배치 크기 감소
            self.current_batch_size = max(self.min_batch_size, self.current_batch_size - 1)

    def get_stats(self) -> dict[str, Any]:
        """
        통계 조회.

        Returns:
            통계 딕셔너리
        """
        avg_wait_time = (
            self.stats["total_wait_time"] / self.stats["total_batches"] if self.stats["total_batches"] > 0 else 0.0
        )
        avg_process_time = (
            self.stats["total_process_time"] / self.stats["total_batches"] if self.stats["total_batches"] > 0 else 0.0
        )

        return {
            "queue_size": self.queue.qsize(),
            "current_batch_size": self.current_batch_size,
            "avg_wait_time": avg_wait_time,
            "avg_process_time": avg_process_time,
            "avg_latency": (sum(self.latencies) / len(self.latencies) if self.latencies else 0.0),
            **self.stats,
        }


# ============================================================
# Batched Function Decorator
# ============================================================


def batched(
    min_batch_size: int = 1,
    max_batch_size: int = 10,
    max_wait_time: float = 0.1,
):
    """
    함수를 배치 처리로 래핑하는 데코레이터.

    Example:
        @batched(max_batch_size=10, max_wait_time=0.1)
        async def process_items(items: list[str]) -> list[str]:
            return [item.upper() for item in items]

        # 자동으로 배치 처리됨
        result = await process_items.submit("hello")
    """

    def decorator(func: Callable[[list[T]], list[R]]):
        processor = BatchProcessor(
            process_func=func,
            min_batch_size=min_batch_size,
            max_batch_size=max_batch_size,
            max_wait_time=max_wait_time,
        )

        async def submit(data: T, priority: Priority = Priority.MEDIUM) -> R:
            return await processor.submit(data, priority)

        # 함수 속성 추가
        submit.processor = processor
        submit.get_stats = processor.get_stats

        return submit

    return decorator
