"""
PostgreSQL Storage Adapter

Provides async connection pool for PostgreSQL operations.
Used by Fuzzy and Domain index adapters.
"""

import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


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
        min_pool_size: int = 2,
        max_pool_size: int = 10,
    ):
        """
        Initialize PostgreSQL store.

        Args:
            connection_string: PostgreSQL connection string
            min_pool_size: Minimum pool size
            max_pool_size: Maximum pool size
        """
        self.connection_string = connection_string
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        """
        Get connection pool.

        Note: This property will lazy-initialize the pool on first access.
        For synchronous initialization, call initialize() explicitly.

        Raises:
            RuntimeError: If pool is not initialized and cannot be created synchronously
        """
        if self._pool is None:
            raise RuntimeError(
                "PostgresStore pool not initialized. "
                "Call 'await store.initialize()' before using the pool, "
                "or use lazy initialization by awaiting _ensure_pool()."
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
        return self._pool

    async def initialize(self) -> None:
        """
        Initialize connection pool.

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
                command_timeout=60,
            )
            logger.info(f"PostgreSQL pool initialized: min={self.min_pool_size}, max={self.max_pool_size}")
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
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: list[tuple]) -> None:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query
            args: List of parameter tuples
        """
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
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
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)

    async def health_check(self) -> bool:
        """
        Check database connection health.

        Returns:
            True if healthy, False otherwise
        """
        try:
            if self._pool is None:
                return False

            async with self.pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    # ============================================================
    # Context Manager Support (Optional)
    # ============================================================

    async def __aenter__(self) -> "PostgresStore":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
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
    min_pool_size: int = 2,
    max_pool_size: int = 10,
) -> PostgresStore:
    """
    Factory function for PostgresStore.

    Args:
        connection_string: PostgreSQL connection string
        min_pool_size: Minimum pool size
        max_pool_size: Maximum pool size

    Returns:
        Configured PostgresStore instance
    """
    return PostgresStore(
        connection_string=connection_string,
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
    )
