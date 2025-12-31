"""
Resilience Patterns for Infrastructure

SOTA-grade circuit breaker, retry, and fallback patterns.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar

from codegraph_shared.common.observability import get_logger
from codegraph_shared.infra.exceptions import CircuitBreakerOpenError

logger = get_logger(__name__)

T = TypeVar("T")


# ============================================================================
# Circuit Breaker
# ============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int = 5  # Open after N failures
    success_threshold: int = 2  # Close after N successes in half-open
    timeout: float = 60.0  # Stay open for N seconds
    half_open_max_calls: int = 3  # Max calls in half-open state


class CircuitBreaker:
    """
    Circuit breaker pattern for fault tolerance.

    Prevents cascading failures by failing fast when a service is down.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Service is down, reject requests immediately
    - HALF_OPEN: Testing recovery, allow limited requests

    Usage:
        breaker = CircuitBreaker("redis", failure_threshold=5, timeout=60)

        async with breaker:
            result = await redis.get(key)
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None, debug: bool = False):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.debug = debug
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float | None = None
        self.half_open_calls = 0

    async def __aenter__(self):
        """Check if request is allowed."""
        if self.debug:
            logger.debug(
                "circuit_breaker_check",
                name=self.name,
                state=self.state.value,
                failure_count=self.failure_count,
            )

        if self.state == CircuitState.OPEN:
            # Check if timeout expired
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.config.timeout:
                logger.info("circuit_breaker_half_open", name=self.name)
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
            else:
                raise CircuitBreakerOpenError(
                    component=self.name,
                    failure_count=self.failure_count,
                    threshold=self.config.failure_threshold,
                )

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                raise CircuitBreakerOpenError(
                    component=self.name,
                    failure_count=self.failure_count,
                    threshold=self.config.failure_threshold,
                )
            self.half_open_calls += 1

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Record success or failure."""
        if exc_type is None:
            # Success
            self._on_success()
        else:
            # Failure
            self._on_failure()

        return False

    def _on_success(self):
        """Record successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info("circuit_breaker_closed", name=self.name)
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def _on_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("circuit_breaker_open", name=self.name, reason="failure_in_half_open")
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
            logger.error(
                "circuit_breaker_open",
                name=self.name,
                failure_count=self.failure_count,
                threshold=self.config.failure_threshold,
            )
            self.state = CircuitState.OPEN

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
        }

    def print_stats(self):
        """Print developer-friendly stats."""
        stats = self.get_stats()

        state_emoji = {
            "closed": "🟢",
            "open": "🔴",
            "half_open": "🟡",
        }

        print(
            f"""
Circuit Breaker: {self.name}
{"=" * 50}
State:     {state_emoji.get(stats["state"], "⚪")} {stats["state"].upper()}
Failures:  {stats["failure_count"]}/{self.config.failure_threshold}
Successes: {stats["success_count"]}/{self.config.success_threshold}
Last Fail: {stats["last_failure_time"] or "Never"}
{"=" * 50}
        """
        )


# ============================================================================
# Retry with Exponential Backoff
# ============================================================================


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Start with 1 second
    max_delay: float = 60.0  # Cap at 60 seconds
    exponential_base: float = 2.0  # 1s, 2s, 4s, 8s, ...
    jitter: bool = True  # Add randomness to prevent thundering herd


class RetryPolicy(Generic[T]):
    """
    Retry policy with exponential backoff and jitter.

    Features:
    - Exponential backoff: delay = base_delay * (exponential_base ** attempt)
    - Jitter: Add randomness to prevent thundering herd
    - Max attempts: Stop after N attempts
    - Selective retry: Only retry if exception is retryable

    Usage:
        policy = RetryPolicy(max_attempts=3)

        result = await policy.execute(
            lambda: redis.get(key),
            retryable=lambda e: isinstance(e, RedisConnectionError)
        )
    """

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        retryable: Callable[[Exception], bool] | None = None,
        on_retry: Callable[[Exception, int, float], None] | None = None,
    ) -> T:
        """
        Execute function with retry.

        Args:
            func: Async function to execute
            retryable: Function to check if exception is retryable
            on_retry: Callback on retry (for logging/metrics)

        Returns:
            Result of func()

        Raises:
            Last exception if all retries exhausted
        """
        last_exception: Exception | None = None

        for attempt in range(self.config.max_attempts):
            try:
                return await func()

            except Exception as e:
                last_exception = e

                # Check if retryable
                is_retryable = retryable(e) if retryable else getattr(e, "retryable", True)

                if not is_retryable or attempt == self.config.max_attempts - 1:
                    # Not retryable or last attempt
                    raise

                # Calculate delay
                delay = self._calculate_delay(attempt)

                # Callback
                if on_retry:
                    on_retry(e, attempt + 1, delay)

                logger.warning(
                    "retry_attempt",
                    attempt=attempt + 1,
                    max_attempts=self.config.max_attempts,
                    delay=delay,
                    error=str(e),
                )

                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry failed with no exception")

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt."""
        # Exponential backoff
        delay = self.config.base_delay * (self.config.exponential_base**attempt)

        # Cap at max_delay
        delay = min(delay, self.config.max_delay)

        # Add jitter
        if self.config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


# ============================================================================
# Fallback Pattern
# ============================================================================


class Fallback(Generic[T]):
    """
    Fallback pattern for graceful degradation.

    Try primary operation, fall back to secondary if it fails.

    Usage:
        fallback = Fallback(
            primary=lambda: redis.get(key),
            secondary=lambda: db.get(key),
            name="cache_with_db_fallback"
        )

        result = await fallback.execute()
    """

    def __init__(
        self,
        primary: Callable[[], Awaitable[T]],
        secondary: Callable[[], Awaitable[T]],
        name: str = "fallback",
    ):
        self.primary = primary
        self.secondary = secondary
        self.name = name

    async def execute(self) -> T:
        """Execute with fallback."""
        try:
            return await self.primary()
        except Exception as e:
            logger.warning("fallback_triggered", name=self.name, primary_error=str(e))
            return await self.secondary()


# ============================================================================
# Timeout Pattern
# ============================================================================


async def with_timeout(coro: Awaitable[T], timeout: float, operation: str = "operation") -> T:
    """
    Execute coroutine with timeout.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        operation: Operation name (for logging)

    Returns:
        Result of coroutine

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("timeout_exceeded", operation=operation, timeout=timeout)
        raise


# ============================================================================
# Bulkhead Pattern
# ============================================================================


class Bulkhead:
    """
    Bulkhead pattern for resource isolation.

    Limit concurrent executions to prevent resource exhaustion.

    Usage:
        bulkhead = Bulkhead(max_concurrent=10, max_queue_size=100)

        async with bulkhead:
            result = await expensive_operation()
    """

    def __init__(self, max_concurrent: int = 10, max_queue_size: int = 100):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.queue_size = 0

    async def __aenter__(self):
        """Acquire slot."""
        if self.queue_size >= self.max_queue_size:
            raise RuntimeError(f"Bulkhead queue full: {self.queue_size}/{self.max_queue_size}")

        self.queue_size += 1
        try:
            await self.semaphore.acquire()
            self.queue_size -= 1
        except Exception:
            self.queue_size -= 1
            raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release slot."""
        self.semaphore.release()
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get bulkhead statistics."""
        return {
            "max_concurrent": self.max_concurrent,
            "active": self.max_concurrent - self.semaphore._value,
            "queue_size": self.queue_size,
            "max_queue_size": self.max_queue_size,
        }
