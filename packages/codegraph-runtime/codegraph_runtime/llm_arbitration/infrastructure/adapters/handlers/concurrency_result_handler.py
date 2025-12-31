"""Concurrency Result Handler (RFC-028 Integration)"""

from typing import Any

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    ConfidenceBasis,
    Evidence,
    ProofObligation,
)
from codegraph_engine.shared_kernel.contracts.mappings import VERDICT_TO_CONFIDENCE_BASIS


class ConcurrencyResultHandler:
    """
    RaceCondition[] → Claims + Evidences (RFC-028 Contract).

    SOLID:
    - S: RaceCondition 처리만
    - O: 확장 가능
    - L: 교체 가능
    - I: 최소 인터페이스
    - D: ConfidenceBasis 매핑에 의존
    """

    def handle(self, result: list[Any], analyzer_name: str, request_id: str) -> tuple[list[Claim], list[Evidence]]:
        """
        RaceCondition[] → Claims + Evidences.

        Args:
            result: list[RaceCondition] from AsyncRaceDetector
            analyzer_name: "race_detector"
            request_id: Request ID

        Returns:
            (claims, evidences)
        """
        claims = []
        evidences = []

        # result is list[RaceCondition]
        for race in result:
            claim_id = f"{request_id}_claim_race_{len(claims)}"

            # Verdict → ConfidenceBasis
            verdict = getattr(race, "verdict", "likely")
            confidence_basis = VERDICT_TO_CONFIDENCE_BASIS.get(verdict, ConfidenceBasis.INFERRED)

            # Severity mapping
            severity_str = str(getattr(race, "severity", "MEDIUM")).lower()

            claim = Claim(
                id=claim_id,
                type="race_condition",
                severity=severity_str,
                confidence=getattr(race, "confidence", 0.8),
                confidence_basis=confidence_basis,
                proof_obligation=ProofObligation(
                    assumptions=["alias analysis correct", "await points detected"],
                    broken_if=["lock protection exists"],
                    unknowns=["runtime interleaving"],
                ),
            )
            claims.append(claim)

            # Evidence (ConcurrencyEvidenceBuilder 사용)
            evidence = getattr(race, "evidence", None)
            if evidence:
                evidence.claim_ids = [claim_id]
                evidences.append(evidence)

        return claims, evidences
