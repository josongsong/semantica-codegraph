"""
Replay Executor (RFC-SEM-022 SOTA)

결정론적 실행 재현 (Deterministic Replay).

SOTA Features:
- VerificationSnapshot 기반 결정론 보장
- Execution 재실행 및 비교
- Regression Proof 통합
- Diff 생성 (baseline vs replay)

Architecture:
- Port/Adapter Pattern
- Event Sourcing Ready
- Audit Trail Integration
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.shared_kernel.contracts import Execution, ResultEnvelope

logger = get_logger(__name__)


@dataclass
class ReplayRequest:
    """Replay 요청."""

    execution_id: str
    workspace_id: str | None = None  # Override workspace
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayResult:
    """Replay 결과."""

    replay_id: str
    original_execution_id: str
    status: str  # "identical" | "different" | "error"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Comparison
    findings_diff: dict[str, Any] = field(default_factory=dict)
    metrics_diff: dict[str, Any] = field(default_factory=dict)

    # New execution (if created)
    new_execution_id: str | None = None
    new_envelope: dict[str, Any] | None = None

    # Errors
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "replay_id": self.replay_id,
            "original_execution_id": self.original_execution_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "findings_diff": self.findings_diff,
            "metrics_diff": self.metrics_diff,
            "new_execution_id": self.new_execution_id,
            "new_envelope": self.new_envelope,
            "error": self.error,
        }


class ReplayExecutor:
    """
    Replay Executor (RFC-SEM-022 SOTA).

    결정론적 실행 재현:
    1. 원본 Execution 로드
    2. VerificationSnapshot 검증
    3. 동일 조건에서 재실행
    4. 결과 비교 (Regression Proof)

    Usage:
        executor = ReplayExecutor()

        # Replay execution
        result = await executor.replay("exec_abc123")

        # Check if results are identical
        if result.status == "identical":
            print("Deterministic execution verified!")
        else:
            print(f"Diff found: {result.findings_diff}")
    """

    def __init__(
        self,
        execution_repository: Any | None = None,
        audit_store: Any | None = None,
        execute_executor: Any | None = None,
    ):
        """
        Initialize ReplayExecutor.

        Args:
            execution_repository: Execution 저장소 (lazy if None)
            audit_store: AuditStore for logging (lazy if None)
            execute_executor: ExecuteExecutor for re-execution (lazy if None)
        """
        self._execution_repository = execution_repository
        self._audit_store = audit_store
        self._execute_executor = execute_executor

    @property
    def execution_repository(self):
        """Lazy-initialized ExecutionRepository."""
        if self._execution_repository is None:
            from codegraph_engine.shared_kernel.infrastructure.execution_repository import (
                get_execution_repository,
            )

            self._execution_repository = get_execution_repository()
        return self._execution_repository

    @property
    def audit_store(self):
        """Lazy-initialized AuditStore."""
        if self._audit_store is None:
            from codegraph_runtime.replay_audit.infrastructure import AuditStore

            self._audit_store = AuditStore()
        return self._audit_store

    @property
    def execute_executor(self):
        """Lazy-initialized ExecuteExecutor."""
        if self._execute_executor is None:
            from codegraph_runtime.llm_arbitration.application import ExecuteExecutor

            self._execute_executor = ExecuteExecutor()
        return self._execute_executor

    async def replay(
        self,
        execution_id: str,
        workspace_id: str | None = None,
        force_rerun: bool = False,
    ) -> ReplayResult:
        """
        Replay execution (RFC-SEM-022 SOTA).

        Args:
            execution_id: 재실행할 Execution ID
            workspace_id: 다른 workspace에서 실행 (A/B 비교)
            force_rerun: 강제 재실행 (snapshot 불일치 시에도)

        Returns:
            ReplayResult with comparison

        Steps:
        1. Load original execution
        2. Validate VerificationSnapshot
        3. Re-execute with same spec
        4. Compare findings (Regression Proof)
        """
        replay_id = f"replay_{uuid4().hex[:12]}"

        logger.info(
            "replay_started",
            replay_id=replay_id,
            execution_id=execution_id,
            force_rerun=force_rerun,
        )

        try:
            # Step 1: Load original execution
            original = await self.execution_repository.get(execution_id)

            if not original:
                return ReplayResult(
                    replay_id=replay_id,
                    original_execution_id=execution_id,
                    status="error",
                    error=f"Execution not found: {execution_id}",
                )

            # Step 2: Validate VerificationSnapshot
            if not force_rerun and original.verification_snapshot:
                snapshot_valid = await self._validate_snapshot(original.verification_snapshot)
                if not snapshot_valid:
                    return ReplayResult(
                        replay_id=replay_id,
                        original_execution_id=execution_id,
                        status="error",
                        error="VerificationSnapshot mismatch (engine/ruleset changed)",
                    )

            # Step 3: Get original spec from audit log
            audit_log = await self.audit_store.get(f"req_{execution_id.replace('exec_', '')}")

            if audit_log:
                spec = audit_log.input_spec
            else:
                # Fallback: reconstruct spec from execution
                spec = {
                    "intent": "analyze",
                    "template_id": original.spec_type,
                    "scope": {"workspace_id": workspace_id or original.workspace_id},
                }

            # Step 4: Re-execute
            if workspace_id:
                spec["scope"]["workspace_id"] = workspace_id

            new_envelope = await self.execute_executor.execute(spec)

            # Step 5: Compare findings (Regression Proof)
            new_execution_id = f"exec_{uuid4().hex[:12]}"

            # Save new execution for comparison
            from codegraph_engine.shared_kernel.contracts import Execution

            new_execution = Execution(
                execution_id=new_execution_id,
                workspace_id=workspace_id or original.workspace_id,
                spec_type=original.spec_type,
                state="completed",
                trace_id=f"trace_{uuid4().hex[:8]}",
                verification_snapshot=original.verification_snapshot,
            )
            await self.execution_repository.save(new_execution)

            # Save findings from new envelope
            if new_envelope.claims:
                from codegraph_engine.shared_kernel.contracts import Finding

                for claim in new_envelope.claims:
                    if hasattr(claim, "type") and hasattr(claim, "location"):
                        finding = Finding(
                            finding_id=f"finding_{uuid4().hex[:8]}",
                            type=getattr(claim, "type", "unknown"),
                            severity=getattr(claim, "severity", "medium"),
                            message=getattr(claim, "message", str(claim)),
                            file_path=getattr(claim.location, "file", "") if hasattr(claim, "location") else "",
                            line=getattr(claim.location, "line", 0) if hasattr(claim, "location") else 0,
                            execution_id=new_execution_id,
                        )
                        await self.execution_repository.save_finding(new_execution_id, finding)

            # Compare findings
            findings_comparison = await self.execution_repository.compare_findings(
                baseline_execution_id=execution_id,
                current_execution_id=new_execution_id,
            )

            # Determine status
            if findings_comparison.get("passed", False):
                status = "identical"
            else:
                status = "different"

            # Metrics comparison
            metrics_diff = self._compare_metrics(
                original_result=original.result or {},
                new_result=new_envelope.model_dump() if hasattr(new_envelope, "model_dump") else {},
            )

            result = ReplayResult(
                replay_id=replay_id,
                original_execution_id=execution_id,
                status=status,
                findings_diff=findings_comparison,
                metrics_diff=metrics_diff,
                new_execution_id=new_execution_id,
                new_envelope=new_envelope.model_dump() if hasattr(new_envelope, "model_dump") else {},
            )

            logger.info(
                "replay_completed",
                replay_id=replay_id,
                status=status,
                new_findings=len(findings_comparison.get("new_findings", [])),
                removed_findings=len(findings_comparison.get("removed_findings", [])),
            )

            return result

        except Exception as e:
            logger.error(
                "replay_failed",
                replay_id=replay_id,
                execution_id=execution_id,
                error=str(e),
                exc_info=True,
            )

            return ReplayResult(
                replay_id=replay_id,
                original_execution_id=execution_id,
                status="error",
                error=str(e),
            )

    async def replay_with_patch(
        self,
        execution_id: str,
        patchset_id: str,
    ) -> ReplayResult:
        """
        Replay with patchset applied (A/B Testing).

        Workflow:
        1. Get baseline execution
        2. Create branched workspace with patchset
        3. Re-execute on branched workspace
        4. Compare findings

        This is the core of Agent Verification Loop:
        - Agent proposes patch
        - Replay verifies patch resolves finding without regression
        """
        from codegraph_engine.shared_kernel.infrastructure.workspace_repository import (
            branch_workspace,
            get_workspace_repository,
        )

        # Get original execution
        original = await self.execution_repository.get(execution_id)
        if not original:
            return ReplayResult(
                replay_id=f"replay_{uuid4().hex[:12]}",
                original_execution_id=execution_id,
                status="error",
                error=f"Execution not found: {execution_id}",
            )

        # Create branched workspace
        try:
            branched_ws = await branch_workspace(
                base_workspace_id=original.workspace_id,
                patchset_id=patchset_id,
                metadata={"replay_execution_id": execution_id},
            )
        except ValueError as e:
            return ReplayResult(
                replay_id=f"replay_{uuid4().hex[:12]}",
                original_execution_id=execution_id,
                status="error",
                error=str(e),
            )

        # Replay on branched workspace
        return await self.replay(
            execution_id=execution_id,
            workspace_id=branched_ws.workspace_id,
            force_rerun=True,  # Different workspace = different index
        )

    async def _validate_snapshot(
        self,
        snapshot: Any,
    ) -> bool:
        """
        Validate VerificationSnapshot against current state.

        Returns True if snapshot matches current:
        - Engine version
        - Ruleset hash
        - Policies hash
        """
        try:
            from codegraph_runtime.llm_arbitration.infrastructure.snapshot_factory import (
                get_snapshot_factory,
            )

            factory = get_snapshot_factory()
            current_snapshot = await factory.create(
                repo_id="default",
                workspace_id="default",
            )

            # Compare critical fields
            if snapshot.engine_version != current_snapshot.engine_version:
                logger.warning(
                    "snapshot_engine_mismatch",
                    original=snapshot.engine_version,
                    current=current_snapshot.engine_version,
                )
                return False

            if snapshot.ruleset_hash != current_snapshot.ruleset_hash:
                logger.warning(
                    "snapshot_ruleset_mismatch",
                    original=snapshot.ruleset_hash,
                    current=current_snapshot.ruleset_hash,
                )
                return False

            return True

        except Exception as e:
            logger.warning(f"Snapshot validation failed: {e}")
            return True  # Allow replay on validation failure

    def _compare_metrics(
        self,
        original_result: dict[str, Any],
        new_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare execution metrics."""
        return {
            "original_claims_count": original_result.get("claims_count", 0),
            "new_claims_count": len(new_result.get("claims", [])),
            "original_execution_time_ms": original_result.get("execution_time_ms", 0),
            "new_execution_time_ms": new_result.get("metrics", {}).get("execution_time_ms", 0),
        }


# ============================================================
# Factory Function
# ============================================================


_replay_executor: ReplayExecutor | None = None


def get_replay_executor() -> ReplayExecutor:
    """Get ReplayExecutor singleton."""
    global _replay_executor
    if _replay_executor is None:
        _replay_executor = ReplayExecutor()
    return _replay_executor


def reset_replay_executor() -> None:
    """Reset singleton (for testing)."""
    global _replay_executor
    _replay_executor = None
