"""
Semantic Differ

동작 변화 vs 순수 리팩토링 구분.
"""

from src.contexts.code_foundation.domain.models import EdgeKind
from src.contexts.code_foundation.infrastructure.document.graph_document import GraphDocument
from src.contexts.code_foundation.infrastructure.document.ir_document import IRDocument
from src.contexts.reasoning_engine.domain.models import (
    EffectSet,
    SemanticDiff,
)

from .effect_differ import EffectDiffer
from .effect_system import EffectAnalyzer


class SemanticDiffer:
    """
    의미적 변화 감지.

    동작 변화 vs 순수 리팩토링 구분.
    """

    def __init__(self, old_graph: GraphDocument, new_graph: GraphDocument):
        self.old_graph = old_graph
        self.new_graph = new_graph
        self.effect_analyzer_old = EffectAnalyzer(old_graph)
        self.effect_analyzer_new = EffectAnalyzer(new_graph)
        self.effect_differ = EffectDiffer()

    def detect_behavior_change(self, old_ir: IRDocument, new_ir: IRDocument) -> SemanticDiff:
        """
        의미적 변화 감지.

        검사 항목:
        1. Signature 변화
        2. Call graph 변화
        3. Effect 변화
        4. Reachable set 변화 (optional)
        """
        # 1. Signature 변화
        sig_changes = self._compare_signatures(old_ir, new_ir)

        # 2. Call graph 변화
        call_changes = self._compare_call_edges()

        # 3. Effect 변화
        old_effects = self.effect_analyzer_old.analyze_all(old_ir)
        new_effects = self.effect_analyzer_new.analyze_all(new_ir)
        effect_changes = self._compare_effects(old_effects, new_effects)

        # 4. Reachable set 변화 (placeholder)
        reachable_changes = {}

        # 5. 순수 리팩토링 판정
        is_refactoring = self._is_pure_refactoring(sig_changes, call_changes, effect_changes)

        # 6. Confidence 계산
        confidence = self._calculate_confidence(sig_changes, call_changes, effect_changes)

        # 7. Reason 생성
        reason = self._explain_changes(sig_changes, effect_changes)

        return SemanticDiff(
            signature_changes=sig_changes,
            call_graph_changes=call_changes,
            effect_changes=effect_changes,
            reachable_set_changes=reachable_changes,
            is_pure_refactoring=is_refactoring,
            confidence=confidence,
            reason=reason,
        )

    def _compare_signatures(self, old_ir: IRDocument, new_ir: IRDocument) -> list[str]:
        """Signature 변화 감지"""
        changes = []

        # Symbol ID로 매칭
        old_nodes = {n.id: n for n in old_ir.nodes}
        new_nodes = {n.id: n for n in new_ir.nodes}

        common_ids = set(old_nodes.keys()) & set(new_nodes.keys())

        for symbol_id in common_ids:
            old_node = old_nodes[symbol_id]
            new_node = new_nodes[symbol_id]

            # 파라미터 비교
            old_params = [p.type_annotation for p in old_node.params]
            new_params = [p.type_annotation for p in new_node.params]

            # 반환 타입 비교
            old_return = old_node.return_type
            new_return = new_node.return_type

            if old_params != new_params or old_return != new_return:
                changes.append(f"{symbol_id}: signature changed")

        return changes

    def _compare_call_edges(self) -> dict[str, list]:
        """Call graph 변화"""
        old_calls = {(e.source_node_id, e.target_node_id) for e in self.old_graph.edges if e.kind == EdgeKind.CALLS}

        new_calls = {(e.source_node_id, e.target_node_id) for e in self.new_graph.edges if e.kind == EdgeKind.CALLS}

        return {"added": list(new_calls - old_calls), "removed": list(old_calls - new_calls)}

    def _compare_effects(
        self, old_effects: dict[str, EffectSet], new_effects: dict[str, EffectSet]
    ) -> dict[str, tuple[EffectSet, EffectSet]]:
        """Effect 변화"""
        changes = {}

        common_symbols = set(old_effects.keys()) & set(new_effects.keys())

        for symbol_id in common_symbols:
            old_effect = old_effects[symbol_id]
            new_effect = new_effects[symbol_id]

            # Effect 변화가 있으면 기록
            if old_effect.effects != new_effect.effects:
                changes[symbol_id] = (old_effect, new_effect)

        return changes

    def _is_pure_refactoring(self, sig_changes: list[str], call_changes: dict[str, list], effect_changes: dict) -> bool:
        """
        순수 리팩토링 판정.

        조건:
        - Signature 변경 없음
        - Effect 변경 없음
        - Call graph 변경이 최소한
        """
        # Signature 변경 있으면 refactoring 아님
        if len(sig_changes) > 0:
            return False

        # Effect 변경 있으면 refactoring 아님
        if len(effect_changes) > 0:
            return False

        # Call graph 변경이 많으면 refactoring 아님
        if not self._is_minimal_call_change(call_changes):
            return False

        return True

    def _is_minimal_call_change(self, call_changes: dict) -> bool:
        """Call graph 변경이 최소한인지"""
        added = call_changes.get("added", [])
        removed = call_changes.get("removed", [])

        # 변경이 10개 이하면 minimal로 간주
        return len(added) + len(removed) <= 10

    def _calculate_confidence(self, sig_changes: list[str], call_changes: dict, effect_changes: dict) -> float:
        """
        Confidence 계산.

        높은 confidence:
        - Signature 변경: 1.0
        - Effect 변경: 0.9
        - Call graph만 변경: 0.7
        """
        if len(sig_changes) > 0:
            return 1.0

        if len(effect_changes) > 0:
            return 0.9

        if len(call_changes.get("added", [])) + len(call_changes.get("removed", [])) > 0:
            return 0.7

        return 1.0

    def _explain_changes(self, sig_changes: list[str], effect_changes: dict) -> str:
        """변경 사유 설명"""
        reasons = []

        if len(sig_changes) > 0:
            reasons.append(f"{len(sig_changes)} signature(s) changed")

        if len(effect_changes) > 0:
            reasons.append(f"{len(effect_changes)} effect(s) changed")

        if not reasons:
            return "No significant changes"

        return ", ".join(reasons)
