"""
SQLite Write Queue (RFC-020 Phase 6)

Single-writer pattern for SQLite concurrency handling.

Architecture:
- Infrastructure layer
- Async queue-based write serialization
- Multiple readers, single writer

Performance:
- Sequential write: ~1ms/operation
- 100 concurrent: ~100ms (queued)
"""

import asyncio
import sqlite3

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class SQLiteWriteQueue:
    """
    SQLite write queue (single-writer pattern)

    Handles SQLite concurrency limitation:
    - Multiple readers: OK
    - Multiple writers: SQLITE_BUSY error

    Solution: Queue all writes to single writer thread
    """

    def __init__(self, db_path: str):
        """
        Initialize write queue

        Args:
            db_path: SQLite database path
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.write_queue: asyncio.Queue | None = None
        self.writer_task = None
        self._started = False

    def _ensure_started(self):
        """
        Ensure writer loop started (lazy)

        Called on first execute(), not in __init__ (event loop may not exist)
        """
        if not self._started:
            if not self.write_queue:
                self.write_queue = asyncio.Queue()
            self.writer_task = asyncio.create_task(self._writer_loop())
            self._started = True

    async def _writer_loop(self):
        """Single writer thread"""
        while True:
            try:
                operation, result_future = await self.write_queue.get()
                try:
                    result = operation(self.db)
                    result_future.set_result(result)
                except Exception as e:
                    result_future.set_exception(e)
            except Exception as e:
                logger.error("Writer loop error", error=str(e))

    async def execute(self, query: str, args: tuple):
        """
        Execute write query (queued)

        Args:
            query: SQL query
            args: Query arguments

        Returns:
            Query result
        """
        self._ensure_started()  # Lazy start

        future = asyncio.Future()

        def operation(db):
            cursor = db.execute(query, args)
            db.commit()
            return cursor.lastrowid

        if self.write_queue:
            await self.write_queue.put((operation, future))

        return await future
