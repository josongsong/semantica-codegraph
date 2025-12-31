"""RFC Orchestrator - Wraps existing orchestrators with ResultEnvelope output"""

import time
from typing import Any
from uuid import uuid4

from codegraph_runtime.llm_arbitration.application import ExecuteExecutor
from codegraph_runtime.llm_arbitration.infrastructure.arbitration_engine import (
    ArbitrationEngine,
)
from codegraph_runtime.llm_arbitration.infrastructure.envelope_builder import (
    EnvelopeBuilder,
)
from codegraph_runtime.replay_audit.domain.models import RequestAuditLog
from codegraph_runtime.replay_audit.infrastructure import AuditStore
from codegraph_engine.shared_kernel.contracts import ResultEnvelope


class RFCOrchestrator:
    """
    RFC-027 Orchestrator.

    기존 DeepReasoningOrchestrator / FastPathOrchestrator를 래핑하여
    ResultEnvelope 출력 제공.
    """

    def __init__(
        self,
        # deep_orchestrator: DeepReasoningOrchestrator | None = None,
        # fast_orchestrator: FastPathOrchestrator | None = None,
        envelope_builder: EnvelopeBuilder | None = None,
        arbitration_engine: ArbitrationEngine | None = None,
        audit_store: AuditStore | None = None,
    ):
        # self.deep = deep_orchestrator
        # self.fast = fast_orchestrator
        self.envelope_builder = envelope_builder or EnvelopeBuilder()
        self.arbitration = arbitration_engine or ArbitrationEngine()
        self.audit = audit_store or AuditStore()

    async def execute(self, spec: dict[str, Any]) -> ResultEnvelope:
        """
        RFC Spec 실행 → ResultEnvelope 반환.

        Args:
            spec: RetrieveSpec | AnalyzeSpec | EditSpec

        Returns:
            ResultEnvelope (arbitrated)
        """
        request_id = str(uuid4())
        start_time = time.perf_counter()

        intent = spec.get("intent")

        # ExecuteExecutor 사용
        executor = ExecuteExecutor()
        result = await executor.execute(spec)

        # Arbitration
        arbitrated_claims = self.arbitration.arbitrate(result.claims)
        result.claims = arbitrated_claims

        # Audit log
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        await self.audit.save(
            RequestAuditLog(
                request_id=request_id,
                input_spec=spec,
                resolved_spec=spec,  # TODO: resolve
                engine_versions=self._get_engine_versions(),
                index_digests={},  # TODO: get digests
                llm_decisions=[],
                tool_trace=[],
                outputs={},
                duration_ms=elapsed_ms,
            )
        )

        result.request_id = request_id
        result.replay_ref = f"replay:{request_id}"

        return result

    def _get_engine_versions(self) -> dict[str, str]:
        """엔진 버전 정보 (Snapshot)"""
        return {
            "sccp": "1.0.0",
            "taint": "1.0.0",
            "reasoning": "1.0.0",
            "deep_reasoning": "1.0.0",
        }
