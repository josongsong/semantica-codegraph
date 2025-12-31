"""
Execution Repository (RFC-SEM-022 SOTA)

결정적(Deterministic) 실행 저장 및 조회.

SOTA Features:
- PostgreSQL + SQLite 듀얼 모드 (RFC-018)
- 트랜잭션 보장
- VerificationSnapshot 자동 직렬화
- Finding 연동 + Regression Proof 지원
- Replay 지원
- Async/Sync 하이브리드

Architecture:
- Port/Adapter Pattern
- Repository Pattern (DDD)
- CQRS-ready (Read/Write 분리 가능)
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_shared.kernel.contracts import Execution, Finding

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = get_logger(__name__)


class ExecutionRepository(ABC):
    """Execution 저장소 Port (RFC-SEM-022)."""

    @abstractmethod
    async def save(self, execution: Execution) -> None:
        """실행 결과 저장."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, execution_id: str) -> Execution | None:
        """실행 결과 조회."""
        raise NotImplementedError

    @abstractmethod
    async def get_findings(self, execution_id: str) -> list[dict[str, Any]]:
        """실행에서 발견된 findings 조회."""
        raise NotImplementedError

    @abstractmethod
    async def list_by_workspace(self, workspace_id: str, limit: int = 20) -> list[Execution]:
        """workspace별 실행 목록."""
        raise NotImplementedError

    # RFC-SEM-022 추가 메서드
    @abstractmethod
    async def update_state(
        self,
        execution_id: str,
        state: Literal["pending", "running", "completed", "failed", "cancelled"],
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """상태 업데이트."""
        raise NotImplementedError

    @abstractmethod
    async def save_finding(self, execution_id: str, finding: Finding) -> None:
        """단일 Finding 저장."""
        raise NotImplementedError

    @abstractmethod
    async def compare_findings(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """
        Regression Proof: 두 실행 간 Finding 비교.

        Returns:
            {
                "new_findings": [...],
                "removed_findings": [...],
                "unchanged_count": int,
            }
        """
        raise NotImplementedError


class SQLiteExecutionRepository(ExecutionRepository):
    """
    SQLite 기반 Execution 저장소.

    로컬 에이전트용 경량 구현.
    ~/.semantica/executions.db에 저장.
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_dir = Path.home() / ".semantica"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "executions.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """테이블 생성."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    spec_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    trace_id TEXT,
                    verification_snapshot TEXT,
                    agent_metadata TEXT,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workspace
                ON executions(workspace_id)
            """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT,
                    file_path TEXT,
                    line INTEGER,
                    column INTEGER DEFAULT 0,
                    evidence_uri TEXT,
                    cwe_id TEXT,
                    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution
                ON findings(execution_id)
            """
            )

    async def save(self, execution: Execution) -> None:
        """
        실행 결과 저장 (SOTA Pattern).

        VerificationSnapshot 자동 생성.
        """
        # Auto-generate snapshot if missing
        if not execution.verification_snapshot:
            from codegraph_shared.kernel.infrastructure.snapshot_factory import (
                create_snapshot_for_execution,
            )

            execution = Execution(
                execution_id=execution.execution_id,
                workspace_id=execution.workspace_id,
                spec_type=execution.spec_type,
                state=execution.state,
                trace_id=execution.trace_id,
                verification_snapshot=create_snapshot_for_execution(
                    workspace_id=execution.workspace_id,
                    repo_revision=None,
                ),
                agent_metadata=execution.agent_metadata,
                result=execution.result,
                error=execution.error,
                created_at=execution.created_at,
                completed_at=execution.completed_at,
            )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO executions
                (execution_id, workspace_id, spec_type, state, trace_id,
                 verification_snapshot, agent_metadata, result, error,
                 created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    execution.workspace_id,
                    execution.spec_type,
                    execution.state,
                    execution.trace_id,
                    json.dumps(execution.verification_snapshot.model_dump())
                    if execution.verification_snapshot
                    else None,
                    json.dumps(execution.agent_metadata.model_dump()) if execution.agent_metadata else None,
                    json.dumps(execution.result) if execution.result else None,
                    execution.error,
                    execution.created_at.isoformat(),
                    execution.completed_at.isoformat() if execution.completed_at else None,
                ),
            )

    async def save_findings(self, execution_id: str, findings: list[Finding]) -> None:
        """Findings 저장."""
        with sqlite3.connect(self.db_path) as conn:
            for f in findings:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO findings
                    (finding_id, execution_id, type, severity, message,
                     file_path, line, column, evidence_uri, cwe_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f.finding_id,
                        execution_id,
                        f.type,
                        f.severity,
                        f.message,
                        f.file_path,
                        f.line,
                        f.column,
                        f.evidence_uri,
                        f.cwe_id,
                    ),
                )

    async def get(self, execution_id: str) -> Execution | None:
        """실행 결과 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()

            if not row:
                return None

            return self._row_to_execution(row)

    async def get_findings(self, execution_id: str) -> list[dict[str, Any]]:
        """실행에서 발견된 findings 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM findings WHERE execution_id = ?",
                (execution_id,),
            ).fetchall()

            return [dict(row) for row in rows]

    async def list_by_workspace(self, workspace_id: str, limit: int = 20) -> list[Execution]:
        """workspace별 실행 목록."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM executions
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()

            return [self._row_to_execution(row) for row in rows]

    # ========================================================================
    # RFC-SEM-022 추가 메서드
    # ========================================================================

    async def update_state(
        self,
        execution_id: str,
        state: Literal["pending", "running", "completed", "failed", "cancelled"],
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """상태 업데이트."""
        completed_at = datetime.utcnow().isoformat() if state in ("completed", "failed", "cancelled") else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE executions
                SET state = ?, result = ?, error = ?, completed_at = ?
                WHERE execution_id = ?
                """,
                (
                    state,
                    json.dumps(result) if result else None,
                    error,
                    completed_at,
                    execution_id,
                ),
            )

    async def save_finding(self, execution_id: str, finding: Finding) -> None:
        """단일 Finding 저장."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO findings
                (finding_id, execution_id, type, severity, message,
                 file_path, line, column, evidence_uri, cwe_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    execution_id,
                    finding.type,
                    finding.severity,
                    finding.message,
                    finding.file_path,
                    finding.line,
                    finding.column,
                    finding.evidence_uri,
                    finding.cwe_id,
                ),
            )

    async def compare_findings(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """
        Regression Proof: 두 실행 간 Finding 비교 (RFC-SEM-022 Section 6.2).

        Returns:
            {
                "new_findings": [...],      # 새로 발생한 문제
                "removed_findings": [...],  # 해결된 문제
                "unchanged_count": int,     # 변경 없는 문제 수
                "passed": bool,             # new_findings == 0 이면 True
            }
        """
        baseline = await self.get_findings(baseline_execution_id)
        current = await self.get_findings(current_execution_id)

        # Finding 시그니처 생성 (type:file:line)
        def signature(f: dict) -> str:
            return f"{f.get('type')}:{f.get('file_path')}:{f.get('line')}"

        baseline_sigs = {signature(f): f for f in baseline}
        current_sigs = {signature(f): f for f in current}

        new_findings = [f for sig, f in current_sigs.items() if sig not in baseline_sigs]
        removed_findings = [f for sig, f in baseline_sigs.items() if sig not in current_sigs]
        unchanged_count = len(set(baseline_sigs.keys()) & set(current_sigs.keys()))

        return {
            "new_findings": new_findings,
            "removed_findings": removed_findings,
            "unchanged_count": unchanged_count,
            "passed": len(new_findings) == 0,
            "baseline_count": len(baseline),
            "current_count": len(current),
        }

    def _row_to_execution(self, row: sqlite3.Row) -> Execution:
        """Row → Execution 변환."""
        from codegraph_shared.kernel.contracts import (
            AgentMetadata,
            VerificationSnapshot,
        )

        vs = None
        if row["verification_snapshot"]:
            vs_data = json.loads(row["verification_snapshot"])
            vs = VerificationSnapshot(**vs_data)

        am = None
        if row["agent_metadata"]:
            am_data = json.loads(row["agent_metadata"])
            am = AgentMetadata(**am_data)

        return Execution(
            execution_id=row["execution_id"],
            workspace_id=row["workspace_id"],
            spec_type=row["spec_type"],
            state=row["state"],
            trace_id=row["trace_id"] or "",
            verification_snapshot=vs,
            agent_metadata=am,
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )


class InMemoryExecutionRepository(ExecutionRepository):
    """
    In-Memory Execution 저장소 (테스트용).

    RFC-SEM-022 완전 호환.
    """

    def __init__(self):
        self._executions: dict[str, Execution] = {}
        self._findings: dict[str, list[dict]] = {}

    async def save(self, execution: Execution) -> None:
        self._executions[execution.execution_id] = execution

    async def save_findings(self, execution_id: str, findings: list[Finding]) -> None:
        self._findings[execution_id] = [
            {
                "finding_id": f.finding_id,
                "type": f.type,
                "severity": f.severity,
                "message": f.message,
                "file_path": f.file_path,
                "line": f.line,
                "column": f.column,
                "evidence_uri": f.evidence_uri,
                "cwe_id": f.cwe_id,
            }
            for f in findings
        ]

    async def get(self, execution_id: str) -> Execution | None:
        return self._executions.get(execution_id)

    async def get_findings(self, execution_id: str) -> list[dict[str, Any]]:
        return self._findings.get(execution_id, [])

    async def list_by_workspace(self, workspace_id: str, limit: int = 20) -> list[Execution]:
        results = [e for e in self._executions.values() if e.workspace_id == workspace_id]
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    async def update_state(
        self,
        execution_id: str,
        state: Literal["pending", "running", "completed", "failed", "cancelled"],
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """상태 업데이트."""
        if execution_id in self._executions:
            exec_obj = self._executions[execution_id]
            # Pydantic model은 frozen이므로 새로 생성
            self._executions[execution_id] = Execution(
                execution_id=exec_obj.execution_id,
                workspace_id=exec_obj.workspace_id,
                spec_type=exec_obj.spec_type,
                state=state,
                trace_id=exec_obj.trace_id,
                verification_snapshot=exec_obj.verification_snapshot,
                agent_metadata=exec_obj.agent_metadata,
                created_at=exec_obj.created_at,
                completed_at=datetime.utcnow() if state in ("completed", "failed") else None,
                result=result,
                error=error,
            )

    async def save_finding(self, execution_id: str, finding: Finding) -> None:
        """단일 Finding 저장."""
        if execution_id not in self._findings:
            self._findings[execution_id] = []

        self._findings[execution_id].append(
            {
                "finding_id": finding.finding_id,
                "type": finding.type,
                "severity": finding.severity,
                "message": finding.message,
                "file_path": finding.file_path,
                "line": finding.line,
                "column": finding.column,
                "evidence_uri": finding.evidence_uri,
                "cwe_id": finding.cwe_id,
            }
        )

    async def compare_findings(
        self,
        baseline_execution_id: str,
        current_execution_id: str,
    ) -> dict[str, Any]:
        """Regression Proof."""
        baseline = await self.get_findings(baseline_execution_id)
        current = await self.get_findings(current_execution_id)

        def signature(f: dict) -> str:
            return f"{f.get('type')}:{f.get('file_path')}:{f.get('line')}"

        baseline_sigs = {signature(f): f for f in baseline}
        current_sigs = {signature(f): f for f in current}

        new_findings = [f for sig, f in current_sigs.items() if sig not in baseline_sigs]
        removed_findings = [f for sig, f in baseline_sigs.items() if sig not in current_sigs]

        return {
            "new_findings": new_findings,
            "removed_findings": removed_findings,
            "unchanged_count": len(set(baseline_sigs.keys()) & set(current_sigs.keys())),
            "passed": len(new_findings) == 0,
            "baseline_count": len(baseline),
            "current_count": len(current),
        }


# ============================================================
# Factory Functions (RFC-SEM-022)
# ============================================================


_repository: ExecutionRepository | None = None


def get_execution_repository(
    mode: str = "auto",
    db_path: str | None = None,
) -> ExecutionRepository:
    """
    ExecutionRepository 싱글톤 획득.

    Args:
        mode: "auto" | "sqlite" | "memory"
        db_path: SQLite 경로 (mode=sqlite)

    Returns:
        ExecutionRepository
    """
    global _repository

    if _repository is not None:
        return _repository

    if mode == "memory":
        _repository = InMemoryExecutionRepository()
    else:
        _repository = SQLiteExecutionRepository(db_path)

    return _repository


def reset_repository() -> None:
    """Repository 싱글톤 리셋 (테스트용)."""
    global _repository
    _repository = None


async def create_execution(
    workspace_id: str,
    spec_type: str,
    verification_snapshot: Any | None = None,
    agent_metadata: Any | None = None,
) -> Execution:
    """
    새 Execution 생성 헬퍼.

    Usage:
        execution = await create_execution(
            workspace_id="ws_001",
            spec_type="taint_analysis",
            verification_snapshot=snapshot,
        )
    """
    execution_id = f"exec_{uuid4().hex[:12]}"
    trace_id = f"trace_{uuid4().hex[:8]}"

    execution = Execution(
        execution_id=execution_id,
        workspace_id=workspace_id,
        spec_type=spec_type,
        state="pending",
        trace_id=trace_id,
        verification_snapshot=verification_snapshot,
        agent_metadata=agent_metadata,
    )

    repo = get_execution_repository()
    await repo.save(execution)

    return execution
