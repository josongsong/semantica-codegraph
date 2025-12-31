"""Taint Result Handler (Strategy Pattern)"""

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


class TaintResultHandler:
    """TaintAnalysisResult → Claims + Evidences"""

    def handle(self, result: Any, analyzer_name: str, request_id: str) -> tuple[list[Claim], list[Evidence]]:
        """Handle TaintAnalysisResult"""
        claims = []
        evidences = []

        vulnerabilities = getattr(result, "vulnerabilities", [])

        for vuln in vulnerabilities:
            claim_id = f"{request_id}_claim_taint_{len(claims)}"

            claim = Claim(
                id=claim_id,
                type=getattr(vuln, "type", "taint_vulnerability"),
                severity=getattr(vuln, "severity", "high"),
                confidence=0.95,
                confidence_basis=ConfidenceBasis.PROVEN,
                proof_obligation=ProofObligation(
                    assumptions=["data flow graph is sound"],
                    broken_if=["sanitizer on path"],
                    unknowns=[],
                ),
            )
            claims.append(claim)

            # Evidence
            evidence = Evidence(
                id=f"{request_id}_ev_{len(evidences)}",
                kind=EvidenceKind.DATA_FLOW_PATH,
                location=Location(
                    file_path=getattr(vuln, "file_path", "unknown"),
                    start_line=getattr(vuln, "line", 0),
                    end_line=getattr(vuln, "line", 0),
                ),
                content={
                    "vulnerability_type": claim.type,
                    "description": getattr(vuln, "description", ""),
                },
                provenance=Provenance(engine="TaintAnalyzer", template=claim.type),
                claim_ids=[claim_id],
            )
            evidences.append(evidence)

        return claims, evidences
