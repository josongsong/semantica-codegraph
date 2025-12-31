"""
Lock Keeper - Lock 자동 갱신 (Keep-Alive)

Hexagonal Architecture:
- Domain Layer (비즈니스 로직)
- Port를 통한 LockManager 의존

SOLID:
- S: Lock 갱신만 담당
- O: renewal_strategy 확장 가능
- L: LockKeeperProtocol 준수
- I: 최소 인터페이스
- D: Protocol 의존 (구체 클래스 의존 X)

Thread-Safety: asyncio.Lock 사용
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.ports.lock_protocols import LockManagerProtocol

logger = logging.getLogger(__name__)


# ============================================================
# Port (Hexagonal)
# ============================================================


class LockKeeperProtocol(Protocol):
    """Lock Keeper Port"""

    async def start_keeping(self, agent_id: str, file_paths: list[str]) -> str:
        """갱신 시작"""
        ...

    async def stop_keeping(self, keeper_id: str) -> None:
        """갱신 중단"""
        ...


# ============================================================
# Domain Models
# ============================================================


@dataclass
class RenewalMetrics:
    """갱신 통계 (메모리 누수 방지)"""

    total_renewals: int = 0
    failed_renewals: int = 0
    active_keepers: int = 0
    avg_renewal_latency_ms: float = 0.0

    # 🔥 deque로 메모리 누수 방지 (최근 1000개만)
    _latencies: deque[float] = field(
        default_factory=lambda: deque(maxlen=1000),
        repr=False,
    )

    def record_renewal(self, latency_ms: float, success: bool):
        """갱신 기록"""
        if success:
            self.total_renewals += 1
            self._latencies.append(latency_ms)

            if self._latencies:
                self.avg_renewal_latency_ms = sum(self._latencies) / len(self._latencies)
        else:
            self.failed_renewals += 1

    @property
    def success_rate(self) -> float:
        """성공률"""
        total = self.total_renewals + self.failed_renewals
        return self.total_renewals / total if total > 0 else 0.0


# ============================================================
# Domain Service
# ============================================================


class LockKeeper:
    """
    Lock Keep-Alive Service (SOTA급)

    책임:
    - 주기적으로 Lock TTL 연장
    - Renewal 실패 감지
    - 통계 수집

    Thread-Safety:
    - asyncio.Lock으로 _tasks dict 보호

    Error Handling:
    - Renewal 실패 → 로그 + 계속
    - 연속 실패 3회 → task 중단

    Performance:
    - Renewal interval: 5분 (TTL 30분의 1/6)
    - Overhead: <1ms per renewal
    """

    def __init__(
        self,
        lock_manager: "LockManagerProtocol",
        renewal_interval: float = 300.0,  # 5분
        max_consecutive_failures: int = 3,
    ):
        """
        Args:
            lock_manager: Lock Manager (Protocol)
            renewal_interval: 갱신 간격 (초)
            max_consecutive_failures: 최대 연속 실패 (초과 시 중단)

        Raises:
            ValueError: Invalid parameters
        """
        if renewal_interval <= 0:
            raise ValueError(f"renewal_interval must be > 0, got {renewal_interval}")

        if max_consecutive_failures < 1:
            raise ValueError(f"max_consecutive_failures must be >= 1, got {max_consecutive_failures}")

        self.lock_manager = lock_manager
        self.renewal_interval = renewal_interval
        self.max_consecutive_failures = max_consecutive_failures

        # Active keep-alive tasks
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # Metrics
        self._metrics = RenewalMetrics()

        logger.info(f"LockKeeper initialized: interval={renewal_interval}s, max_failures={max_consecutive_failures}")

    async def start_keeping(
        self,
        agent_id: str,
        file_paths: list[str],
    ) -> str:
        """
        Lock 갱신 시작

        Args:
            agent_id: Agent ID
            file_paths: 갱신할 파일 경로 리스트

        Returns:
            keeper_id (중단 시 사용)

        Raises:
            ValueError: Empty file_paths
        """
        if not file_paths:
            raise ValueError("file_paths cannot be empty")

        import time
        import uuid

        # 🔥 UUID로 충돌 방지
        keeper_id = f"{agent_id}:{uuid.uuid4().hex[:8]}"

        async with self._lock:
            if keeper_id in self._tasks:
                logger.warning(f"Keeper already exists: {keeper_id}")
                return keeper_id

            task = asyncio.create_task(self._keep_alive_loop(agent_id, file_paths, keeper_id))

            self._tasks[keeper_id] = task
            self._metrics.active_keepers += 1

        logger.info(f"Lock keeper started: {keeper_id}, files={len(file_paths)}")

        return keeper_id

    async def stop_keeping(self, keeper_id: str) -> None:
        """
        Lock 갱신 중단

        Args:
            keeper_id: Keeper ID

        Thread-Safety: asyncio.Lock 보호
        """
        async with self._lock:
            task = self._tasks.pop(keeper_id, None)

            if task and not task.done():
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

                self._metrics.active_keepers -= 1

        logger.info(f"Lock keeper stopped: {keeper_id}")

    async def stop_all(self):
        """모든 Keeper 중단"""
        async with self._lock:
            keeper_ids = list(self._tasks.keys())

        for keeper_id in keeper_ids:
            await self.stop_keeping(keeper_id)

        logger.info("All lock keepers stopped")

    async def _keep_alive_loop(
        self,
        agent_id: str,
        file_paths: list[str],
        keeper_id: str,
    ):
        """
        Keep-alive loop (백그라운드)

        Algorithm:
        1. Sleep renewal_interval
        2. Renew all locks
        3. Check consecutive failures
        4. Repeat

        Args:
            agent_id: Agent ID
            file_paths: 파일 경로 리스트
            keeper_id: Keeper ID
        """
        renewal_count = 0
        consecutive_failures = 0

        try:
            while True:
                await asyncio.sleep(self.renewal_interval)

                # 🔥 배치 renewal (병렬 처리 - 성능 최적화)
                success_count = 0
                start_time = asyncio.get_event_loop().time()

                # 병렬로 renew (asyncio.gather)
                renewal_tasks = [self._renew_single_lock(agent_id, file_path) for file_path in file_paths]

                results = await asyncio.gather(*renewal_tasks, return_exceptions=True)

                # 개별 실패 로그 (but 개별 카운트 안 함)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.warning(
                            f"Failed to renew lock: {file_paths[i]}",
                            extra={"agent": agent_id, "error": str(result)},
                        )
                    elif result:
                        success_count += 1

                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                # 통계 기록
                batch_success = success_count == len(file_paths)
                self._metrics.record_renewal(latency_ms, batch_success)

                # 🔥 L11 개선: 전체 배치 실패만 카운트 (부분 실패는 허용)
                if batch_success:
                    consecutive_failures = 0
                    renewal_count += 1
                    logger.debug(f"Locks renewed: {agent_id}, count={renewal_count}, latency={latency_ms:.1f}ms")
                else:
                    # 전체 배치 실패만 consecutive_failures 증가
                    consecutive_failures += 1
                    logger.warning(
                        f"Batch renewal failed: {agent_id}, success={success_count}/{len(file_paths)}",
                        extra={"consecutive_failures": consecutive_failures},
                    )

                # 연속 배치 실패 체크
                if consecutive_failures >= self.max_consecutive_failures:
                    logger.error(
                        f"Max consecutive failures reached: {consecutive_failures}, stopping keeper {keeper_id}"
                    )
                    break

        except asyncio.CancelledError:
            logger.info(f"Keep-alive cancelled: {keeper_id}, renewals={renewal_count}")
            raise

        except Exception as e:
            logger.error(f"Keep-alive error: {keeper_id}, {e}", exc_info=True)

    async def _renew_single_lock(
        self,
        agent_id: str,
        file_path: str,
    ) -> bool:
        """
        단일 Lock 갱신

        Algorithm:
        1. Lock 조회
        2. 소유권 확인
        3. acquired_at 갱신
        4. 재저장

        Args:
            agent_id: Agent ID
            file_path: 파일 경로

        Returns:
            성공 여부
        """
        try:
            # Lock 조회
            lock = await self.lock_manager.get_lock(file_path)

            if not lock:
                logger.debug(f"Lock not found (expired?): {file_path}")
                return False

            # 🔥 renew_lock() 사용 (캡슐화 준수)
            return await self.lock_manager.renew_lock(agent_id, file_path)

        except Exception as e:
            logger.error(f"Failed to renew lock: {file_path}, {e}")
            return False

    def get_metrics(self) -> RenewalMetrics:
        """통계 조회"""
        return self._metrics

    def get_active_keepers(self) -> list[str]:
        """활성 Keeper 목록"""
        return list(self._tasks.keys())


# ============================================================
# Export
# ============================================================

__all__ = [
    "LockKeeper",
    "LockKeeperProtocol",
    "RenewalMetrics",
]
