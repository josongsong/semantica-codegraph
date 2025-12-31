"""ResultEnvelope Builder - Combines multiple analysis results"""

from typing import Any
from uuid import uuid4

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    Conclusion,
    Evidence,
    Metrics,
    ResultEnvelope,
)

from .adapters.deep_reasoning_adapter import DeepReasoningAdapter
from .adapters.reasoning_adapter import ReasoningAdapter
from .adapters.risk_adapter import RiskAdapter
from .adapters.taint_adapter import TaintAdapter


class EnvelopeBuilder:
    """
    ResultEnvelope 빌더 - 여러 분석 결과를 조합.

    Usage:
        builder = EnvelopeBuilder(request_id="req_123")
        builder.from_taint_result(taint_result)
        builder.from_reasoning_result(reasoning_result)
        envelope = builder.build()
    """

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id or str(uuid4())

        # Accumulator
        self.claims: list[Claim] = []
        self.evidences: list[Evidence] = []
        self.conclusions: list[Conclusion] = []
        self.metrics_list: list[Metrics] = []
        self.legacy_results: dict[str, Any] = {}

        # Adapters
        self.taint_adapter = TaintAdapter()
        self.reasoning_adapter = ReasoningAdapter()
        self.risk_adapter = RiskAdapter()
        self.deep_reasoning_adapter = DeepReasoningAdapter()

    def new(self, request_id: str | None = None) -> "EnvelopeBuilder":
        """새로운 빌더 인스턴스 생성"""
        return EnvelopeBuilder(request_id=request_id)

    def from_taint_result(self, taint_result: dict[str, Any]) -> "EnvelopeBuilder":
        """TaintAnalyzer 결과 추가"""
        envelope = self.taint_adapter.to_envelope(taint_result, self.request_id)

        self.claims.extend(envelope.claims)
        self.evidences.extend(envelope.evidences)
        self.legacy_results["taint"] = taint_result

        return self

    def from_reasoning_result(self, reasoning_result: Any) -> "EnvelopeBuilder":
        """ReasoningResult 추가 (Conclusion으로)"""
        conclusion = self.reasoning_adapter.to_conclusion(reasoning_result)
        self.conclusions.append(conclusion)
        self.legacy_results["reasoning"] = reasoning_result

        return self

    def from_risk_report(self, risk_report: Any) -> "EnvelopeBuilder":
        """RiskReport 추가 (Claim으로)"""
        claim = self.risk_adapter.to_claim(risk_report)
        self.claims.append(claim)
        self.legacy_results["risk"] = risk_report

        return self

    def from_deep_reasoning_result(
        self,
        deep_result: Any,
        strategy: str = "auto",
    ) -> "EnvelopeBuilder":
        """DeepReasoningResult 추가"""
        envelope = self.deep_reasoning_adapter.to_envelope(deep_result, strategy, self.request_id)

        self.claims.extend(envelope.claims)
        self.evidences.extend(envelope.evidences)
        if envelope.conclusion:
            self.conclusions.append(envelope.conclusion)
        if envelope.metrics:
            self.metrics_list.append(envelope.metrics)
        self.legacy_results["deep_reasoning"] = deep_result

        return self

    def add_claim(self, claim: Claim) -> "EnvelopeBuilder":
        """Claim 직접 추가"""
        self.claims.append(claim)
        return self

    def add_evidence(self, evidence: Evidence) -> "EnvelopeBuilder":
        """Evidence 직접 추가"""
        self.evidences.append(evidence)
        return self

    def add_conclusion(self, conclusion: Conclusion) -> "EnvelopeBuilder":
        """Conclusion 직접 추가"""
        self.conclusions.append(conclusion)
        return self

    def build(self) -> ResultEnvelope:
        """
        최종 ResultEnvelope 생성.

        Returns:
            ResultEnvelope
        """
        # Conclusion 병합 (여러 개면 첫 번째 사용)
        final_conclusion = self.conclusions[0] if self.conclusions else None

        # Metrics 병합 (여러 개면 합산, 없으면 기본값)
        final_metrics = (
            self._merge_metrics()
            if self.metrics_list
            else Metrics(
                execution_time_ms=0.1,
                claims_generated=len(self.claims),
                claims_suppressed=sum(1 for c in self.claims if c.suppressed),
            )
        )

        # Summary 생성
        summary = self._generate_summary()

        # replay_ref: replay:<request_id_suffix> (req_ 제거)
        request_id_suffix = (
            self.request_id.replace("req_", "") if self.request_id.startswith("req_") else self.request_id
        )
        replay_ref = f"replay:{request_id_suffix}"

        return ResultEnvelope(
            request_id=self.request_id,
            summary=summary,
            claims=self.claims,
            evidences=self.evidences,
            conclusion=final_conclusion,
            metrics=final_metrics,
            escalation=None,
            replay_ref=replay_ref,
            legacy_result=self.legacy_results if self.legacy_results else None,
        )

    def _generate_summary(self) -> str:
        """Summary 자동 생성"""
        if not self.claims:
            return "No findings"

        claim_types = {}
        for claim in self.claims:
            claim_types[claim.type] = claim_types.get(claim.type, 0) + 1

        parts = [f"{count} {ctype}" for ctype, count in claim_types.items()]
        return f"Found: {', '.join(parts)}"

    def _merge_metrics(self) -> Metrics | None:
        """여러 Metrics 병합"""
        if not self.metrics_list:
            return None

        total_time = sum(m.execution_time_ms for m in self.metrics_list)
        total_paths = sum(m.paths_analyzed for m in self.metrics_list)
        total_claims = sum(m.claims_generated for m in self.metrics_list)
        total_suppressed = sum(m.claims_suppressed for m in self.metrics_list)

        return Metrics(
            execution_time_ms=total_time,
            paths_analyzed=total_paths,
            claims_generated=total_claims,
            claims_suppressed=total_suppressed,
        )
