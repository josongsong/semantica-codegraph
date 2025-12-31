"""Audit Store - RequestAuditLog 저장소"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..domain.models import RequestAuditLog


class AuditStore:
    """
    RequestAuditLog SQLite 저장소.

    Schema:
        - audit_logs: request_id, input_spec, resolved_spec, engine_versions, ..., timestamp
    """

    def __init__(self, db_path: str | Path = "data/audit_logs.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """DB 초기화"""
        with sqlite3.connect(self.db_path) as conn:
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
                    user_id TEXT,
                    session_id TEXT
                )
            """
            )

            # Index for replay queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON audit_logs(timestamp DESC)
            """
            )

    async def save(self, log: RequestAuditLog) -> None:
        """RequestAuditLog 저장"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audit_logs
                (request_id, input_spec, resolved_spec, engine_versions,
                 index_digests, llm_decisions, tool_trace, outputs,
                 timestamp, duration_ms, user_id, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    log.user_id,
                    log.session_id,
                ),
            )

    async def get(self, request_id: str) -> RequestAuditLog | None:
        """request_id로 로그 조회"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM audit_logs WHERE request_id = ?", (request_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return RequestAuditLog(
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
                user_id=row["user_id"],
                session_id=row["session_id"],
            )

    async def list(self, limit: int = 100, offset: int = 0) -> list[RequestAuditLog]:
        """최근 로그 목록"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )

            logs = []
            for row in cursor:
                logs.append(
                    RequestAuditLog(
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
                        user_id=row["user_id"],
                        session_id=row["session_id"],
                    )
                )

            return logs

    async def delete(self, request_id: str) -> bool:
        """로그 삭제 (GDPR 등 규제 대응)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM audit_logs WHERE request_id = ?", (request_id,))
            return cursor.rowcount > 0
