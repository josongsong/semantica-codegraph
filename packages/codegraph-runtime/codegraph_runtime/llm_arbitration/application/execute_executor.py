"""
Execute Executor - Spec 실행 및 ResultEnvelope 생성 (RFC-SEM-022 SOTA)

SOTA Features:
- VerificationSnapshot 자동 생성
- Execution 추적 및 저장
- Deterministic Replay 지원
- Finding 자동 저장
"""

import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.di import CodeFoundationContainer
    from codegraph_runtime.llm_arbitration.infrastructure.snapshot_factory import SnapshotFactory
    from codegraph_engine.shared_kernel.infrastructure.execution_repository import ExecutionRepository

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import Execution, ResultEnvelope

logger = get_logger(__name__)


class ExecuteExecutor:
    """
    Spec Executor Factory (RFC-SEM-022 SOTA).

    SOLID: Single Responsibility = Routing + Execution Tracking.

    RFC-SEM-022 Features:
    - VerificationSnapshot 자동 생성 (결정론 보장)
    - Execution 저장 (Replay 지원)
    - Finding 자동 저장 (Regression Proof)

    책임:
    - Spec routing (intent → 적절한 executor)
    - Executor 생성 (Factory pattern)
    - Metrics 수집
    - Execution 추적 (RFC-SEM-022)

    NOT responsible for:
    - 실제 실행 (Delegated to AnalyzeExecutor, etc.)
    - IR loading (IRLoaderPort)
    - Envelope building (EnvelopeBuilder)

    SOLID:
    - S: Routing + Tracking
    - O: 새 intent 추가 시 executor만 추가
    - L: 교체 가능
    - I: 최소 인터페이스 (execute만)
    - D: Executor interface에 의존
    """

    def __init__(
        self,
        foundation_container: "CodeFoundationContainer | None" = None,
        snapshot_factory: "SnapshotFactory | None" = None,
        execution_repository: "ExecutionRepository | None" = None,
        enable_snapshot: bool = True,
        enable_execution_tracking: bool = True,
        enable_cache: bool = True,
    ):
        """
        Initialize factory.

        Args:
            foundation_container: CodeFoundationContainer (lazy if None)
            snapshot_factory: VerificationSnapshot factory (lazy if None)
            execution_repository: Execution 저장소 (lazy if None)
            enable_snapshot: VerificationSnapshot 생성 여부
            enable_execution_tracking: Execution 추적 여부
            enable_cache: 분석 결과 캐싱 여부
        """
        self._foundation_container = foundation_container
        self._snapshot_factory = snapshot_factory
        self._execution_repository = execution_repository
        self._enable_snapshot = enable_snapshot
        self._enable_execution_tracking = enable_execution_tracking
        self._enable_cache = enable_cache
        self._executors = {}  # Lazy-initialized executors
        self._cache = None  # Lazy-initialized

    @property
    def foundation_container(self):
        """Lazy-initialized CodeFoundationContainer"""
        if self._foundation_container is None:
            from codegraph_engine.code_foundation.di import code_foundation_container

            self._foundation_container = code_foundation_container
        return self._foundation_container

    @property
    def snapshot_factory(self):
        """Lazy-initialized SnapshotFactory (RFC-SEM-022)"""
        if self._snapshot_factory is None:
            from codegraph_runtime.llm_arbitration.infrastructure.snapshot_factory import (
                get_snapshot_factory,
            )

            self._snapshot_factory = get_snapshot_factory()
        return self._snapshot_factory

    @property
    def execution_repository(self):
        """Lazy-initialized ExecutionRepository (RFC-SEM-022)"""
        if self._execution_repository is None:
            from codegraph_engine.shared_kernel.infrastructure.execution_repository import (
                get_execution_repository,
            )

            self._execution_repository = get_execution_repository()
        return self._execution_repository

    @property
    def cache(self):
        """Lazy-initialized AnalysisCache (SOTA)"""
        if self._cache is None and self._enable_cache:
            from codegraph_shared.infra.analysis_cache import get_analysis_cache

            self._cache = get_analysis_cache()
        return self._cache

    def _get_executor(self, intent: str):
        """
        Get executor for intent (Factory pattern).

        Args:
            intent: "analyze" | "retrieve" | "edit"

        Returns:
            Executor instance
        """
        if intent not in self._executors:
            if intent == "analyze":
                from .executors import AnalyzeExecutor

                self._executors["analyze"] = AnalyzeExecutor(
                    foundation_container=self.foundation_container,
                )
            elif intent == "retrieve":
                from .executors import RetrieveExecutor

                self._executors["retrieve"] = RetrieveExecutor()
            elif intent == "edit":
                from .executors import EditExecutor

                self._executors["edit"] = EditExecutor()
            else:
                raise ValueError(f"Unknown intent: {intent}")

        return self._executors[intent]

    async def execute(self, spec: dict[str, Any]) -> ResultEnvelope:
        """
        Execute spec (Factory pattern: route to appropriate executor).

        RFC-SEM-022 SOTA:
        1. VerificationSnapshot 자동 생성
        2. Execution 생성 및 저장
        3. 실행 결과 저장
        4. Finding 저장 (Regression Proof 지원)

        Args:
            spec: RetrieveSpec | AnalyzeSpec | EditSpec

        Returns:
            ResultEnvelope (with execution_id in metadata)
        """
        request_id = f"req_{uuid4().hex[:12]}"
        execution_id = f"exec_{uuid4().hex[:12]}"
        trace_id = f"trace_{uuid4().hex[:8]}"
        start_time = time.perf_counter()
        intent = spec.get("intent")

        # Extract context from spec
        scope = spec.get("scope", {})
        repo_id = scope.get("repo_id", "default")
        workspace_id = scope.get("workspace_id", "default")

        # RFC-SEM-022: Create VerificationSnapshot
        verification_snapshot = None
        snapshot_hash = None
        if self._enable_snapshot:
            try:
                verification_snapshot = await self.snapshot_factory.create(
                    repo_id=repo_id,
                    workspace_id=workspace_id,
                )
                snapshot_hash = verification_snapshot.ruleset_hash
                logger.debug(
                    "verification_snapshot_created",
                    execution_id=execution_id,
                    engine_version=verification_snapshot.engine_version,
                    ruleset_hash=verification_snapshot.ruleset_hash[:20],
                )
            except Exception as e:
                logger.warning(f"Failed to create verification snapshot: {e}")

        # SOTA: Check cache first (for analyze intent only)
        if self._enable_cache and intent == "analyze" and self.cache:
            try:
                cached = await self.cache.get(spec, snapshot_hash)
                if cached:
                    logger.info(
                        "cache_hit",
                        execution_id=execution_id,
                        intent=intent,
                    )
                    # Reconstruct ResultEnvelope from cache
                    # Note: claims/evidences stored as dicts, reconstruct if needed
                    from codegraph_engine.shared_kernel.contracts import Claim, Evidence, Metrics

                    cached_claims = cached.get("claims", [])
                    cached_evidences = cached.get("evidences", [])
                    cached_metrics = cached.get("metrics")

                    # Reconstruct typed objects if stored as dicts (with fallback)
                    def safe_reconstruct(cls, data):
                        """Safely reconstruct pydantic model from dict."""
                        if not isinstance(data, dict):
                            return data
                        try:
                            return cls(**data)
                        except Exception:
                            return data  # Return raw dict if reconstruction fails

                    claims = [safe_reconstruct(Claim, c) for c in cached_claims] if cached_claims else []
                    evidences = [safe_reconstruct(Evidence, e) for e in cached_evidences] if cached_evidences else []
                    metrics = safe_reconstruct(Metrics, cached_metrics) if cached_metrics else None

                    return ResultEnvelope(
                        request_id=request_id,
                        summary=cached.get("summary", "Cached result"),
                        claims=claims,
                        evidences=evidences,
                        conclusion=cached.get("conclusion"),
                        metrics=metrics,
                        replay_ref=cached.get("replay_ref"),
                    )
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")

        # RFC-SEM-022: Create Execution record
        execution = None
        if self._enable_execution_tracking:
            try:
                execution = Execution(
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    spec_type=spec.get("template_id", intent or "unknown"),
                    state="running",
                    trace_id=trace_id,
                    verification_snapshot=verification_snapshot,
                )
                await self.execution_repository.save(execution)
                logger.debug("execution_created", execution_id=execution_id)
            except Exception as e:
                logger.warning(f"Failed to save execution: {e}")

        try:
            # Factory pattern: Get appropriate executor
            executor = self._get_executor(intent)

            # Delegate execution
            envelope = await executor.execute(spec, request_id)

            # Add metrics
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if envelope.metrics is None:
                from codegraph_engine.shared_kernel.contracts import Metrics

                envelope = ResultEnvelope(
                    request_id=envelope.request_id,
                    summary=envelope.summary,
                    claims=envelope.claims,
                    evidences=envelope.evidences,
                    conclusion=envelope.conclusion,
                    metrics=Metrics(
                        execution_time_ms=elapsed_ms,
                        claims_generated=len(envelope.claims),
                    ),
                    escalation=envelope.escalation,
                    replay_ref=envelope.replay_ref,
                )

            # RFC-SEM-022: Update Execution with result
            if self._enable_execution_tracking and execution:
                try:
                    await self.execution_repository.update_state(
                        execution_id=execution_id,
                        state="completed",
                        result={
                            "request_id": request_id,
                            "summary": envelope.summary,
                            "claims_count": len(envelope.claims),
                            "execution_time_ms": elapsed_ms,
                        },
                    )

                    # Save findings for Regression Proof
                    for claim in envelope.claims:
                        if hasattr(claim, "type") and hasattr(claim, "location"):
                            from codegraph_engine.shared_kernel.contracts import Finding

                            finding = Finding(
                                finding_id=f"finding_{uuid4().hex[:8]}",
                                type=claim.type,
                                severity=claim.severity if hasattr(claim, "severity") else "medium",
                                message=claim.message if hasattr(claim, "message") else str(claim),
                                file_path=claim.location.file if hasattr(claim.location, "file") else "",
                                line=claim.location.line if hasattr(claim.location, "line") else 0,
                                execution_id=execution_id,
                            )
                            await self.execution_repository.save_finding(execution_id, finding)

                except Exception as e:
                    logger.warning(f"Failed to update execution: {e}")

            # SOTA: Cache successful analysis results
            if self._enable_cache and intent == "analyze" and self.cache:
                try:
                    cache_data = {
                        "summary": envelope.summary,
                        "claims": [c.model_dump() if hasattr(c, "model_dump") else c for c in envelope.claims],
                        "evidences": [e.model_dump() if hasattr(e, "model_dump") else e for e in envelope.evidences],
                        "conclusion": envelope.conclusion,
                        "replay_ref": envelope.replay_ref,
                    }
                    await self.cache.set(spec, cache_data, snapshot_hash)
                    logger.debug("cache_set", execution_id=execution_id)
                except Exception as e:
                    logger.warning(f"Cache set failed: {e}")

            # Add execution_id to envelope metadata (for Replay)
            logger.info(
                "execution_completed",
                execution_id=execution_id,
                intent=intent,
                claims_count=len(envelope.claims),
                elapsed_ms=elapsed_ms,
            )

            return envelope

        except Exception as e:
            logger.error("execute_failed", intent=intent, error=str(e), exc_info=True)

            # RFC-SEM-022: Update Execution with error
            if self._enable_execution_tracking and execution:
                try:
                    await self.execution_repository.update_state(
                        execution_id=execution_id,
                        state="failed",
                        error=str(e),
                    )
                except Exception:
                    pass

            # Error envelope
            from codegraph_engine.shared_kernel.contracts import Escalation, Metrics

            return ResultEnvelope(
                request_id=request_id,
                summary=f"Execution failed: {str(e)}",
                claims=[],
                evidences=[],
                metrics=Metrics(
                    execution_time_ms=(time.perf_counter() - start_time) * 1000,
                    claims_generated=0,
                ),
                escalation=Escalation(
                    required=True,
                    reason="execution_error",
                    decision_needed=f"Failed to execute {intent} spec",
                    options=["retry", "skip", "escalate"],
                ),
                replay_ref=f"replay:{request_id.replace('req_', '')}",
            )
