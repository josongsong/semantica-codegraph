"""
Enhanced PostgreSQL Storage Adapter (SOTA)

Features:
- Circuit breaker for fault tolerance
- Retry with exponential backoff
- Connection pool metrics
- Health check with latency threshold
- Graceful degradation
"""

import asyncio
import time
from typing import Any

import asyncpg

from codegraph_shared.common.observability import get_logger, record_gauge, record_histogram
from codegraph_shared.infra.exceptions import (
    DatabaseError,
    QueryTimeoutError,
    TransactionError,
)
from codegraph_shared.infra.resilience import CircuitBreaker, CircuitBreakerConfig, RetryConfig, RetryPolicy

logger = get_logger(__name__)


class EnhancedPostgresStore:
    """
    SOTA PostgreSQL adapter with resilience patterns.

    Features:
    - Circuit breaker: Fail fast when DB is down
    - Retry: Auto-retry transient failures
    - Metrics: Connection pool usage, query latency
    - Health check: Latency-aware health status
    """

    def __init__(
        self,
        connection_string: str,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
        command_timeout: float = 30.0,
        max_idle_time: float = 300.0,
        # Resilience config
        enable_circuit_breaker: bool = True,
        enable_retry: bool = True,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
    ):
        """
        Initialize enhanced PostgreSQL store.

        Args:
            connection_string: PostgreSQL connection string
            min_pool_size: Minimum pool size
            max_pool_size: Maximum pool size
            command_timeout: Timeout for commands in seconds
            max_idle_time: Max idle time before connection recycling
            enable_circuit_breaker: Enable circuit breaker
            enable_retry: Enable retry with backoff
            circuit_breaker_config: Circuit breaker configuration
            retry_config: Retry configuration
        """
        self.connection_string = connection_string
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.command_timeout = command_timeout
        self.max_idle_time = max_idle_time
        self._pool: asyncpg.Pool | None = None

        # Resilience
        self.enable_circuit_breaker = enable_circuit_breaker
        self.enable_retry = enable_retry
        self.circuit_breaker = CircuitBreaker("postgres", circuit_breaker_config) if enable_circuit_breaker else None
        self.retry_policy = RetryPolicy(retry_config) if enable_retry else None

        # Metrics
        self._query_count = 0
        self._error_count = 0

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Ensure connection pool is initialized."""
        if self._pool is not None:
            return self._pool

        try:
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=self.command_timeout,
                max_inactive_connection_lifetime=self.max_idle_time,
            )
            logger.info(
                "postgres_pool_created",
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
            )
            return self._pool

        except Exception as e:
            logger.error("postgres_pool_creation_failed", error=str(e))
            raise DatabaseError(f"Failed to create connection pool: {e}", retryable=True) from e

    async def execute(
        self,
        query: str,
        *args: Any,
        timeout: float | None = None,
    ) -> str:
        """
        Execute query with resilience patterns.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional query timeout

        Returns:
            Result status

        Raises:
            DatabaseError: If query fails after retries
        """

        async def _execute():
            pool = await self._ensure_pool()

            # Record pool metrics
            self._record_pool_metrics(pool)

            try:
                if self.circuit_breaker and self.enable_circuit_breaker:
                    async with self.circuit_breaker:
                        async with pool.acquire() as conn:
                            result = await conn.execute(query, *args, timeout=timeout or self.command_timeout)
                            self._query_count += 1
                            return result
                else:
                    async with pool.acquire() as conn:
                        result = await conn.execute(query, *args, timeout=timeout or self.command_timeout)
                        self._query_count += 1
                        return result

            except asyncio.TimeoutError as e:
                self._error_count += 1
                raise QueryTimeoutError(query, timeout or self.command_timeout) from e
            except Exception as e:
                self._error_count += 1
                raise DatabaseError(f"Query execution failed: {e}", retryable=True) from e

        if self.retry_policy and self.enable_retry:
            return await self.retry_policy.execute(
                _execute,
                retryable=lambda e: isinstance(e, DatabaseError) and e.retryable,
            )
        else:
            return await _execute()

    async def fetch(
        self,
        query: str,
        *args: Any,
        timeout: float | None = None,
    ) -> list[asyncpg.Record]:
        """
        Fetch multiple rows with resilience.

        Args:
            query: SQL query
            *args: Query parameters
            timeout: Optional query timeout

        Returns:
            List of records
        """
        start = time.time()

        # Query start logging
        logger.debug(
            "postgres_query_start",
            query=query[:100],
            args_count=len(args),
        )

        async def _fetch():
            pool = await self._ensure_pool()
            self._record_pool_metrics(pool)

            try:
                if self.circuit_breaker and self.enable_circuit_breaker:
                    async with self.circuit_breaker:
                        async with pool.acquire() as conn:
                            result = await conn.fetch(query, *args, timeout=timeout or self.command_timeout)
                            self._query_count += 1
                            return result
                else:
                    async with pool.acquire() as conn:
                        result = await conn.fetch(query, *args, timeout=timeout or self.command_timeout)
                        self._query_count += 1
                        return result

            except asyncio.TimeoutError as e:
                self._error_count += 1
                raise QueryTimeoutError(query, timeout or self.command_timeout) from e
            except Exception as e:
                self._error_count += 1
                raise DatabaseError(f"Query fetch failed: {e}", retryable=True) from e

        try:
            result = await self.retry_policy.execute(_fetch) if self.retry_policy else await _fetch()

            # Record latency
            latency_ms = (time.time() - start) * 1000
            record_histogram("postgres_query_latency_ms", latency_ms)

            # Success logging
            logger.info(
                "postgres_query_success",
                query=query[:100],
                rows=len(result),
                latency_ms=f"{latency_ms:.2f}",
            )

            return result

        except Exception as e:
            latency_ms = (time.time() - start) * 1000

            # Error logging with suggestion
            logger.error(
                "postgres_query_failed",
                query=query[:100],
                error_type=type(e).__name__,
                error_msg=str(e),
                latency_ms=f"{latency_ms:.2f}",
                suggestion=getattr(e, "details", {}).get("suggestion", "N/A"),
            )
            raise

    async def fetchrow(
        self,
        query: str,
        *args: Any,
        timeout: float | None = None,
    ) -> asyncpg.Record | None:
        """Fetch single row with resilience."""
        import time

        start = time.time()

        async def _fetchrow():
            pool = await self._ensure_pool()
            self._record_pool_metrics(pool)

            if self.circuit_breaker and self.enable_circuit_breaker:
                async with self.circuit_breaker:
                    async with pool.acquire() as conn:
                        result = await conn.fetchrow(query, *args, timeout=timeout or self.command_timeout)
                        self._query_count += 1
                        return result
            else:
                async with pool.acquire() as conn:
                    result = await conn.fetchrow(query, *args, timeout=timeout or self.command_timeout)
                    self._query_count += 1
                    return result

        result = await self.retry_policy.execute(_fetchrow) if self.retry_policy else await _fetchrow()

        latency_ms = (time.time() - start) * 1000
        record_histogram("postgres_query_latency_ms", latency_ms)

        return result

    async def health_check(self, latency_threshold_ms: float = 100.0) -> tuple[bool, dict[str, Any]]:
        """
        Advanced health check with latency awareness.

        Args:
            latency_threshold_ms: Latency threshold for degraded state

        Returns:
            (healthy, details) tuple
            healthy: True if healthy, False if degraded/down
            details: Health check details
        """
        import time

        try:
            start = time.time()
            pool = await self._ensure_pool()

            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")

            latency_ms = (time.time() - start) * 1000

            is_healthy = result == 1 and latency_ms < latency_threshold_ms

            return is_healthy, {
                "status": "healthy" if is_healthy else "degraded",
                "latency_ms": latency_ms,
                "threshold_ms": latency_threshold_ms,
                "pool_size": pool.get_size(),
                "pool_free": pool.get_idle_size(),
                "query_count": self._query_count,
                "error_count": self._error_count,
                "error_rate": self._error_count / max(self._query_count, 1),
                "circuit_breaker": self.circuit_breaker.get_stats() if self.circuit_breaker else None,
            }

        except Exception as e:
            logger.error("postgres_health_check_failed", error=str(e))
            return False, {
                "status": "down",
                "error": str(e),
                "query_count": self._query_count,
                "error_count": self._error_count,
            }

    def _record_pool_metrics(self, pool: asyncpg.Pool):
        """Record connection pool metrics."""
        pool_size = pool.get_size()
        pool_free = pool.get_idle_size()
        pool_active = pool_size - pool_free

        record_gauge("postgres_pool_size", pool_size)
        record_gauge("postgres_pool_active", pool_active)
        record_gauge("postgres_pool_idle", pool_free)
        record_gauge("postgres_pool_utilization", pool_active / max(pool_size, 1))

    async def transaction(self):
        """
        Get transaction context manager with error handling.

        Usage:
            async with store.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
        """
        pool = await self._ensure_pool()
        conn = await pool.acquire()

        class TransactionContext:
            def __init__(self, connection, pool_instance):
                self._conn = connection
                self._pool = pool_instance
                self._transaction = None

            async def __aenter__(self):
                try:
                    self._transaction = self._conn.transaction()
                    await self._transaction.start()
                    return self._conn
                except Exception as e:
                    await self._pool.release(self._conn)
                    raise TransactionError(f"Failed to start transaction: {e}") from e

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                try:
                    if exc_type is None:
                        await self._transaction.commit()
                    else:
                        await self._transaction.rollback()
                except Exception as e:
                    logger.error("transaction_error", error=str(e))
                    raise TransactionError(f"Transaction error: {e}") from e
                finally:
                    await self._pool.release(self._conn)

                return False

        return TransactionContext(conn, pool)

    async def close(self):
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("postgres_pool_closed")

    async def __aenter__(self):
        """Context manager support."""
        await self._ensure_pool()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()
        return False
