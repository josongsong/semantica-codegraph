"""DeepReasoningResult → RFC-027 ResultEnvelope Adapter"""

from typing import TYPE_CHECKING
from uuid import uuid4

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    Conclusion,
    ConfidenceBasis,
    Evidence,
    EvidenceKind,
    Location,
    Metrics,
    ProofObligation,
    Provenance,
    ResultEnvelope,
)
from codegraph_engine.shared_kernel.contracts.mappings import STRATEGY_TO_CONFIDENCE_BASIS

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.shared.reasoning.deep.deep_models import DeepReasoningResult


class DeepReasoningAdapter:
    """
    DeepReasoningResult → ResultEnvelope 변환.

    Deep Reasoning 전략별로 confidence_basis 매핑:
    - o1 (verified): PROVEN
    - debate/beam/tot: INFERRED
    - alphacode: HEURISTIC
    - auto: UNKNOWN
    """

    def to_envelope(
        self,
        result: "DeepReasoningResult",
        strategy: str = "auto",
        request_id: str | None = None,
    ) -> ResultEnvelope:
        """
        DeepReasoningResult를 ResultEnvelope로 변환.

        Args:
            result: DeepReasoningOrchestrator 실행 결과
            strategy: 사용된 추론 전략 (o1, debate, beam, tot, alphacode, auto)
            request_id: 요청 ID

        Returns:
            ResultEnvelope
        """
        request_id = request_id or str(uuid4())

        # Verification 통과 여부로 confidence_basis 결정
        all_verified = all(v.is_valid for v in result.verification_results)

        # o1 전략 + 검증 통과 = PROVEN
        if strategy == "o1" and all_verified:
            confidence_basis = ConfidenceBasis.PROVEN
        else:
            confidence_basis = STRATEGY_TO_CONFIDENCE_BASIS.get(strategy, ConfidenceBasis.UNKNOWN)

        claim_id = f"{request_id}_claim_1"

        # Main claim
        claim = Claim(
            id=claim_id,
            type="code_generation",
            severity="info",
            confidence=result.final_confidence,
            confidence_basis=confidence_basis,
            proof_obligation=ProofObligation(
                assumptions=[f"strategy: {strategy}"],
                broken_if=["test failure", "lint error", "compilation error"],
                unknowns=["runtime behavior", "edge cases"],
            ),
        )

        # Reasoning steps → Evidence
        evidences: list[Evidence] = []
        for step in result.reasoning_steps:
            evidence = Evidence(
                id=f"{request_id}_ev_{len(evidences) + 1}",
                kind=EvidenceKind.CODE_SNIPPET,
                location=Location(
                    file_path="<generated>",
                    start_line=0,
                    end_line=0,
                ),
                content={
                    "step_number": step.step_number,
                    "question": step.question,
                    "answer": step.answer,
                    "confidence": step.confidence,
                },
                provenance=Provenance(
                    engine="DeepReasoning",
                    template=strategy,
                ),
                claim_ids=[claim_id],
            )
            evidences.append(evidence)

        # Conclusion
        conclusion = Conclusion(
            reasoning_summary=result.get_reasoning_trace()[:500],  # 첫 500자
            coverage=result.final_confidence,
            counterevidence=[
                f"Verification failed: {v.error_message}" for v in result.verification_results if not v.is_valid
            ],
            recommendation="Review generated code and verify edge cases",
        )

        # Metrics
        metrics = Metrics(
            execution_time_ms=result.reasoning_time * 1000,  # sec → ms
            paths_analyzed=result.total_steps,
            claims_generated=1,
            claims_suppressed=0,
            metadata={
                "strategy": strategy,
                "total_depth": result.total_depth,
                "total_thoughts": result.total_thoughts,
                "total_verifications": result.total_verifications,
            },
        )

        return ResultEnvelope(
            request_id=request_id,
            summary=result.final_answer[:200],  # 첫 200자
            claims=[claim],
            evidences=evidences,
            conclusion=conclusion,
            metrics=metrics,
            escalation=None,
            replay_ref=f"replay:{request_id}",
            legacy_result={
                "final_answer": result.final_answer,
                "final_code": result.final_code,
            },
        )
