"""Security Result Handler (Strategy Pattern)"""

from typing import Any

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    ConfidenceBasis,
    Evidence,
    EvidenceKind,
    Location,
    ProofObligation,
    Provenance,
)


class SecurityResultHandler:
    """AnalysisResult (SecurityIssue[]) → Claims + Evidences"""

    def handle(self, result: Any, analyzer_name: str, request_id: str) -> tuple[list[Claim], list[Evidence]]:
        """Handle AnalysisResult"""
        claims = []
        evidences = []

        issues = getattr(result, "issues", [])

        for issue in issues:
            claim_id = f"{request_id}_claim_sec_{len(claims)}"

            severity_str = str(getattr(issue, "severity", "MEDIUM")).lower()

            claim = Claim(
                id=claim_id,
                type=getattr(issue, "issue_type", "security_issue"),
                severity=severity_str,
                confidence=getattr(issue, "confidence", 0.9),
                confidence_basis=ConfidenceBasis.PROVEN,
                proof_obligation=ProofObligation(
                    assumptions=["pattern matching correct"],
                    broken_if=[],
                    unknowns=[],
                ),
            )
            claims.append(claim)

            # Evidence
            evidence = Evidence(
                id=f"{request_id}_ev_{len(evidences)}",
                kind=EvidenceKind.CODE_SNIPPET,
                location=Location(
                    file_path=getattr(issue, "file_path", "unknown"),
                    start_line=getattr(issue, "line_start", 0),
                    end_line=getattr(issue, "line_end", 0),
                ),
                content={
                    "code_snippet": getattr(issue, "code_snippet", ""),
                    "message": getattr(issue, "message", ""),
                },
                provenance=Provenance(engine="SecurityAnalyzer"),
                claim_ids=[claim_id],
            )
            evidences.append(evidence)

        return claims, evidences
