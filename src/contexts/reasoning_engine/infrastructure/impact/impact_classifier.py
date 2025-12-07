"""
Impact Classifier

Hash 비교 기반 영향도 분류.
"""

from src.contexts.reasoning_engine.domain.models import (
    ImpactLevel,
    ImpactType,
    SymbolHash,
)


class ImpactClassifier:
    """
    Hash 비교 기반 영향도 분류.

    변경 유형:
    - NO_IMPACT: Hash 모두 동일
    - IR_LOCAL: Body만 변경
    - SIGNATURE_CHANGE: Signature 변경
    - STRUCTURAL_CHANGE: Import/Export 구조 변경 (별도 감지 필요)
    """

    def classify(self, old_hash: SymbolHash, new_hash: SymbolHash) -> ImpactType:
        """
        Hash 비교로 영향도 결정.

        우선순위:
        1. Signature 변경 → SIGNATURE_CHANGE (가장 위험)
        2. Body 변경 → IR_LOCAL
        3. 모두 동일 → NO_IMPACT
        """
        # 1. Signature 변경 체크
        if old_hash.signature_hash != new_hash.signature_hash:
            return ImpactType(
                level=ImpactLevel.SIGNATURE_CHANGE,
                affected_symbols=[new_hash.symbol_id],
                reason="Signature changed (params or return type)",
                confidence=1.0,
            )

        # 2. Body 변경 체크
        if old_hash.body_hash != new_hash.body_hash:
            return ImpactType(
                level=ImpactLevel.IR_LOCAL,
                affected_symbols=[new_hash.symbol_id],
                reason="Body changed, signature unchanged",
                confidence=1.0,
            )

        # 3. Impact hash 변경 체크
        # (Callee의 signature가 변경된 경우)
        if old_hash.impact_hash != new_hash.impact_hash:
            return ImpactType(
                level=ImpactLevel.SIGNATURE_CHANGE,
                affected_symbols=[new_hash.symbol_id],
                reason="Callee signature changed (transitive impact)",
                confidence=0.95,
            )

        # 4. 변경 없음
        return ImpactType(level=ImpactLevel.NO_IMPACT, affected_symbols=[], reason="No change detected", confidence=1.0)

    def classify_batch(
        self, old_hashes: dict[str, SymbolHash], new_hashes: dict[str, SymbolHash]
    ) -> dict[str, ImpactType]:
        """
        여러 심볼의 영향도를 일괄 분류.

        Returns:
            symbol_id → ImpactType
        """
        result = {}

        # 1. 공통 심볼 (변경 또는 불변)
        common_symbols = set(old_hashes.keys()) & set(new_hashes.keys())
        for symbol_id in common_symbols:
            old_hash = old_hashes[symbol_id]
            new_hash = new_hashes[symbol_id]
            result[symbol_id] = self.classify(old_hash, new_hash)

        # 2. 새로 추가된 심볼
        added_symbols = set(new_hashes.keys()) - set(old_hashes.keys())
        for symbol_id in added_symbols:
            result[symbol_id] = ImpactType(
                level=ImpactLevel.STRUCTURAL_CHANGE, affected_symbols=[symbol_id], reason="Symbol added", confidence=1.0
            )

        # 3. 삭제된 심볼
        removed_symbols = set(old_hashes.keys()) - set(new_hashes.keys())
        for symbol_id in removed_symbols:
            result[symbol_id] = ImpactType(
                level=ImpactLevel.STRUCTURAL_CHANGE,
                affected_symbols=[symbol_id],
                reason="Symbol removed",
                confidence=1.0,
            )

        return result

    def get_changed_symbols(self, impact_types: dict[str, ImpactType]) -> set[str]:
        """변경된 심볼 집합 반환 (NO_IMPACT 제외)"""
        changed = set()

        for symbol_id, impact in impact_types.items():
            if impact.level != ImpactLevel.NO_IMPACT:
                changed.add(symbol_id)

        return changed

    def get_signature_changed_symbols(self, impact_types: dict[str, ImpactType]) -> set[str]:
        """Signature가 변경된 심볼 집합"""
        changed = set()

        for symbol_id, impact in impact_types.items():
            if impact.level == ImpactLevel.SIGNATURE_CHANGE:
                changed.add(symbol_id)

        return changed

    def summary(self, impact_types: dict[str, ImpactType]) -> dict[str, int]:
        """영향도 분류 요약"""
        summary = {
            "no_impact": 0,
            "ir_local": 0,
            "signature_change": 0,
            "structural_change": 0,
        }

        for impact in impact_types.values():
            if impact.level == ImpactLevel.NO_IMPACT:
                summary["no_impact"] += 1
            elif impact.level == ImpactLevel.IR_LOCAL:
                summary["ir_local"] += 1
            elif impact.level == ImpactLevel.SIGNATURE_CHANGE:
                summary["signature_change"] += 1
            elif impact.level == ImpactLevel.STRUCTURAL_CHANGE:
                summary["structural_change"] += 1

        return summary
