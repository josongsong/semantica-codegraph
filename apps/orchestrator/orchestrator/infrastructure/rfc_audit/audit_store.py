"""
AuditStore (RFC-027 Section 9)

SQLite-based audit log storage for replay & determinism.

Architecture:
- Infrastructure Layer
- Storage: SQLite (thread-safe)
- No business logic

RFC-027 Section 9.1: Stored Per Request
- input_spec, resolved_spec
- engine_versions, index_digests
- llm_decisions, tool_trace
- outputs, timestamp, duration_ms
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


# ============================================================
# RequestAuditLog Model (RFC-027 Section 9.1)
# ============================================================


class RequestAuditLog(BaseModel):
    """
    RequestAuditLog (RFC-027 Section 9.1)

    Audit log for request replay & determinism.

    Fields:
    - request_id: Request ID (unique)
    - input_spec: Original spec from LLM
    - resolved_spec: Resolved spec (after defaults)
    - engine_versions: Analyzer versions (e.g., {"sccp": "1.0.0", "taint": "3.0.1"})
    - index_digests: Index checksums (e.g., {"chunk_index": "sha256:abc123"})
    - llm_decisions: LLM decision trace (for bias detection)
    - tool_trace: Tool execution trace
    - outputs: Result outputs (envelope)
    - timestamp: Request timestamp
    - duration_ms: Execution time

    Validation:
    - request_id: non-empty
    - Dicts are JSON-serializable

    Example:
        RequestAuditLog(
            request_id="req_abc123",
            input_spec={"intent": "analyze", ...},
            resolved_spec={"intent": "analyze", "limits": {...}},
            engine_versions={"sccp": "1.0.0"},
            index_digests={"chunk_index": "sha256:abc123"},
            timestamp=datetime.now(),
            duration_ms=234.5
        )
    """

    request_id: str = Field(..., min_length=1, description="Request ID")
    input_spec: dict[str, Any] = Field(..., description="Original spec")
    resolved_spec: dict[str, Any] = Field(..., description="Resolved spec (with defaults)")
    engine_versions: dict[str, str] = Field(default_factory=dict, description="Engine versions")
    index_digests: dict[str, str] = Field(default_factory=dict, description="Index checksums")
    llm_decisions: list[dict[str, Any]] = Field(default_factory=list, description="LLM decision trace")
    tool_trace: list[dict[str, Any]] = Field(default_factory=list, description="Tool execution trace")
    outputs: dict[str, Any] = Field(default_factory=dict, description="Result outputs")
    timestamp: datetime = Field(default_factory=datetime.now, description="Request timestamp")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Execution time (milliseconds)")

    @field_validator("input_spec", "resolved_spec", "outputs")
    @classmethod
    def validate_json_serializable(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate dicts are JSON-serializable"""
        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Dict must be JSON-serializable: {e}")
        return v

    def to_replay_entry(self) -> dict[str, Any]:
        """
        Convert to replay entry format

        Returns:
            Dict for /rfc/replay/{id} response
        """
        return {
            "request_id": self.request_id,
            "input_spec": self.input_spec,
            "resolved_spec": self.resolved_spec,
            "engine_versions": self.engine_versions,
            "index_digests": self.index_digests,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }


# ============================================================
# AuditStore (SQLite Implementation)
# ============================================================


