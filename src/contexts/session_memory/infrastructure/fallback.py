"""
Fallback and Degradation Mechanisms

장애 발생 시 우아한 성능 저하 (Graceful Degradation)
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from src.infra.observability import get_logger, record_counter

logger = get_logger(__name__)

T = TypeVar("T")


class ServiceHealth(Enum):
    """서비스 건강 상태"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # 일부 기능 제한
    UNAVAILABLE = "unavailable"  # 완전 장애


class CircuitBreaker:
    """
    Circuit Breaker 패턴

    연속 실패 시 서비스 차단 -> 복구 시도 -> 정상화
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        recovery_timeout: int = 30,
    ):
        """
        Initialize circuit breaker

        Args:
            failure_threshold: 연속 실패 임계값
            timeout_seconds: Circuit Open 유지 시간
            recovery_timeout: 복구 시도 타임아웃
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.recovery_timeout = recovery_timeout

        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._state: ServiceHealth = ServiceHealth.HEALTHY

    @property
    def state(self) -> ServiceHealth:
        """현재 상태"""
        # Auto-recovery check
        if (
            self._state == ServiceHealth.UNAVAILABLE
            and self._last_failure_time is not None
            and (datetime.now() - self._last_failure_time).total_seconds() > self.timeout_seconds
        ):
            # Try half-open state (degraded)
            self._state = ServiceHealth.DEGRADED
            logger.info("circuit_breaker_half_open", service=id(self))

        return self._state

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any | None, bool]:
        """
        Circuit breaker를 통한 함수 호출

        Args:
            func: 호출할 함수
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            (result, success) 튜플
        """
        # Circuit open (unavailable)
        if self.state == ServiceHealth.UNAVAILABLE:
            logger.warning("circuit_breaker_open", service=func.__name__)
            record_counter("memory_circuit_breaker_rejected_total")
            return None, False

        try:
            # Call function with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else asyncio.to_thread(func, *args, **kwargs),
                timeout=self.recovery_timeout if self.state == ServiceHealth.DEGRADED else None,
            )

            # Success - reset counter
            self._on_success()
            return result, True

        except asyncio.TimeoutError:
            logger.error("circuit_breaker_timeout", service=func.__name__)
            self._on_failure()
            return None, False

        except Exception as e:
            logger.error("circuit_breaker_error", service=func.__name__, error=str(e))
            self._on_failure()
            return None, False

    def _on_success(self) -> None:
        """성공 시 처리"""
        if self._state == ServiceHealth.DEGRADED:
            # Degraded -> Healthy
            self._state = ServiceHealth.HEALTHY
            logger.info("circuit_breaker_recovered", service=id(self))

        self._failure_count = 0

    def _on_failure(self) -> None:
        """실패 시 처리"""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._failure_count >= self.failure_threshold:
            # Open circuit
            self._state = ServiceHealth.UNAVAILABLE
            logger.error(
                "circuit_breaker_opened",
                service=id(self),
                failures=self._failure_count,
            )
            record_counter("memory_circuit_breaker_opened_total")

    def reset(self) -> None:
        """수동 리셋"""
        self._failure_count = 0
        self._state = ServiceHealth.HEALTHY
        logger.info("circuit_breaker_reset", service=id(self))


class FallbackStrategy:
    """
    Fallback 전략

    Primary 실패 시 Secondary -> Tertiary 순서로 시도
    """

    def __init__(self):
        """Initialize fallback strategy"""
        self.circuit_breakers: dict[str, CircuitBreaker] = {}

    def get_or_create_breaker(self, service_name: str) -> CircuitBreaker:
        """
        Circuit breaker 가져오기 또는 생성

        Args:
            service_name: 서비스 이름

        Returns:
            CircuitBreaker
        """
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()

        return self.circuit_breakers[service_name]

    async def try_with_fallback(
        self,
        primary: Callable[[], Any],
        fallback: Callable[[], Any],
        service_name: str = "default",
    ) -> tuple[Any | None, str]:
        """
        Primary 실패 시 Fallback 시도

        Args:
            primary: Primary 함수
            fallback: Fallback 함수
            service_name: 서비스 이름

        Returns:
            (result, source) 튜플 ("primary" | "fallback")
        """
        breaker = self.get_or_create_breaker(service_name)

        # Try primary
        result, success = await breaker.call(primary)

        if success:
            return result, "primary"

        # Fallback
        logger.warning("fallback_triggered", service=service_name)
        record_counter("memory_fallback_triggered_total", labels={"service": service_name})

        try:
            result = await (fallback() if asyncio.iscoroutinefunction(fallback) else asyncio.to_thread(fallback))
            return result, "fallback"

        except Exception as e:
            logger.error("fallback_failed", service=service_name, error=str(e))
            return None, "failed"

    def get_health_status(self) -> dict[str, ServiceHealth]:
        """
        전체 서비스 건강 상태

        Returns:
            서비스별 상태 딕셔너리
        """
        return {name: breaker.state for name, breaker in self.circuit_breakers.items()}


class DegradationManager:
    """
    Degradation 관리자

    서비스별 우선순위에 따라 기능 제한
    """

    def __init__(self):
        """Initialize degradation manager"""
        self.feature_flags: dict[str, bool] = {
            # Core features (always on)
            "episodic_memory": True,
            "working_memory": True,
            # Advanced features (can be disabled)
            "embeddings": True,
            "reflection": True,
            "caching": True,
            "bug_patterns": True,
            "code_patterns": True,
        }

        self.degradation_levels = [
            # Level 0: Full functionality
            [],
            # Level 1: Disable reflection
            ["reflection"],
            # Level 2: Disable embeddings
            ["reflection", "embeddings"],
            # Level 3: Disable caching
            ["reflection", "embeddings", "caching"],
            # Level 4: Disable pattern learning
            ["reflection", "embeddings", "caching", "bug_patterns", "code_patterns"],
        ]

        self.current_level = 0

    def degrade(self, level: int) -> None:
        """
        Degradation level 설정

        Args:
            level: 0 (full) ~ 4 (minimal)
        """
        if level < 0 or level >= len(self.degradation_levels):
            logger.error("invalid_degradation_level", level=level)
            return

        self.current_level = level
        disabled = self.degradation_levels[level]

        # Disable features
        for feature in disabled:
            self.feature_flags[feature] = False

        logger.warning("degradation_level_set", level=level, disabled=disabled)
        record_counter("memory_degradation_triggered_total", labels={"level": str(level)})

    def is_enabled(self, feature: str) -> bool:
        """
        기능 활성화 여부

        Args:
            feature: 기능 이름

        Returns:
            True if enabled
        """
        return self.feature_flags.get(feature, False)

    def auto_degrade_on_error(self, error_rate: float) -> None:
        """
        에러율 기반 자동 degradation

        Args:
            error_rate: 에러율 (0.0-1.0)
        """
        if error_rate > 0.5:
            # Critical - minimal mode
            self.degrade(4)
        elif error_rate > 0.3:
            # High error - disable learning
            self.degrade(3)
        elif error_rate > 0.2:
            # Medium error - disable expensive features
            self.degrade(2)
        elif error_rate > 0.1:
            # Low error - disable reflection only
            self.degrade(1)
        else:
            # Healthy - full functionality
            self.degrade(0)


# Global instances
_fallback_strategy = FallbackStrategy()
_degradation_manager = DegradationManager()


def get_fallback_strategy() -> FallbackStrategy:
    """전역 fallback strategy 가져오기"""
    return _fallback_strategy


def get_degradation_manager() -> DegradationManager:
    """전역 degradation manager 가져오기"""
    return _degradation_manager
