"""
Claim Models (RFC-027)

Claim은 분석 결과의 주장입니다.
반드시 Evidence로 뒷받침되어야 합니다.

Architecture:
- Domain Layer (Pure model)
- Immutable (frozen=True)
- Type-safe (Pydantic)

RFC-027 Section 6.2: Claim
RFC-028: verdict 매핑 (proven/likely/heuristic)
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConfidenceBasis(str, Enum):
    """
    Confidence 근거 (RFC-027 Section 6.2)

    Arbitration 우선순위:
    1. PROVEN (highest) — Deterministic static proof (SCCP+, Type inference)
    2. INFERRED — Path existence proof (Taint path, Call chain)
    3. HEURISTIC — Pattern-based, ML-based
    4. UNKNOWN (lowest) — Vector similarity hypothesis

    RFC-028 verdict 매핑:
    - verdict="proven" → PROVEN
    - verdict="likely" → INFERRED
    - verdict="heuristic" → HEURISTIC
    """

    PROVEN = "proven"  # Static proof (SCCP, Type inference)
    INFERRED = "inferred"  # Path existence (Taint, Call chain)
    HEURISTIC = "heuristic"  # Pattern, ML
    UNKNOWN = "unknown"  # Hypothesis only


class ProofObligation(BaseModel):
    """
    증명 의무 (RFC-027 Section 6.2)

    Claim이 성립하기 위해 필요한 조건들.

    Fields:
    - assumptions: 가정 (이것들이 참이면 Claim도 참)
    - broken_if: 무효화 조건 (이것들이 참이면 Claim 무효)
    - unknowns: 확인 안 된 것들

    Example:
        ProofObligation(
            assumptions=["call graph is complete", "no dynamic dispatch"],
            broken_if=["sanitizer exists on path"],
            unknowns=["external library behavior"]
        )
    """

    assumptions: list[str] = Field(default_factory=list, description="Assumed conditions for claim")
    broken_if: list[str] = Field(default_factory=list, description="Conditions that invalidate claim")
    unknowns: list[str] = Field(default_factory=list, description="Unverified aspects")

    @field_validator("assumptions", "broken_if", "unknowns")
    @classmethod
    def validate_string_lists(cls, v: list[str]) -> list[str]:
        """Validate all items are non-empty strings"""
        for item in v:
            if not item or not item.strip():
                raise ValueError(f"Empty string in list: {v}")
        return v

    model_config = {"frozen": True}


class Claim(BaseModel):
    """
    Claim (RFC-027 Section 6.2)

    분석 결과의 주장. 반드시 Evidence로 뒷받침됨.

    핵심 설계:
    - confidence_basis: 어떻게 얻어진 결론인가? (PROVEN/INFERRED/HEURISTIC)
    - confidence: 얼마나 확신하는가? (0.0-1.0)
    - proof_obligation: 무엇이 참이어야 이 주장이 성립하는가?
    - suppressed: Arbitration engine이 억제했는가?

    Validation:
    - id: UUID format
    - type: non-empty (e.g., "sql_injection", "null_deref", "performance_issue")
    - severity: critical/high/medium/low/info
    - confidence: 0.0-1.0
    - suppressed와 suppression_reason 일관성

    Examples:
        # Taint analysis claim (PROVEN)
        Claim(
            id="claim_001",
            type="sql_injection",
            severity="critical",
            confidence=0.95,
            confidence_basis=ConfidenceBasis.PROVEN,
            proof_obligation=ProofObligation(
                assumptions=["taint propagates through data flow"],
                broken_if=["sanitizer exists on path"],
                unknowns=[]
            )
        )

        # Cost analysis claim (HEURISTIC)
        Claim(
            id="claim_002",
            type="performance_issue",
            severity="high",
            confidence=0.2,
            confidence_basis=ConfidenceBasis.HEURISTIC,
            proof_obligation=ProofObligation(
                assumptions=[],
                broken_if=[],
                unknowns=["loop bound unknown, assumed O(n²)"]
            )
        )
    """

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$", description="Claim ID (UUID)")
    type: str = Field(..., min_length=1, description="Claim type (e.g., sql_injection, null_deref)")
    severity: str = Field(..., pattern=r"^(critical|high|medium|low|info)$", description="Severity level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    confidence_basis: ConfidenceBasis = Field(..., description="How was this confidence obtained?")
    proof_obligation: ProofObligation = Field(..., description="Proof obligations")

    suppressed: bool = Field(default=False, description="Suppressed by arbitration engine?")
    suppression_reason: str | None = Field(None, description="Why suppressed?")

    # Optional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("suppression_reason")
    @classmethod
    def validate_suppression_consistency(cls, v: str | None, info) -> str | None:
        """
        Validate suppression_reason consistency with suppressed flag

        Rule:
        - suppressed=True → suppression_reason required
        - suppressed=False → suppression_reason must be None
        """
        suppressed = info.data.get("suppressed", False)

        if suppressed and not v:
            raise ValueError("suppression_reason is required when suppressed=True")

        if not suppressed and v:
            raise ValueError("suppression_reason must be None when suppressed=False")

        return v

    model_config = {"frozen": True}

    def is_actionable(self) -> bool:
        """
        Is this claim actionable? (not suppressed)

        Returns:
            True if claim should be shown to user
        """
        return not self.suppressed

    def is_high_confidence(self) -> bool:
        """
        High confidence claim?

        Returns:
            True if confidence >= 0.8
        """
        return self.confidence >= 0.8

    def is_proven(self) -> bool:
        """
        Static proof?

        Returns:
            True if confidence_basis is PROVEN
        """
        return self.confidence_basis == ConfidenceBasis.PROVEN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization"""
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis.value,
            "proof_obligation": {
                "assumptions": self.proof_obligation.assumptions,
                "broken_if": self.proof_obligation.broken_if,
                "unknowns": self.proof_obligation.unknowns,
            },
            "suppressed": self.suppressed,
            "suppression_reason": self.suppression_reason,
            "metadata": self.metadata,
        }


