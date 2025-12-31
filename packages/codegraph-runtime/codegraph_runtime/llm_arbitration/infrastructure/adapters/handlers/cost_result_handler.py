"""Cost Result Handler (Strategy Pattern - Single Responsibility)"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import Claim, ConfidenceBasis, Evidence, ProofObligation
from codegraph_engine.shared_kernel.contracts.mappings import (
    COMPLEXITY_TO_SEVERITY,
    VERDICT_TO_CONFIDENCE_BASIS,
)

logger = get_logger(__name__)


class CostResultHandler:
    """
    CostResult → Claim + Evidence (RFC-028 Contract).

    SOLID:
    - S: CostResult 처리만
    - O: 확장 가능
    - L: 교체 가능
    - I: 최소 인터페이스
    - D: ConfidenceBasis 매핑에 의존
    """

    def handle(self, result: Any, analyzer_name: str, request_id: str) -> tuple[list[Claim], list[Evidence]]:
        """
        CostResult → Claim + Evidence.

        RFC-028 Contract:
        - result.verdict: "proven"/"likely"/"heuristic"
        - result.evidence: Evidence
        - result.confidence: float

        Args:
            result: CostResult
            analyzer_name: Analyzer name
            request_id: Request ID

        Returns:
            (claims, evidences)
        """
        claim_id = f"{request_id}_claim_cost"

        # Verdict → ConfidenceBasis
        verdict = getattr(result, "verdict", "heuristic")
        confidence_basis = VERDICT_TO_CONFIDENCE_BASIS.get(verdict, ConfidenceBasis.HEURISTIC)

        # Complexity → Severity
        complexity_str = str(getattr(result, "complexity", "O(n)"))
        severity = COMPLEXITY_TO_SEVERITY.get(complexity_str, "medium")

        claim = Claim(
            id=claim_id,
            type="performance_issue",
            severity=severity,
            confidence=getattr(result, "confidence", 0.9),
            confidence_basis=confidence_basis,
            proof_obligation=ProofObligation(
                assumptions=["loop bound inference correct"],
                broken_if=[],
                unknowns=result.metadata.get("unknowns", []) if hasattr(result, "metadata") else [],
            ),
        )

        # Evidence (RFC-028 Contract: result.evidence)
        evidence = getattr(result, "evidence", None)
        if evidence:
            evidence.claim_ids = [claim_id]
            return [claim], [evidence]

        return [claim], []
