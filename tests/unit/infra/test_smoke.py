"""
5초 안에 끝나는 smoke test.

개인 랩탑에서 빠르게 확인용.
"""

import asyncio

import pytest

from codegraph_shared.infra.exceptions import CircuitBreakerOpenError, QueryTimeoutError
from codegraph_shared.infra.resilience import CircuitBreaker, RetryConfig, RetryPolicy


@pytest.mark.asyncio
async def test_smoke_circuit_breaker():
    """Circuit breaker 기본 동작만 확인."""
    breaker = CircuitBreaker("test")

    # 성공 케이스
    async with breaker:
        pass

    assert breaker.state.value == "closed"


@pytest.mark.asyncio
async def test_smoke_retry():
    """Retry 기본 동작만 확인."""
    policy = RetryPolicy(RetryConfig(max_attempts=2, base_delay=0.01))

    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Fail once")
        return "success"

    result = await policy.execute(func, retryable=lambda e: True)

    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_smoke_exception_details():
    """Exception에 details와 suggestion이 있는지 확인."""
    exc = QueryTimeoutError("SELECT 1", 30.0)

    assert "timeout" in exc.details
    assert "suggestion" in exc.details  # ✅ 추가된 기능
    assert exc.retryable is True
    assert "Consider" in exc.details["suggestion"]


@pytest.mark.asyncio
async def test_smoke_circuit_breaker_print_stats():
    """Circuit breaker print_stats 실행 확인."""
    breaker = CircuitBreaker("test", debug=True)

    # print_stats가 오류 없이 실행되는지 확인
    breaker.print_stats()  # Should not raise
