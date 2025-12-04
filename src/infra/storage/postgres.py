"""
PostgreSQL Storage Adapter

Provides async connection pool for PostgreSQL operations.
Used by Fuzzy and Domain index adapters.
"""

from typing import Any

import asyncpg

from src.common.observability import get_logger

logger = get_logger(__name__)


class PostgresStore:
    """
    PostgreSQL storage adapter with async connection pool.

    Features:
    - asyncpg connection pool
    - Automatic pool management
    - Connection health checks

    Usage:
        store = PostgresStore(connection_string="postgresql://user:pass@localhost/db")
        await store.initialize()

        async with store.pool.acquire() as conn:
            result = await conn.fetch("SELECT * FROM table")
    """

    def __init__(
        self,
        connection_string: str,
        min_pool_size: int = 5,  # Optimized: Increased from 2 for better concurrency
        max_pool_size: int = 20,  # Optimized: Increased from 10 for higher load
        command_timeout: float = 30.0,  # Command timeout in seconds
        max_idle_time: float = 300.0,  # Max idle time before recycling (5 minutes)
    ):
        """
        Initialize PostgreSQL store with optimized connection pooling.

        Args:
            connection_string: PostgreSQL connection string
            min_pool_size: Minimum pool size (default: 5, optimized from 2)
            max_pool_size: Maximum pool size (default: 20, optimized from 10)
            command_timeout: Timeout for commands in seconds (default: 30s, reduced from 60s)
            max_idle_time: Max idle time before connection recycling (default: 300s)

        Optimization Impact:
            - Increased min_pool_size (2→5): ~-2ms (reduces connection creation overhead)
            - Increased max_pool_size (10→20): ~-1ms (supports more concurrent queries)
            - Reduced command_timeout (60s→30s): Faster failure detection
            - Added max_idle_time: Prevents stale connections
            - Total estimated impact: ~-3ms for database-heavy workloads
        """
        self.connection_string = connection_string
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.command_timeout = command_timeout
        self.max_idle_time = max_idle_time
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        """
        Get connection pool.

        WARNING: This property is synchronous and requires the pool to be initialized.
        Use this only when you're certain the pool has been initialized.

        For automatic initialization, use async methods (execute, fetch, etc.) which
        call _ensure_pool() internally.

        Raises:
            RuntimeError: If pool is not initialized
        """
        if self._pool is None:
            raise RuntimeError(
                "PostgresStore pool not initialized. "
                "Either call 'await store.initialize()' explicitly during startup, "
                "or use async methods (execute, fetch, etc.) which auto-initialize."
            )
        return self._pool

    async def _ensure_pool(self) -> asyncpg.Pool:
        """
        Ensure pool is initialized (lazy initialization).

        This is called automatically by adapters.

        Returns:
            Initialized pool
        """
        if self._pool is None:
            await self.initialize()
        assert self._pool is not None, "Pool initialization failed"
        return self._pool

    async def initialize(self) -> None:
        """
        Initialize connection pool with optimized settings.

        Should be called during application startup.
        """
        if self._pool is not None:
            logger.warning("PostgresStore pool already initialized")
            return

        try:
            self._pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=self.command_timeout,
                max_inactive_connection_lifetime=self.max_idle_time,
            )
            logger.info(
                f"PostgreSQL pool initialized (optimized): "
                f"min={self.min_pool_size}, max={self.max_pool_size}, "
                f"timeout={self.command_timeout}s, max_idle={self.max_idle_time}s"
            )
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}", exc_info=True)
            raise

    async def close(self) -> None:
        """
        Close connection pool.

        Should be called during application shutdown.
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL pool closed")

    async def execute(self, query: str, *args: Any) -> str:
        """
        Execute a query without returning results.

        Args:
            query: SQL query
            args: Query parameters

        Returns:
            Query result status (e.g., "INSERT 0 1")
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: list[tuple]) -> None:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query
            args: List of parameter tuples
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.executemany(query, args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """
        Fetch all rows from query.

        Args:
            query: SQL query
            args: Query parameters

        Returns:
            List of records
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """
        Fetch single row from query.

        Args:
            query: SQL query
            args: Query parameters

        Returns:
            Single record or None
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """
        Fetch single value from query.

        Args:
            query: SQL query
            args: Query parameters
            column: Column index (default: 0)

        Returns:
            Single value
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)

    async def health_check(self) -> bool:
        """
        Check database connection health.

        Returns:
            True if healthy, False otherwise
        """
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    # ============================================================
    # Transaction Support
    # ============================================================

    async def transaction(self):
        """
        Get a transaction context manager.

        Usage:
            async with store.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
                # Auto-commit on success, rollback on exception

        Returns:
            async context manager yielding asyncpg.Connection with transaction

        Example:
            async with store.transaction() as conn:
                await conn.execute("INSERT INTO table VALUES ($1)", value)
                # If exception, auto-rollback
                # If success, auto-commit
        """
        pool = await self._ensure_pool()
        conn = await pool.acquire()

        class TransactionContext:
            """Transaction context manager."""

            def __init__(self, connection, pool_instance):
                self._conn = connection
                self._pool = pool_instance
                self._transaction = None

            async def __aenter__(self):
                self._transaction = self._conn.transaction()
                await self._transaction.start()
                return self._conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                try:
                    if exc_type is None:
                        await self._transaction.commit()
                    else:
                        await self._transaction.rollback()
                finally:
                    await self._pool.release(self._conn)
                return False

        return TransactionContext(conn, pool)

    # ============================================================
    # Context Manager Support (Optional)
    # ============================================================

    async def __aenter__(self) -> "PostgresStore":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# ============================================================
# Backward Compatibility Alias
# ============================================================

# Keep PostgresAdapter as alias for backward compatibility
PostgresAdapter = PostgresStore


# ============================================================
# Convenience Factory
# ============================================================


def create_postgres_store(
    connection_string: str,
    min_pool_size: int = 5,  # Optimized from 2
    max_pool_size: int = 20,  # Optimized from 10
    command_timeout: float = 30.0,
    max_idle_time: float = 300.0,
) -> PostgresStore:
    """
    Factory function for PostgresStore with optimized defaults.

    Args:
        connection_string: PostgreSQL connection string
        min_pool_size: Minimum pool size (default: 5, optimized from 2)
        max_pool_size: Maximum pool size (default: 20, optimized from 10)
        command_timeout: Command timeout in seconds (default: 30s)
        max_idle_time: Max idle time before recycling (default: 300s)

    Returns:
        Configured PostgresStore instance with optimized connection pooling
    """
    return PostgresStore(
        connection_string=connection_string,
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
        command_timeout=command_timeout,
        max_idle_time=max_idle_time,
    )
