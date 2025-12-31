"""
Infrastructure Layer Exceptions

SOTA-grade exception hierarchy for precise error handling and observability.
"""

from typing import Any

# ============================================================================
# Base Infrastructure Exception
# ============================================================================


class InfraException(Exception):
    """
    Base exception for all infrastructure errors.

    Attributes:
        message: Human-readable error message
        details: Additional context (dict)
        retryable: Whether the operation can be retried
        component: Which infra component failed
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        component: str = "unknown",
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.component = component

    def __str__(self) -> str:
        base = f"[{self.component}] {self.message}"
        if self.details:
            base += f" | details={self.details}"
        return base


# ============================================================================
# Database Exceptions
# ============================================================================


class DatabaseError(InfraException):
    """Base exception for database errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None, retryable: bool = False):
        super().__init__(message, details, retryable, component="postgres")


class ConnectionPoolExhaustedError(DatabaseError):
    """Connection pool exhausted (all connections in use)."""

    def __init__(self, pool_size: int, wait_time: float):
        super().__init__(
            f"Connection pool exhausted (size={pool_size}, wait={wait_time:.2f}s)",
            details={
                "pool_size": pool_size,
                "wait_time": wait_time,
                "suggestion": (
                    "Connection pool is full. Consider:\n"
                    f"  1. Increasing pool size (current: {pool_size})\n"
                    "  2. Checking for connection leaks\n"
                    "  3. Optimizing query performance"
                ),
            },
            retryable=True,
        )


class QueryTimeoutError(DatabaseError):
    """Database query exceeded timeout."""

    def __init__(self, query: str, timeout: float):
        super().__init__(
            f"Query timeout after {timeout}s",
            details={
                "query": query[:200],
                "timeout": timeout,
                "suggestion": (
                    "Query is too slow. Consider:\n"
                    "  1. Adding database indexes\n"
                    "  2. Optimizing query (use EXPLAIN)\n"
                    "  3. Increasing timeout threshold"
                ),
            },
            retryable=True,
        )


class TransactionError(DatabaseError):
    """Transaction commit/rollback failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details, retryable=False)


# ============================================================================
# Cache Exceptions
# ============================================================================


class CacheError(InfraException):
    """Base exception for cache errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None, retryable: bool = True):
        super().__init__(message, details, retryable, component="cache")


class RedisConnectionError(CacheError):
    """Redis connection failed."""

    def __init__(self, host: str, port: int, cause: Exception):
        super().__init__(
            f"Redis connection failed: {host}:{port}",
            details={"host": host, "port": port, "cause": str(cause)},
            retryable=True,
        )


class CacheInvalidationError(CacheError):
    """Cache invalidation pattern failed."""

    def __init__(self, pattern: str, reason: str):
        super().__init__(
            f"Failed to invalidate cache pattern: {pattern}",
            details={"pattern": pattern, "reason": reason},
            retryable=True,
        )


# ============================================================================
# Vector Store Exceptions
# ============================================================================


class VectorStoreError(InfraException):
    """Base exception for vector store errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None, retryable: bool = True):
        super().__init__(message, details, retryable, component="qdrant")


class VectorUpsertError(VectorStoreError):
    """Vector upsert operation failed."""

    def __init__(self, collection: str, vector_count: int, cause: Exception):
        super().__init__(
            f"Failed to upsert {vector_count} vectors to {collection}",
            details={"collection": collection, "vector_count": vector_count, "cause": str(cause)},
            retryable=True,
        )


class VectorSearchError(VectorStoreError):
    """Vector search operation failed."""

    def __init__(self, collection: str, cause: Exception):
        super().__init__(
            f"Vector search failed in {collection}",
            details={"collection": collection, "cause": str(cause)},
            retryable=True,
        )


# ============================================================================
# Graph Store Exceptions
# ============================================================================


class GraphStoreError(InfraException):
    """Base exception for graph store errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None, retryable: bool = True):
        super().__init__(message, details, retryable, component="memgraph")


class GraphQueryError(GraphStoreError):
    """Graph query execution failed."""

    def __init__(self, query: str, cause: Exception):
        super().__init__(
            f"Graph query failed: {cause}",
            details={"query": query[:200], "cause": str(cause)},
            retryable=True,
        )


# ============================================================================
# LLM Exceptions
# ============================================================================


class LLMError(InfraException):
    """Base exception for LLM errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None, retryable: bool = True, component: str = "llm"
    ):
        super().__init__(message, details, retryable, component)


class RateLimitExceededError(LLMError):
    """API rate limit exceeded."""

    def __init__(self, model: str, retry_after: float | None = None):
        super().__init__(
            f"Rate limit exceeded for {model}",
            details={
                "model": model,
                "retry_after": retry_after,
                "suggestion": (
                    f"API rate limit exceeded for {model}. "
                    f"Wait {retry_after or 60}s before retrying, or use a different model."
                ),
            },
            retryable=True,
        )


class LLMTimeoutError(LLMError):
    """LLM request timed out."""

    def __init__(self, model: str, timeout: float):
        super().__init__(
            f"LLM request timeout: {model} after {timeout}s",
            details={"model": model, "timeout": timeout},
            retryable=True,
        )


class TokenLimitExceededError(LLMError):
    """Token limit exceeded."""

    def __init__(self, model: str, token_count: int, limit: int):
        super().__init__(
            f"Token limit exceeded: {token_count}/{limit} for {model}",
            details={"model": model, "token_count": token_count, "limit": limit},
            retryable=False,
        )


# ============================================================================
# Circuit Breaker Exception
# ============================================================================


class CircuitBreakerOpenError(InfraException):
    """Circuit breaker is open (too many failures)."""

    def __init__(self, component: str, failure_count: int, threshold: int):
        super().__init__(
            f"Circuit breaker open for {component}: {failure_count}/{threshold} failures",
            details={
                "failure_count": failure_count,
                "threshold": threshold,
                "suggestion": (
                    f"The {component} service is experiencing failures. "
                    f"Wait 60s for circuit to enter HALF_OPEN state, or restart the service."
                ),
            },
            retryable=False,
            component=component,
        )
