"""Arbitration Engine - Claim prioritization and conflict resolution"""

from typing import Any

from codegraph_engine.shared_kernel.contracts import Claim
from codegraph_engine.shared_kernel.contracts.confidence import CONFIDENCE_BASIS_PRIORITY


class ArbitrationEngine:
    """
    결정적 우선순위 기반 Claim 중재 엔진.

    Priority Rules:
        PROVEN > INFERRED > HEURISTIC > UNKNOWN

    Suppression Rules:
        - 같은 (type, severity)에 대해 우선순위 낮은 Claim 억제
        - 억제된 Claim은 suppressed=True, suppression_reason 설정
    """

    def arbitrate(self, claims: list[Claim]) -> list[Claim]:
        """
        Claim 우선순위 중재.

        Args:
            claims: 중재할 Claim 리스트

        Returns:
            중재된 Claim 리스트 (억제 정보 포함)
        """
        if not claims:
            return []

        # Priority에 따라 정렬 (낮은 숫자 = 높은 우선순위)
        sorted_claims = sorted(claims, key=self._get_priority)

        result: list[Claim] = []
        seen: dict[str, Claim] = {}

        for claim in sorted_claims:
            # 동일 (type, severity) 키
            key = f"{claim.type}:{claim.severity}"

            if key in seen:
                existing = seen[key]

                # 현재 claim이 우선순위 낮으면 억제
                if self._get_priority(claim) > self._get_priority(existing):
                    claim = Claim(
                        id=claim.id,
                        type=claim.type,
                        severity=claim.severity,
                        confidence=claim.confidence,
                        confidence_basis=claim.confidence_basis,
                        proof_obligation=claim.proof_obligation,
                        suppressed=True,
                        suppression_reason=f"Superseded by {existing.id} ({existing.confidence_basis.value})",
                    )
            else:
                seen[key] = claim

            result.append(claim)

        return result

    def _get_priority(self, claim: Claim) -> int:
        """Claim 우선순위 계산 (낮을수록 높은 우선순위)"""
        return CONFIDENCE_BASIS_PRIORITY[claim.confidence_basis]

    def filter_suppressed(self, claims: list[Claim]) -> list[Claim]:
        """억제되지 않은 Claim만 반환"""
        return [c for c in claims if not c.suppressed]

    def get_highest_priority_claims(self, claims: list[Claim], limit: int = 10) -> list[Claim]:
        """가장 높은 우선순위 Claim N개 반환"""
        sorted_claims = sorted(claims, key=self._get_priority)
        return sorted_claims[:limit]

    def group_by_type(self, claims: list[Claim]) -> dict[str, list[Claim]]:
        """Claim을 type별로 그룹화"""
        groups: dict[str, list[Claim]] = {}
        for claim in claims:
            if claim.type not in groups:
                groups[claim.type] = []
            groups[claim.type].append(claim)
        return groups

    def group_by_severity(self, claims: list[Claim]) -> dict[str, list[Claim]]:
        """Claim을 severity별로 그룹화"""
        groups: dict[str, list[Claim]] = {}
        for claim in claims:
            if claim.severity not in groups:
                groups[claim.severity] = []
            groups[claim.severity].append(claim)
        return groups

    def get_arbitration_stats(self, claims: list[Claim]) -> dict[str, Any]:
        """중재 통계"""
        total = len(claims)
        suppressed = sum(1 for c in claims if c.suppressed)
        active = total - suppressed

        by_basis = {}
        for claim in claims:
            basis = claim.confidence_basis.value
            by_basis[basis] = by_basis.get(basis, 0) + 1

        return {
            "total_claims": total,
            "active_claims": active,
            "suppressed_claims": suppressed,
            "suppression_rate": suppressed / total if total > 0 else 0.0,
            "by_confidence_basis": by_basis,
        }
