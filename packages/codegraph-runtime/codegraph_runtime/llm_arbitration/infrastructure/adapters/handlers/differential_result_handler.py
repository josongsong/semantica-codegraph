"""Differential Result Handler (RFC-028 Integration)"""

from typing import Any

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    ConfidenceBasis,
    Evidence,
    ProofObligation,
)


class DifferentialResultHandler:
    """
    DiffResult → Claims + Evidences (RFC-028 Contract).

    SOLID:
    - S: DiffResult 처리만
    - O: 확장 가능
    - L: 교체 가능
    - I: 최소 인터페이스
    - D: ConfidenceBasis 매핑에 의존
    """

    def handle(self, result: Any, analyzer_name: str, request_id: str) -> tuple[list[Claim], list[Evidence]]:
        """
        DiffResult → Claims + Evidences.

        Args:
            result: DiffResult from DifferentialAnalyzer
            analyzer_name: "differential_analyzer"
            request_id: Request ID

        Returns:
            (claims, evidences)
        """
        claims = []
        evidences = []

        # Taint diffs (sanitizer removal)
        taint_diffs = getattr(result, "taint_diffs", [])
        for td in taint_diffs:
            claim_id = f"{request_id}_claim_taint_diff_{len(claims)}"

            claim = Claim(
                id=claim_id,
                type="sanitizer_removal",
                severity="critical",  # Sanitizer removal = critical!
                confidence=0.95,
                confidence_basis=ConfidenceBasis.PROVEN,  # Taint diff = proven
                proof_obligation=ProofObligation(
                    assumptions=["taint analysis correct"],
                    broken_if=[],
                    unknowns=[],
                ),
            )
            claims.append(claim)

            # Evidence
            evidence = getattr(td, "evidence", None)
            if evidence:
                evidence.claim_ids = [claim_id]
                evidences.append(evidence)

        # Cost diffs (performance regression)
        cost_diffs = getattr(result, "cost_diffs", [])
        for cd in cost_diffs:
            claim_id = f"{request_id}_claim_cost_diff_{len(claims)}"

            # Regression severity
            before_complexity = getattr(cd, "before_complexity", "O(n)")
            after_complexity = getattr(cd, "after_complexity", "O(n²)")

            # O(n) → O(n²) = high, O(n) → O(n³) = critical
            severity = "critical" if "³" in str(after_complexity) or "^" in str(after_complexity) else "high"

            claim = Claim(
                id=claim_id,
                type="performance_regression",
                severity=severity,
                confidence=0.9,
                confidence_basis=ConfidenceBasis.PROVEN,  # Cost analysis = proven
                proof_obligation=ProofObligation(
                    assumptions=["loop bound inference correct"],
                    broken_if=[],
                    unknowns=[],
                ),
            )
            claims.append(claim)

            # Evidence
            evidence = getattr(cd, "evidence", None)
            if evidence:
                evidence.claim_ids = [claim_id]
                evidences.append(evidence)

        # Breaking changes
        breaking_changes = getattr(result, "breaking_changes", [])
        for bc in breaking_changes:
            claim_id = f"{request_id}_claim_breaking_{len(claims)}"

            claim = Claim(
                id=claim_id,
                type="breaking_change",
                severity="critical",
                confidence=0.95,
                confidence_basis=ConfidenceBasis.PROVEN,
                proof_obligation=ProofObligation(
                    assumptions=["API signature analysis correct"],
                    broken_if=[],
                    unknowns=[],
                ),
            )
            claims.append(claim)

            # Evidence
            evidence = getattr(bc, "evidence", None)
            if evidence:
                evidence.claim_ids = [claim_id]
                evidences.append(evidence)

        return claims, evidences
