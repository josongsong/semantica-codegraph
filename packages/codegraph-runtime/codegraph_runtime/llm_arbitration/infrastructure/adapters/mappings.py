"""
RFC-027 & RFC-028 Mapping Tables (공통)

팀 A (RFC-028)와 팀 B (RFC-027) 간 계약.

Architecture: Adapter Layer (공통 유틸리티)
"""

from codegraph_engine.shared_kernel.contracts import ConfidenceBasis

# ============================================================
# Verdict → ConfidenceBasis 매핑 (양 팀 공유)
# ============================================================

VERDICT_TO_CONFIDENCE_BASIS: dict[str, ConfidenceBasis] = {
    "proven": ConfidenceBasis.PROVEN,
    "likely": ConfidenceBasis.INFERRED,
    "heuristic": ConfidenceBasis.HEURISTIC,
}

# 역방향 매핑 (필요 시)
CONFIDENCE_BASIS_TO_VERDICT: dict[ConfidenceBasis, str] = {
    ConfidenceBasis.PROVEN: "proven",
    ConfidenceBasis.INFERRED: "likely",
    ConfidenceBasis.HEURISTIC: "heuristic",
    ConfidenceBasis.UNKNOWN: "heuristic",  # UNKNOWN도 heuristic으로 매핑
}


# ============================================================
# Complexity → Severity 매핑
# ============================================================

COMPLEXITY_TO_SEVERITY: dict[str, str] = {
    "O(1)": "info",
    "O(log n)": "info",
    "O(n)": "low",
    "O(n log n)": "medium",
    "O(n²)": "high",
    "O(n³)": "high",
    "O(2^n)": "critical",
    "O(n!)": "critical",
    "UNKNOWN": "medium",  # Conservative
}


# ============================================================
# Evidence Claim Linking Helper
# ============================================================


def link_evidence_to_claim(evidence, claim_id: str):
    """
    Link evidence to claim (팀 B가 사용)

    Args:
        evidence: Evidence with claim_ids=["pending"]
        claim_id: Actual claim ID

    Returns:
        New Evidence with updated claim_ids

    Note: Evidence는 immutable이므로 새 인스턴스 반환
    """
    from codegraph_engine.shared_kernel.contracts import Evidence

    # 새 Evidence 생성 (immutable이므로)
    return Evidence(
        id=evidence.id,
        kind=evidence.kind,
        location=evidence.location,
        content=evidence.content,
        provenance=evidence.provenance,
        claim_ids=[claim_id],  # ← 실제 ID로 교체
    )
