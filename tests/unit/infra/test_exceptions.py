"""
Unit tests for infrastructure exceptions.
"""

import pytest

from codegraph_shared.infra.exceptions import (
    CacheError,
    CircuitBreakerOpenError,
    ConnectionPoolExhaustedError,
    DatabaseError,
    InfraException,
    LLMError,
    QueryTimeoutError,
    RateLimitExceededError,
    RedisConnectionError,
    TransactionError,
    VectorStoreError,
)


class TestInfraException:
    """Test base InfraException."""

    def test_basic_exception(self):
        """InfraException has message and component."""
        exc = InfraException("test error", component="test")

        assert str(exc) == "[test] test error"
        assert exc.component == "test"
        assert exc.retryable is False

    def test_exception_with_details(self):
        """InfraException includes details in string."""
        exc = InfraException("test error", details={"key": "value"}, component="test")

        assert "key" in str(exc)
        assert "value" in str(exc)

    def test_retryable_flag(self):
        """InfraException has retryable flag."""
        exc = InfraException("test", retryable=True)
        assert exc.retryable is True


class TestDatabaseExceptions:
    """Test database-related exceptions."""

    def test_connection_pool_exhausted(self):
        """ConnectionPoolExhaustedError has pool info."""
        exc = ConnectionPoolExhaustedError(pool_size=10, wait_time=5.5)

        assert exc.retryable is True
        assert exc.details["pool_size"] == 10
        assert exc.details["wait_time"] == 5.5

    def test_query_timeout(self):
        """QueryTimeoutError has query and timeout."""
        exc = QueryTimeoutError("SELECT * FROM table", timeout=30.0)

        assert exc.retryable is True
        assert "SELECT" in exc.details["query"]
        assert exc.details["timeout"] == 30.0

    def test_transaction_error(self):
        """TransactionError is not retryable."""
        exc = TransactionError("commit failed")

        assert exc.retryable is False


class TestCacheExceptions:
    """Test cache-related exceptions."""

    def test_redis_connection_error(self):
        """RedisConnectionError has host and port."""
        cause = ConnectionError("connection refused")
        exc = RedisConnectionError("localhost", 6379, cause)

        assert exc.retryable is True
        assert exc.details["host"] == "localhost"
        assert exc.details["port"] == 6379


class TestLLMExceptions:
    """Test LLM-related exceptions."""

    def test_rate_limit_exceeded(self):
        """RateLimitExceededError has model and retry_after."""
        exc = RateLimitExceededError("gpt-4", retry_after=60.0)

        assert exc.retryable is True
        assert exc.details["model"] == "gpt-4"
        assert exc.details["retry_after"] == 60.0

    def test_circuit_breaker_open(self):
        """CircuitBreakerOpenError has failure stats."""
        exc = CircuitBreakerOpenError("redis", failure_count=5, threshold=5)

        assert exc.retryable is False
        assert exc.component == "redis"
        assert exc.details["failure_count"] == 5
        assert exc.details["threshold"] == 5
