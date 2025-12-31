"""
Circuit Breaker Pattern for External Index Services

외부 서비스(Qdrant, PostgreSQL) 장애 시 빠른 실패를 위한 Circuit Breaker.

States:
- CLOSED: 정상 상태, 모든 요청 허용
- OPEN: 장애 상태, 모든 요청 즉시 실패
- HALF_OPEN: 복구 테스트 상태, 제한된 요청 허용

Implementation:
- Sliding window 기반 실패율 계산
- 지수 백오프 재시도
- 서비스별 독립 Circuit Breaker
"""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit Breaker 상태"""

    CLOSED = "closed"  # 정상
    OPEN = "open"  # 장애 (요청 차단)
    HALF_OPEN = "half_open"  # 복구 테스트


@dataclass
class CircuitBreakerConfig:
    """Circuit Breaker 설정"""

    # 실패 임계값
    failure_threshold: int = 5  # 연속 실패 수
    failure_rate_threshold: float = 0.5  # 실패율 (50%)
    window_size: int = 10  # 슬라이딩 윈도우 크기

    # 타이밍
    open_timeout_seconds: float = 30.0  # OPEN 상태 유지 시간
    half_open_max_calls: int = 3  # HALF_OPEN에서 허용할 테스트 호출 수

    # 재시도
    retry_count: int = 3
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 10.0


@dataclass
class CircuitStats:
    """Circuit Breaker 통계"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # OPEN 상태에서 거부된 호출
    state_transitions: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreakerError(Exception):
    """Circuit Breaker가 OPEN 상태일 때 발생"""

    def __init__(self, service_name: str, state: CircuitState, retry_after: float):
        self.service_name = service_name
        self.state = state
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker for '{service_name}' is {state.value}. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """
    Circuit Breaker for resilient external service calls.

    Usage:
        breaker = CircuitBreaker("qdrant", config)

        # 방법 1: 데코레이터 스타일
        result = await breaker.call(lambda: qdrant_client.search(...))

        # 방법 2: 컨텍스트 매니저
        async with breaker:
            result = await qdrant_client.search(...)
    """

    def __init__(
        self,
        service_name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        """
        Args:
            service_name: 서비스 이름 (로깅/식별용)
            config: Circuit Breaker 설정
        """
        self.service_name = service_name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._state_changed_at = time.monotonic()
        self._half_open_calls = 0

        # Sliding window for failure tracking
        self._call_results: deque[bool] = deque(maxlen=self.config.window_size)

        # 통계
        self._stats = CircuitStats()

        # Lock for thread safety
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """현재 상태"""
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """통계"""
        return self._stats

    @property
    def is_available(self) -> bool:
        """서비스 사용 가능 여부"""
        return self._state != CircuitState.OPEN

    async def call(
        self,
        func: Callable[[], Any],
        fallback: Callable[[], Any] | None = None,
    ) -> Any:
        """
        Circuit Breaker를 통한 함수 호출.

        Args:
            func: 실행할 async 함수
            fallback: 실패 시 대체 함수 (선택)

        Returns:
            함수 실행 결과

        Raises:
            CircuitBreakerError: Circuit이 OPEN 상태일 때
        """
        async with self._lock:
            await self._maybe_transition_state()

            if self._state == CircuitState.OPEN:
                self._stats.rejected_calls += 1
                retry_after = self._get_retry_after()

                logger.warning(
                    "circuit_breaker_rejected",
                    service=self.service_name,
                    retry_after=retry_after,
                )

                if fallback:
                    return await self._execute_with_retry(fallback)
                raise CircuitBreakerError(self.service_name, self._state, retry_after)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._stats.rejected_calls += 1
                    if fallback:
                        return await self._execute_with_retry(fallback)
                    raise CircuitBreakerError(self.service_name, self._state, 1.0)
                self._half_open_calls += 1

        # 실제 호출 (lock 밖에서)
        try:
            result = await self._execute_with_retry(func)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure(e)
            raise

    async def _execute_with_retry(self, func: Callable[[], Any]) -> Any:
        """지수 백오프 재시도"""
        last_error: Exception | None = None

        for attempt in range(self.config.retry_count):
            try:
                self._stats.total_calls += 1

                # async 함수인지 확인
                result = func()
                if asyncio.iscoroutine(result):
                    return await result
                return result

            except Exception as e:
                last_error = e
                if attempt < self.config.retry_count - 1:
                    delay = min(
                        self.config.retry_base_delay_seconds * (2**attempt),
                        self.config.retry_max_delay_seconds,
                    )
                    logger.debug(
                        "circuit_breaker_retry",
                        service=self.service_name,
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry loop exit")

    async def _record_success(self) -> None:
        """성공 기록"""
        async with self._lock:
            self._call_results.append(True)
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # 성공하면 CLOSED로 복구
                await self._transition_to(CircuitState.CLOSED)
                logger.info(
                    "circuit_breaker_recovered",
                    service=self.service_name,
                )

    async def _record_failure(self, error: Exception) -> None:
        """실패 기록"""
        async with self._lock:
            self._call_results.append(False)
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.monotonic()

            logger.warning(
                "circuit_breaker_failure",
                service=self.service_name,
                error=str(error),
                state=self._state.value,
            )

            # 실패율 체크
            if self._should_open():
                await self._transition_to(CircuitState.OPEN)
                logger.error(
                    "circuit_breaker_opened",
                    service=self.service_name,
                    failure_rate=self._get_failure_rate(),
                )

    def _should_open(self) -> bool:
        """OPEN으로 전환해야 하는지 판단"""
        if len(self._call_results) < self.config.window_size:
            # 윈도우가 채워지지 않음
            consecutive_failures = 0
            for result in reversed(self._call_results):
                if not result:
                    consecutive_failures += 1
                else:
                    break
            return consecutive_failures >= self.config.failure_threshold

        # 실패율 기반
        failure_rate = self._get_failure_rate()
        return failure_rate >= self.config.failure_rate_threshold

    def _get_failure_rate(self) -> float:
        """현재 실패율"""
        if not self._call_results:
            return 0.0
        failures = sum(1 for r in self._call_results if not r)
        return failures / len(self._call_results)

    def _get_retry_after(self) -> float:
        """OPEN 상태 남은 시간"""
        elapsed = time.monotonic() - self._state_changed_at
        remaining = self.config.open_timeout_seconds - elapsed
        return max(0.0, remaining)

    async def _maybe_transition_state(self) -> None:
        """상태 전환 체크"""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._state_changed_at
            if elapsed >= self.config.open_timeout_seconds:
                await self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    "circuit_breaker_half_open",
                    service=self.service_name,
                )

    async def _transition_to(self, new_state: CircuitState) -> None:
        """상태 전환"""
        old_state = self._state
        self._state = new_state
        self._state_changed_at = time.monotonic()
        self._stats.state_transitions += 1

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            self._call_results.clear()

        logger.info(
            "circuit_breaker_state_changed",
            service=self.service_name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

    async def reset(self) -> None:
        """강제 리셋 (CLOSED로)"""
        async with self._lock:
            await self._transition_to(CircuitState.CLOSED)
            self._call_results.clear()
            logger.info("circuit_breaker_reset", service=self.service_name)

    def __repr__(self) -> str:
        return f"CircuitBreaker({self.service_name}, state={self._state.value})"


class CircuitBreakerRegistry:
    """
    서비스별 Circuit Breaker 레지스트리.

    Usage:
        registry = CircuitBreakerRegistry()
        qdrant_breaker = registry.get_or_create("qdrant")
        postgres_breaker = registry.get_or_create("postgres", config)
    """

    def __init__(self, default_config: CircuitBreakerConfig | None = None):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config = default_config or CircuitBreakerConfig()
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        service_name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """서비스별 Circuit Breaker 가져오기 (없으면 생성)"""
        async with self._lock:
            if service_name not in self._breakers:
                self._breakers[service_name] = CircuitBreaker(
                    service_name,
                    config or self._default_config,
                )
            return self._breakers[service_name]

    def get(self, service_name: str) -> CircuitBreaker | None:
        """서비스별 Circuit Breaker 가져오기 (동기)"""
        return self._breakers.get(service_name)

    async def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """모든 Circuit Breaker 통계"""
        return {
            name: {
                "state": breaker.state.value,
                "total_calls": breaker.stats.total_calls,
                "successful_calls": breaker.stats.successful_calls,
                "failed_calls": breaker.stats.failed_calls,
                "rejected_calls": breaker.stats.rejected_calls,
                "failure_rate": breaker._get_failure_rate(),
            }
            for name, breaker in self._breakers.items()
        }

    async def reset_all(self) -> None:
        """모든 Circuit Breaker 리셋"""
        for breaker in self._breakers.values():
            await breaker.reset()


# Global singleton (optional)
_global_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """글로벌 Circuit Breaker 레지스트리"""
    global _global_registry
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry
