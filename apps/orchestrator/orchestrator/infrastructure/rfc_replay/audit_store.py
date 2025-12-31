"""
AuditStore (RFC-027 Section 9)

SQLite-based storage for RequestAuditLog.

Architecture:
- Infrastructure Layer
- Depends on: Domain (RequestAuditLog)
- Thread-safe (SQLite connection per thread)

RFC-027 Section 9: Replay & Determinism
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.orchestrator.orchestrator.domain.rfc_replay.models import RequestAuditLog
from apps.orchestrator.orchestrator.domain.rfc_replay.ports import IAuditStore
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class SQLiteAuditStore(IAuditStore):
    """
    SQLiteAuditStore (RFC-027 Section 9)

    SQLite-based audit log storage.

    Features:
    - CRUD operations
    - JSON serialization
    - Thread-safe (connection per method)
    - Auto schema creation

    Schema:
        audit_logs (
            request_id TEXT PRIMARY KEY,
            input_spec TEXT NOT NULL,
            resolved_spec TEXT NOT NULL,
            engine_versions TEXT,
            index_digests TEXT,
            llm_decisions TEXT,
            tool_trace TEXT,
            outputs TEXT,
            timestamp TEXT NOT NULL,
            duration_ms REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )

    Usage:
        store = SQLiteAuditStore("audit.db")

        # Save
        store.save(audit_log)

        # Load
        log = store.get("req_abc123")

        # List
        logs = store.list(limit=10)

    Thread-Safety:
        Creates new connection per method (SQLite thread-safe mode)
    """

    def __init__(self, db_path: str | Path = "audit.db"):
        """
        Initialize audit store

        Args:
            db_path: SQLite database path

        Raises:
            ValueError: If db_path invalid
        """
        if not db_path:
            raise ValueError("db_path cannot be empty")

        self.db_path = Path(db_path)
        logger.info("audit_store_initialized", db_path=str(self.db_path))

        # Create schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get SQLite connection (thread-safe)

        Returns:
            SQLite connection

        Thread-Safety:
            New connection per call (SQLite handles thread isolation)
        """
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Dict-like access
        return conn

    def _init_schema(self) -> None:
        """
        Initialize database schema

        Creates audit_logs table if not exists.

        Raises:
            sqlite3.Error: If schema creation fails
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    request_id TEXT PRIMARY KEY,
                    input_spec TEXT NOT NULL,
                    resolved_spec TEXT NOT NULL,
                    engine_versions TEXT,
                    index_digests TEXT,
                    llm_decisions TEXT,
                    tool_trace TEXT,
                    outputs TEXT,
                    timestamp TEXT NOT NULL,
                    duration_ms REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Index for timestamp queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON audit_logs(timestamp DESC)
            """
            )

            conn.commit()
            logger.info("audit_store_schema_initialized")

        except sqlite3.Error as e:
            logger.error("schema_init_failed", error=str(e))
            raise
        finally:
            conn.close()

    def save(self, log: RequestAuditLog) -> None:
        """
        Save audit log

        Args:
            log: RequestAuditLog to save

        Raises:
            ValueError: If log invalid
            sqlite3.Error: If save fails

        Example:
            >>> store.save(audit_log)
            >>> # Idempotent: can save same request_id multiple times (upsert)
        """
        if not isinstance(log, RequestAuditLog):
            raise ValueError(f"log must be RequestAuditLog, got {type(log)}")

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO audit_logs
                (request_id, input_spec, resolved_spec, engine_versions, index_digests,
                 llm_decisions, tool_trace, outputs, timestamp, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.request_id,
                    json.dumps(log.input_spec),
                    json.dumps(log.resolved_spec),
                    json.dumps(log.engine_versions),
                    json.dumps(log.index_digests),
                    json.dumps(log.llm_decisions),
                    json.dumps(log.tool_trace),
                    json.dumps(log.outputs),
                    log.timestamp.isoformat(),
                    log.duration_ms,
                ),
            )
            conn.commit()

            logger.info("audit_log_saved", request_id=log.request_id)

        except sqlite3.Error as e:
            logger.error("audit_log_save_failed", request_id=log.request_id, error=str(e))
            raise
        finally:
            conn.close()

    def get(self, request_id: str) -> RequestAuditLog | None:
        """
        Get audit log by request_id

        Args:
            request_id: Request ID

        Returns:
            RequestAuditLog or None if not found

        Raises:
            ValueError: If request_id invalid
            sqlite3.Error: If query fails

        Example:
            >>> log = store.get("req_abc123")
            >>> if log:
            ...     print(log.duration_ms)
        """
        if not request_id or not isinstance(request_id, str):
            raise ValueError(f"Invalid request_id: {request_id}")

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM audit_logs
                WHERE request_id = ?
            """,
                (request_id,),
            )

            row = cursor.fetchone()
            if not row:
                logger.info("audit_log_not_found", request_id=request_id)
                return None

            # Parse row to RequestAuditLog
            log = RequestAuditLog(
                request_id=row["request_id"],
                input_spec=json.loads(row["input_spec"]),
                resolved_spec=json.loads(row["resolved_spec"]),
                engine_versions=json.loads(row["engine_versions"]) if row["engine_versions"] else {},
                index_digests=json.loads(row["index_digests"]) if row["index_digests"] else {},
                llm_decisions=json.loads(row["llm_decisions"]) if row["llm_decisions"] else [],
                tool_trace=json.loads(row["tool_trace"]) if row["tool_trace"] else [],
                outputs=json.loads(row["outputs"]) if row["outputs"] else {},
                timestamp=datetime.fromisoformat(row["timestamp"]),
                duration_ms=row["duration_ms"] or 0.0,
            )

            logger.info("audit_log_loaded", request_id=request_id)
            return log

        except (sqlite3.Error, json.JSONDecodeError, ValueError) as e:
            logger.error("audit_log_load_failed", request_id=request_id, error=str(e))
            raise
        finally:
            conn.close()

    def list(self, limit: int = 100, offset: int = 0) -> list[RequestAuditLog]:
        """
        List audit logs (most recent first)

        Args:
            limit: Maximum logs to return (1-1000)
            offset: Offset for pagination

        Returns:
            List of RequestAuditLog (sorted by timestamp DESC)

        Raises:
            ValueError: If limit invalid
            sqlite3.Error: If query fails

        Example:
            >>> logs = store.list(limit=10)
            >>> for log in logs:
            ...     print(log.request_id)
        """
        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be 1-1000, got {limit}")

        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """,
                (limit, offset),
            )

            rows = cursor.fetchall()

            logs = []
            for row in rows:
                try:
                    log = RequestAuditLog(
                        request_id=row["request_id"],
                        input_spec=json.loads(row["input_spec"]),
                        resolved_spec=json.loads(row["resolved_spec"]),
                        engine_versions=json.loads(row["engine_versions"]) if row["engine_versions"] else {},
                        index_digests=json.loads(row["index_digests"]) if row["index_digests"] else {},
                        llm_decisions=json.loads(row["llm_decisions"]) if row["llm_decisions"] else [],
                        tool_trace=json.loads(row["tool_trace"]) if row["tool_trace"] else [],
                        outputs=json.loads(row["outputs"]) if row["outputs"] else {},
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        duration_ms=row["duration_ms"] or 0.0,
                    )
                    logs.append(log)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("skip_corrupted_log", request_id=row["request_id"], error=str(e))
                    continue

            logger.info("audit_logs_listed", count=len(logs), limit=limit, offset=offset)
            return logs

        except sqlite3.Error as e:
            logger.error("audit_logs_list_failed", error=str(e))
            raise
        finally:
            conn.close()

    def delete(self, request_id: str) -> bool:
        """
        Delete audit log

        Args:
            request_id: Request ID

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If request_id invalid
            sqlite3.Error: If delete fails

        Example:
            >>> deleted = store.delete("req_abc123")
            >>> assert deleted
        """
        if not request_id:
            raise ValueError("request_id cannot be empty")

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                DELETE FROM audit_logs
                WHERE request_id = ?
            """,
                (request_id,),
            )
            conn.commit()

            deleted = cursor.rowcount > 0

            if deleted:
                logger.info("audit_log_deleted", request_id=request_id)
            else:
                logger.info("audit_log_not_found_for_delete", request_id=request_id)

            return deleted

        except sqlite3.Error as e:
            logger.error("audit_log_delete_failed", request_id=request_id, error=str(e))
            raise
        finally:
            conn.close()

    def count(self) -> int:
        """
        Count total audit logs

        Returns:
            Total count

        Example:
            >>> store.count()
            42
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM audit_logs")
            count = cursor.fetchone()[0]
            return count
        finally:
            conn.close()
