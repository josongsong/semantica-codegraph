"""
Unit tests for resilience patterns.

Tests circuit breaker, retry, fallback, and bulkhead patterns.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from codegraph_shared.infra.exceptions import CircuitBreakerOpenError
from codegraph_shared.infra.resilience import (
    Bulkhead,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    Fallback,
    RetryConfig,
    RetryPolicy,
)

# ============================================================================
# Circuit Breaker Tests
# ============================================================================


class TestCircuitBreaker:
    """Test circuit breaker pattern."""

    @pytest.mark.asyncio
    async def test_closed_state_allows_requests(self):
        """Circuit breaker in CLOSED state allows all requests."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        async with breaker:
            pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_open_after_threshold_failures(self):
        """Circuit breaker opens after threshold failures."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3, timeout=1.0))

        # Fail 3 times
        for _ in range(3):
            try:
                async with breaker:
                    raise RuntimeError("Test failure")
            except RuntimeError:
                pass

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

        # 4th request should fail immediately
        with pytest.raises(CircuitBreakerOpenError):
            async with breaker:
                pass

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Circuit breaker enters HALF_OPEN after timeout."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, timeout=0.1))

        # Fail twice to open
        for _ in range(2):
            try:
                async with breaker:
                    raise RuntimeError("Test failure")
            except RuntimeError:
                pass

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.05)  # 0.2 → 0.05

        # Next request should enter HALF_OPEN
        async with breaker:
            pass

        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_closes_after_successes(self):
        """Circuit breaker closes after success threshold in HALF_OPEN."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2, success_threshold=2, timeout=0.1))

        # Open the circuit
        for _ in range(2):
            try:
                async with breaker:
                    raise RuntimeError("Test failure")
            except RuntimeError:
                pass

        # Wait for half-open
        await asyncio.sleep(0.05)  # 0.2 → 0.05

        # 2 successes should close
        for _ in range(2):
            async with breaker:
                pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Circuit breaker provides statistics."""
        breaker = CircuitBreaker("test")
        stats = breaker.get_stats()

        assert stats["name"] == "test"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0


# ============================================================================
# Retry Policy Tests
# ============================================================================


class TestRetryPolicy:
    """Test retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Retry succeeds on first attempt."""
        policy = RetryPolicy(RetryConfig(max_attempts=3))

        mock_func = AsyncMock(return_value="success")
        result = await policy.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_after_failure(self):
        """Retry retries after retryable failure."""
        policy = RetryPolicy(RetryConfig(max_attempts=3, base_delay=0.01))

        # Fail twice, succeed third time
        mock_func = AsyncMock(side_effect=[RuntimeError("fail"), RuntimeError("fail"), "success"])

        result = await policy.execute(
            mock_func,
            retryable=lambda e: True,
        )

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_for_non_retryable(self):
        """Retry doesn't retry non-retryable errors."""
        policy = RetryPolicy(RetryConfig(max_attempts=3))

        mock_func = AsyncMock(side_effect=ValueError("not retryable"))

        with pytest.raises(ValueError):
            await policy.execute(
                mock_func,
                retryable=lambda e: False,
            )

        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_max_attempts_exhausted(self):
        """Retry stops after max attempts."""
        policy = RetryPolicy(RetryConfig(max_attempts=3, base_delay=0.01))

        mock_func = AsyncMock(side_effect=RuntimeError("always fail"))

        with pytest.raises(RuntimeError):
            await policy.execute(
                mock_func,
                retryable=lambda e: True,
            )

        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Retry uses exponential backoff."""
        import time

        policy = RetryPolicy(RetryConfig(max_attempts=3, base_delay=0.1, exponential_base=2.0, jitter=False))

        attempts = []

        async def failing_func():
            attempts.append(time.time())
            if len(attempts) < 3:
                raise RuntimeError("fail")
            return "success"

        await policy.execute(failing_func, retryable=lambda e: True)

        # Check delays: ~0.1s, ~0.2s
        assert len(attempts) == 3
        delay1 = attempts[1] - attempts[0]
        delay2 = attempts[2] - attempts[1]

        assert 0.08 < delay1 < 0.15  # ~0.1s with tolerance
        assert 0.18 < delay2 < 0.25  # ~0.2s with tolerance

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """Retry calls on_retry callback."""
        policy = RetryPolicy(RetryConfig(max_attempts=3, base_delay=0.01))

        retry_calls = []

        def on_retry(e, attempt, delay):
            retry_calls.append((attempt, delay))

        mock_func = AsyncMock(side_effect=[RuntimeError("fail"), "success"])

        await policy.execute(
            mock_func,
            retryable=lambda e: True,
            on_retry=on_retry,
        )

        assert len(retry_calls) == 1
        assert retry_calls[0][0] == 1  # First retry


# ============================================================================
# Fallback Tests
# ============================================================================


class TestFallback:
    """Test fallback pattern."""

    @pytest.mark.asyncio
    async def test_primary_success(self):
        """Fallback uses primary when it succeeds."""
        primary = AsyncMock(return_value="primary")
        secondary = AsyncMock(return_value="secondary")

        fallback = Fallback(primary=primary, secondary=secondary)
        result = await fallback.execute()

        assert result == "primary"
        assert primary.call_count == 1
        assert secondary.call_count == 0

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        """Fallback uses secondary when primary fails."""
        primary = AsyncMock(side_effect=RuntimeError("primary failed"))
        secondary = AsyncMock(return_value="secondary")

        fallback = Fallback(primary=primary, secondary=secondary)
        result = await fallback.execute()

        assert result == "secondary"
        assert primary.call_count == 1
        assert secondary.call_count == 1


# ============================================================================
# Bulkhead Tests
# ============================================================================


class TestBulkhead:
    """Test bulkhead pattern."""

    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        """Bulkhead limits concurrent executions."""
        bulkhead = Bulkhead(max_concurrent=2)

        running = []
        completed = []

        async def task(task_id):
            async with bulkhead:
                running.append(task_id)
                await asyncio.sleep(0.03)  # 0.1 → 0.03
                running.remove(task_id)
                completed.append(task_id)

        # Start 4 tasks
        tasks = [asyncio.create_task(task(i)) for i in range(4)]

        # Wait a bit
        await asyncio.sleep(0.05)

        # Only 2 should be running
        assert len(running) == 2

        # Wait for all
        await asyncio.gather(*tasks)
        assert len(completed) == 4

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Bulkhead provides statistics."""
        bulkhead = Bulkhead(max_concurrent=5, max_queue_size=10)

        stats = bulkhead.get_stats()
        assert stats["max_concurrent"] == 5
        assert stats["active"] == 0
        assert stats["max_queue_size"] == 10