class AuditStore:
    """
    AuditStore (RFC-027 Section 9)

    SQLite-based audit log storage.

    Design:
    - Thread-safe (connection per operation)
    - Auto-create schema
    - JSON serialization for complex fields

    Storage:
    - SQLite for dev/single-user
    - PostgreSQL-ready schema

    Usage:
        store = AuditStore(db_path="audit.db")

        # Save
        log = RequestAuditLog(request_id="req_abc123", ...)
        store.save(log)

        # Get
        log = store.get("req_abc123")

    Thread-Safety:
        Each operation creates new connection (thread-safe)
    """

    def __init__(self, db_path: str | Path = "rfc_audit.db"):
        """
        Initialize audit store

        Args:
            db_path: SQLite database path

        Side Effects:
            Creates database file and schema if not exists
        """
        self.db_path = Path(db_path)
        self._init_schema()

        logger.info("audit_store_initialized", db_path=str(self.db_path))

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get SQLite connection (thread-safe)

        Returns:
            sqlite3.Connection

        Thread-Safety:
            New connection per call (thread-safe)
        """
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Dict-like access
        return conn

    def _init_schema(self) -> None:
        """
        Initialize database schema

        Schema:
            audit_logs table with:
            - request_id (PRIMARY KEY)
            - input_spec (TEXT, JSON)
            - resolved_spec (TEXT, JSON)
            - engine_versions (TEXT, JSON)
            - index_digests (TEXT, JSON)
            - llm_decisions (TEXT, JSON)
            - tool_trace (TEXT, JSON)
            - outputs (TEXT, JSON)
            - timestamp (TEXT, ISO format)
            - duration_ms (REAL)

        Side Effects:
            Creates table if not exists
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    request_id TEXT PRIMARY KEY,
                    input_spec TEXT NOT NULL,
                    resolved_spec TEXT NOT NULL,
                    engine_versions TEXT NOT NULL,
                    index_digests TEXT NOT NULL,
                    llm_decisions TEXT NOT NULL,
                    tool_trace TEXT NOT NULL,
                    outputs TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

            logger.debug("audit_schema_initialized")
        finally:
            conn.close()

    def save(self, log: RequestAuditLog) -> None:
        """
        Save audit log

        Args:
            log: RequestAuditLog

        Raises:
            ValueError: If save fails

        Side Effects:
            INSERT or REPLACE into database
        """
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

        except Exception as e:
            logger.error("audit_log_save_failed", request_id=log.request_id, error=str(e))
            raise ValueError(f"Failed to save audit log: {e}") from e
        finally:
            conn.close()

    def get(self, request_id: str) -> RequestAuditLog | None:
        """
        Get audit log by request_id

        Args:
            request_id: Request ID

        Returns:
            RequestAuditLog or None if not found

        Example:
            >>> log = store.get("req_abc123")
            >>> log.input_spec
            {"intent": "analyze", ...}
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM audit_logs WHERE request_id = ?
            """,
                (request_id,),
            )
            row = cursor.fetchone()

            if not row:
                logger.debug("audit_log_not_found", request_id=request_id)
                return None

            # Parse JSON fields
            log = RequestAuditLog(
                request_id=row["request_id"],
                input_spec=json.loads(row["input_spec"]),
                resolved_spec=json.loads(row["resolved_spec"]),
                engine_versions=json.loads(row["engine_versions"]),
                index_digests=json.loads(row["index_digests"]),
                llm_decisions=json.loads(row["llm_decisions"]),
                tool_trace=json.loads(row["tool_trace"]),
                outputs=json.loads(row["outputs"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                duration_ms=row["duration_ms"],
            )

            logger.debug("audit_log_retrieved", request_id=request_id)
            return log

        except Exception as e:
            logger.error("audit_log_get_failed", request_id=request_id, error=str(e))
            return None
        finally:
            conn.close()

    def list_recent(self, limit: int = 100) -> list[RequestAuditLog]:
        """
        List recent audit logs

        Args:
            limit: Maximum logs to return (1-1000)

        Returns:
            List of RequestAuditLog (newest first)

        Raises:
            ValueError: If limit invalid
        """
        if not 1 <= limit <= 1000:
            raise ValueError(f"limit must be 1-1000, got {limit}")

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()

            logs = []
            for row in rows:
                log = RequestAuditLog(
                    request_id=row["request_id"],
                    input_spec=json.loads(row["input_spec"]),
                    resolved_spec=json.loads(row["resolved_spec"]),
                    engine_versions=json.loads(row["engine_versions"]),
                    index_digests=json.loads(row["index_digests"]),
                    llm_decisions=json.loads(row["llm_decisions"]),
                    tool_trace=json.loads(row["tool_trace"]),
                    outputs=json.loads(row["outputs"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    duration_ms=row["duration_ms"],
                )
                logs.append(log)

            logger.debug("audit_logs_listed", count=len(logs))
            return logs

        finally:
            conn.close()

    def count(self) -> int:
        """
        Count total audit logs

        Returns:
            Total count
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM audit_logs")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def delete(self, request_id: str) -> bool:
        """
        Delete audit log

        Args:
            request_id: Request ID

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM audit_logs WHERE request_id = ?", (request_id,))
            conn.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("audit_log_deleted", request_id=request_id)
            return deleted

        finally:
            conn.close()