# ============================================================
# Claim Builders (Type-safe helpers)
# ============================================================


def create_proven_claim(
    claim_id: str, claim_type: str, severity: str, confidence: float, assumptions: list[str], broken_if: list[str]
) -> Claim:
    """
    Create PROVEN claim (static proof)

    Args:
        claim_id: Claim ID
        claim_type: Type (e.g., "sql_injection")
        severity: Severity level
        confidence: Confidence (typically 0.9-1.0 for proven)
        assumptions: List of assumptions
        broken_if: List of invalidation conditions

    Returns:
        Claim with confidence_basis=PROVEN

    Raises:
        ValueError: If confidence < 0.8 (proven should be high confidence)
    """
    if confidence < 0.8:
        raise ValueError(f"PROVEN claims should have confidence >= 0.8, got {confidence}")

    return Claim(
        id=claim_id,
        type=claim_type,
        severity=severity,
        confidence=confidence,
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(assumptions=assumptions, broken_if=broken_if, unknowns=[]),
    )


def create_heuristic_claim(
    claim_id: str, claim_type: str, severity: str, confidence: float, unknowns: list[str]
) -> Claim:
    """
    Create HEURISTIC claim (pattern-based, low confidence)

    Args:
        claim_id: Claim ID
        claim_type: Type
        severity: Severity level
        confidence: Confidence (typically 0.2-0.5 for heuristic)
        unknowns: List of unknowns

    Returns:
        Claim with confidence_basis=HEURISTIC

    Raises:
        ValueError: If confidence > 0.5 (heuristic should be low confidence)
    """
    if confidence > 0.5:
        raise ValueError(f"HEURISTIC claims should have confidence <= 0.5, got {confidence}")

    return Claim(
        id=claim_id,
        type=claim_type,
        severity=severity,
        confidence=confidence,
        confidence_basis=ConfidenceBasis.HEURISTIC,
        proof_obligation=ProofObligation(assumptions=[], broken_if=[], unknowns=unknowns),
    )
