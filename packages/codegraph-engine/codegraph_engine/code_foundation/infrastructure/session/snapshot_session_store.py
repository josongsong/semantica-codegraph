"""
Snapshot Session Store - SQLite Implementation (SOTA)

RFC-052: MCP Service Layer Architecture
Implements "Snapshot Stickiness" - session-based snapshot pinning.

SOTA Improvements:
- Connection pool (shared with EvidenceRepository pattern)
- Transaction support
- WAL mode for concurrent access
- Prepared statement caching

Design Principles:
- Each session locks to a specific snapshot
- All queries within a session use the same snapshot
- Ensures temporal consistency for agent reasoning
- Session can be explicitly upgraded to newer snapshot

Schema:
- session_snapshots table
- session_id (PK) → snapshot_id mapping

Lifecycle:
- Session starts → latest stable snapshot is auto-locked
- Session continues → same snapshot is used
- Session ends → mapping can be GC'd
- Explicit update → session can be upgraded to newer snapshot
"""

import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SessionConnectionPool:
    """
    Lightweight connection pool for session store.

    Similar to ConnectionPool in evidence_repository_sqlite.py
    but optimized for session workload (fewer connections).
    """

    def __init__(self, db_path: Path, pool_size: int = 3):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections: list[sqlite3.Connection] = []
        self._in_use: set[sqlite3.Connection] = set()

    def _create_connection(self) -> sqlite3.Connection:
        """Create connection with WAL mode"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def acquire(self) -> sqlite3.Connection:
        """Acquire connection"""
        for conn in self._connections:
            if conn not in self._in_use:
                self._in_use.add(conn)
                return conn

        if len(self._connections) < self.pool_size:
            conn = self._create_connection()
            self._connections.append(conn)
            self._in_use.add(conn)
            return conn

        logger.warning("session_pool_exhausted", pool_size=self.pool_size)
        return self._create_connection()

    def release(self, conn: sqlite3.Connection) -> None:
        """Release connection"""
        if conn in self._in_use:
            self._in_use.remove(conn)

    def close_all(self) -> None:
        """Close all connections"""
        for conn in self._connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning("session_conn_close_failed", error=str(e))
        self._connections.clear()
        self._in_use.clear()


class SnapshotSessionStore:
    """
    SQLite-based snapshot session store.

    Manages session → snapshot mapping for Snapshot Stickiness.
    """

    # Schema
    _CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS session_snapshots (
            session_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            locked_at TEXT NOT NULL  -- ISO format
        );
        
        CREATE INDEX IF NOT EXISTS idx_session_snapshot 
        ON session_snapshots(snapshot_id);
        
        CREATE INDEX IF NOT EXISTS idx_session_repo 
        ON session_snapshots(repo_id);
    """

    def __init__(self, db_path: Path | str, pool_size: int = 3):
        """
        Initialize snapshot session store.

        Args:
            db_path: Path to SQLite database file
            pool_size: Connection pool size (default: 3)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize connection pool
        self._pool = SessionConnectionPool(self.db_path, pool_size)

        # Initialize schema
        self._init_schema()

        logger.info(
            "snapshot_session_store_initialized",
            db_path=str(self.db_path),
            pool_size=pool_size,
        )

    def _init_schema(self) -> None:
        """Create tables and indexes"""
        conn = self._pool.acquire()
        try:
            conn.executescript(self._CREATE_TABLE_SQL)
        finally:
            self._pool.release(conn)

    @asynccontextmanager
    async def _connection(self):
        """Context manager for connection lifecycle"""
        conn = self._pool.acquire()
        try:
            yield conn
        finally:
            self._pool.release(conn)

    def close(self) -> None:
        """Close all connections"""
        self._pool.close_all()
        logger.info("snapshot_session_store_closed")

    async def lock_snapshot(
        self,
        session_id: str,
        snapshot_id: str,
        repo_id: str,
    ) -> None:
        """
        Lock session to snapshot (with transaction).

        Args:
            session_id: Session ID
            snapshot_id: Snapshot ID to lock
            repo_id: Repository ID

        Raises:
            ValueError: If session already locked to different snapshot
        """
        # Check existing lock
        existing = await self.get_snapshot(session_id)
        if existing and existing != snapshot_id:
            raise ValueError(
                f"Session {session_id} already locked to snapshot {existing}, "
                f"cannot change to {snapshot_id}. Use update_snapshot() for explicit upgrade."
            )

        locked_at = datetime.now().isoformat()

        async with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")

                conn.execute(
                    """
                    INSERT OR REPLACE INTO session_snapshots
                    (session_id, snapshot_id, repo_id, locked_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (session_id, snapshot_id, repo_id, locked_at),
                )

                conn.execute("COMMIT")

                logger.info(
                    "snapshot_locked",
                    session_id=session_id,
                    snapshot_id=snapshot_id,
                    repo_id=repo_id,
                )

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error("snapshot_lock_failed", error=str(e))
                raise

    async def get_snapshot(self, session_id: str) -> str | None:
        """
        Get locked snapshot for session.

        Args:
            session_id: Session ID

        Returns:
            Snapshot ID or None if not locked
        """
        async with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT snapshot_id FROM session_snapshots
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()

        return row["snapshot_id"] if row else None

    async def update_snapshot(
        self,
        session_id: str,
        new_snapshot_id: str,
    ) -> None:
        """
        Explicitly upgrade session to newer snapshot (with transaction).

        Args:
            session_id: Session ID
            new_snapshot_id: New snapshot ID

        Raises:
            ValueError: If session not found
        """
        # Check session exists
        existing = await self.get_snapshot(session_id)
        if not existing:
            raise ValueError(f"Session {session_id} not found")

        locked_at = datetime.now().isoformat()

        async with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")

                conn.execute(
                    """
                    UPDATE session_snapshots
                    SET snapshot_id = ?,
                        locked_at = ?
                    WHERE session_id = ?
                    """,
                    (new_snapshot_id, locked_at, session_id),
                )

                conn.execute("COMMIT")

                logger.info(
                    "snapshot_upgraded",
                    session_id=session_id,
                    old_snapshot=existing,
                    new_snapshot=new_snapshot_id,
                )

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error("snapshot_upgrade_failed", error=str(e))
                raise

    async def release_session(self, session_id: str) -> bool:
        """
        Release session lock (GC with transaction).

        Args:
            session_id: Session ID

        Returns:
            True if session was released, False if not found
        """
        async with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")

                cursor = conn.execute(
                    """
                    DELETE FROM session_snapshots
                    WHERE session_id = ?
                    """,
                    (session_id,),
                )
                deleted = cursor.rowcount > 0

                conn.execute("COMMIT")

                if deleted:
                    logger.info("session_released", session_id=session_id)

                return deleted

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error("session_release_failed", error=str(e))
                raise

    async def list_sessions_by_snapshot(self, snapshot_id: str) -> list[str]:
        """
        List all sessions using a snapshot.

        Useful for snapshot GC impact analysis.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            List of session IDs
        """
        async with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT session_id FROM session_snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            )
            rows = cursor.fetchall()

        return [row["session_id"] for row in rows]

    async def cleanup_old_sessions(self, days: int = 7) -> int:
        """
        Cleanup sessions older than N days (with transaction).

        Args:
            days: Age threshold in days

        Returns:
            Number of sessions cleaned up
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

        async with self._connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")

                cursor = conn.execute(
                    """
                    DELETE FROM session_snapshots
                    WHERE locked_at < ?
                    """,
                    (cutoff_iso,),
                )
                deleted_count = cursor.rowcount

                conn.execute("COMMIT")

                logger.info("session_gc", days=days, deleted=deleted_count)
                return deleted_count

            except Exception as e:
                conn.execute("ROLLBACK")
                logger.error("session_gc_failed", error=str(e))
                raise

    async def get_session_info(self, session_id: str) -> dict | None:
        """
        Get full session info.

        Args:
            session_id: Session ID

        Returns:
            Dict with snapshot_id, repo_id, locked_at or None
        """
        async with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT snapshot_id, repo_id, locked_at
                FROM session_snapshots
                WHERE session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "snapshot_id": row["snapshot_id"],
            "repo_id": row["repo_id"],
            "locked_at": row["locked_at"],
        }
