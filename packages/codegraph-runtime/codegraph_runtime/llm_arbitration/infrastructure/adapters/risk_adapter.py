"""RiskReport → RFC-027 Claim Adapter"""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codegraph_engine.shared_kernel.contracts import (
    Claim,
    ConfidenceBasis,
    ProofObligation,
)

if TYPE_CHECKING:
    from codegraph_engine.reasoning_engine.domain.speculative_models import RiskReport


class RiskAdapter:
    """
    RiskReport → Claim 변환.

    RiskReport는 speculative execution의 위험도 평가 결과.
    """

    def to_claim(self, report: "RiskReport", request_id: str | None = None) -> Claim:
        """
        RiskReport를 Claim으로 변환.

        Args:
            report: RiskAnalyzer.analyze_risk() 결과
            request_id: Request ID (없으면 UUID 생성, prefix 추가)

        Returns:
            Claim

        Raises:
            TypeError: If report is not RiskReport
        """
        # Type validation
        if not hasattr(report, "risk_level"):
            raise TypeError(f"Expected RiskReport, got {type(report).__name__}")

        if request_id:
            claim_id = f"{request_id}_risk_claim_{uuid4().hex[:8]}"
        else:
            claim_id = f"risk_claim_{uuid4().hex[:8]}"

        # RiskLevel → severity 매핑
        severity = self._risk_level_to_severity(report.risk_level)

        # risk_score를 confidence로 변환 (역산: 1.0 - risk_score)
        confidence = max(0.0, 1.0 - report.risk_score)

        # Breaking change면 type은 "breaking_change"
        claim_type = "breaking_change" if report.is_breaking() else "risk_assessment"

        return Claim(
            id=claim_id,
            type=claim_type,
            severity=severity,
            confidence=confidence,
            confidence_basis=ConfidenceBasis.PROVEN,  # Static analysis (call graph)
            proof_obligation=ProofObligation(
                assumptions=["call graph is complete"],
                broken_if=report.breaking_changes,
                unknowns=[],
            ),
        )

    def _risk_level_to_severity(self, risk_level: Any) -> str:
        """RiskLevel → severity string"""
        # Handle enum value extraction
        if hasattr(risk_level, "value"):
            risk_str = risk_level.value.lower()
        else:
            risk_str = str(risk_level).lower()
            # Extract value from "RiskLevel.SAFE" format
            if "." in risk_str:
                risk_str = risk_str.split(".")[-1]

        mapping = {
            "safe": "info",
            "low": "low",
            "medium": "medium",
            "high": "high",
            "breaking": "critical",
        }

        return mapping.get(risk_str, "medium")
