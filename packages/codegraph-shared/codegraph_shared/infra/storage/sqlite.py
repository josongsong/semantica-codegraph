"""
SQLite Storage Adapter (개인 랩탑용)

PostgreSQL 대신 SQLite 사용:
- 설치 불필요
- 파일 기반 (data/codegraph.db)
- 메모리 <10MB
- 백업 = 파일 복사

동일한 인터페이스 제공 (PostgresStore와 호환)
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class SQLiteStore:
    """
    SQLite storage adapter (개인 랩탑용).

    PostgresStore와 동일한 인터페이스 제공.

    Features:
    - 파일 기반 (설치 불필요)
    - FTS5 full-text search
    - Connection pooling 불필요
    - 자동 schema migration

    Usage:
        store = SQLiteStore(db_path="data/codegraph.db")
        await store.initialize()

        rows = await store.fetch("SELECT * FROM users")
    """

    def __init__(
        self,
        db_path: str | Path = "data/codegraph.db",
        timeout: float = 30.0,
    ):
        """
        Initialize SQLite store.

        Args:
            db_path: SQLite DB 파일 경로 (기본: data/codegraph.db)
            timeout: Query timeout (초)
        """
        self.db_path = Path(db_path)
        self.timeout = timeout
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_connection(self) -> sqlite3.Connection:
        """Get or create connection."""
        if self._conn is None:
            # Run in thread pool (sqlite3 is blocking)
            loop = asyncio.get_event_loop()
            self._conn = await loop.run_in_executor(
                None,
                self._create_connection,
            )
            logger.info(f"SQLite connection created: {self.db_path}")

        return self._conn

    async def _ensure_pool(self) -> "SQLiteStore":
        """
        PostgresStore 호환용 - SQLite는 pool 대신 connection 사용.

        Returns self to allow:
            pool = await store._ensure_pool()
            async with pool.acquire() as conn: ...

        But SQLite doesn't need this pattern, so callers should use
        execute/fetch methods directly.
        """
        await self._get_connection()
        return self

    @property
    def pool(self) -> "SQLiteStore":
        """PostgresStore.pool 호환용."""
        return self

    def acquire(self):
        """
        PostgresStore pool.acquire() 호환용.

        Usage:
            async with store.acquire() as conn:
                await conn.execute(...)

        For SQLite, this just returns a wrapper around the connection.
        Note: Must NOT be async - returns async context manager directly.
        """
        return _SQLiteConnectionContext(self)

    def _create_connection(self) -> sqlite3.Connection:
        """Create SQLite connection (blocking)."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.timeout,
            check_same_thread=False,  # Allow multi-threading
        )

        # Enable FTS5 (full-text search)
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=NORMAL")  # Performance
        conn.execute("PRAGMA foreign_keys=ON")  # Foreign key constraints

        return conn

    async def initialize(self) -> None:
        """Initialize connection."""
        await self._get_connection()
        logger.info(f"SQLiteStore initialized: {self.db_path}")

    async def execute(self, query: str, *args: Any) -> str:
        """
        Execute query (INSERT/UPDATE/DELETE).

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Result status
        """
        async with self._lock:
            conn = await self._get_connection()
            loop = asyncio.get_event_loop()

            def _execute():
                cursor = conn.cursor()
                cursor.execute(query, args)
                conn.commit()
                return f"EXECUTE {cursor.rowcount}"

            return await loop.run_in_executor(None, _execute)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """
        Fetch multiple rows.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of rows (as dicts)
        """
        async with self._lock:
            conn = await self._get_connection()
            loop = asyncio.get_event_loop()

            def _fetch():
                conn.row_factory = sqlite3.Row  # Return as dict
                cursor = conn.cursor()
                cursor.execute(query, args)
                return [dict(row) for row in cursor.fetchall()]

            return await loop.run_in_executor(None, _fetch)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        """
        Fetch single row.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single row (as dict) or None
        """
        async with self._lock:
            conn = await self._get_connection()
            loop = asyncio.get_event_loop()

            def _fetchrow():
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, args)
                row = cursor.fetchone()
                return dict(row) if row else None

            return await loop.run_in_executor(None, _fetchrow)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """
        Fetch single value.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single value or None
        """
        row = await self.fetchrow(query, *args)
        if row:
            return next(iter(row.values()))
        return None

    async def health_check(self) -> bool:
        """
        Check database health.

        Returns:
            True if healthy
        """
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error(f"SQLite health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close connection."""
        if self._conn:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None
            logger.info("SQLite connection closed")

    async def __aenter__(self):
        """Context manager support."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()
        return False


class _SQLiteConnectionContext:
    """
    PostgresStore pool.acquire() 호환용 context manager.

    Usage:
        async with store.acquire() as conn:
            await conn.execute(...)
    """

    def __init__(self, store: SQLiteStore):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def execute(self, query: str, *args: Any) -> str:
        """Delegate to store. Convert $1, $2... to ?"""
        converted_query = self._convert_placeholders(query)
        return await self._store.execute(converted_query, *args)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Delegate to store. Convert $1, $2... to ?"""
        converted_query = self._convert_placeholders(query)
        return await self._store.fetch(converted_query, *args)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Delegate to store. Convert $1, $2... to ?"""
        converted_query = self._convert_placeholders(query)
        return await self._store.fetchrow(converted_query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Delegate to store. Convert $1, $2... to ?"""
        converted_query = self._convert_placeholders(query)
        return await self._store.fetchval(converted_query, *args)

    def _convert_placeholders(self, query: str) -> str:
        """Convert PostgreSQL syntax to SQLite."""
        import re

        # 1. $1, $2... → ?
        result = re.sub(r"\$\d+", "?", query)

        # 2. ::type → remove (SQLite has no type casting)
        result = re.sub(r"::\w+", "", result)

        # 3. JSONB → JSON (SQLite uses JSON, not JSONB)
        result = result.replace("JSONB", "JSON")
        result = result.replace("jsonb", "json")

        # 4. ON CONFLICT (...) DO UPDATE SET ... → REPLACE (simplified)
        # SQLite supports INSERT OR REPLACE but not full ON CONFLICT
        # For now, keep as-is since SQLite3 >= 3.24 supports ON CONFLICT

        return result

    def transaction(self):
        """
        PostgreSQL conn.transaction() 호환용.

        SQLite는 autocommit이 아니면 transaction이 자동 시작됨.
        """
        return _SQLiteTransactionContext(self._store)


class _SQLiteTransactionContext:
    """
    PostgreSQL transaction context 호환용.

    Usage:
        async with conn.transaction():
            await conn.execute(...)
    """

    def __init__(self, store: SQLiteStore):
        self._store = store
        self._started = False

    async def __aenter__(self):
        # SQLite: 명시적 BEGIN
        await self._store.execute("BEGIN IMMEDIATE")
        self._started = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._started:
            return False

        if exc_type is not None:
            # Rollback on error
            try:
                await self._store.execute("ROLLBACK")
            except Exception:
                pass  # Ignore if already rolled back
            return False
        # Commit on success
        await self._store.execute("COMMIT")
        return False


def create_sqlite_store(db_path: str | Path = "data/codegraph.db") -> SQLiteStore:
    """
    Factory function for SQLite store.

    Args:
        db_path: DB 파일 경로

    Returns:
        SQLiteStore instance
    """
    return SQLiteStore(db_path=db_path)
