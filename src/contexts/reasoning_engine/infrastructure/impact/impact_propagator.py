"""
Impact Propagator

Graph 기반 영향 전파.
Signature 변경이 caller들에게 전파되는지 계산.
"""

from collections import deque

# GraphDocument removed - using IRDocument instead
from src.contexts.code_foundation.infrastructure.ir.models import EdgeKind, IRDocument
from src.contexts.reasoning_engine.domain.models import ImpactLevel, ImpactType


class GraphBasedImpactPropagator:
    """
    Call/Import Graph 기반 영향 전파.

    전파 규칙:
    - SIGNATURE_CHANGE → caller들로 전파 (call graph)
    - STRUCTURAL_CHANGE → importer들로 전파 (import graph)
    - IR_LOCAL → 전파 안함
    """

    def __init__(self, graph: IRDocument):
        self.graph = graph
        self._build_reverse_indices()

    def _build_reverse_indices(self):
        """Reverse index 구축 (callee → callers, target → importers)"""
        self.callers_map: dict[str, set[str]] = {}  # callee_id → caller_ids
        self.importers_map: dict[str, set[str]] = {}  # target_id → importer_ids

        for edge in self.graph.edges:
            if edge.kind == EdgeKind.CALLS:
                callee_id = edge.target_node_id
                caller_id = edge.source_node_id

                if callee_id not in self.callers_map:
                    self.callers_map[callee_id] = set()

                self.callers_map[callee_id].add(caller_id)

            elif edge.kind == EdgeKind.IMPORTS:
                target_id = edge.target_node_id
                importer_id = edge.source_node_id

                if target_id not in self.importers_map:
                    self.importers_map[target_id] = set()

                self.importers_map[target_id].add(importer_id)

    def propagate(self, changed_symbols: set[str], impact_types: dict[str, ImpactType], max_depth: int = 5) -> set[str]:
        """
        영향 받는 심볼 집합 계산.

        Args:
            changed_symbols: 변경된 심볼 집합
            impact_types: 각 심볼의 영향도
            max_depth: 최대 전파 깊이

        Returns:
            영향 받는 모든 심볼 집합 (changed_symbols 포함)
        """
        affected = set(changed_symbols)
        queue = deque([(sym, 0) for sym in changed_symbols])

        while queue:
            symbol_id, depth = queue.popleft()

            # 최대 깊이 체크
            if depth >= max_depth:
                continue

            impact = impact_types.get(symbol_id)
            if not impact:
                continue

            # SIGNATURE_CHANGE만 caller로 전파
            if impact.level == ImpactLevel.SIGNATURE_CHANGE:
                callers = self.callers_map.get(symbol_id, set())
                for caller in callers:
                    if caller not in affected:
                        affected.add(caller)
                        queue.append((caller, depth + 1))

            # STRUCTURAL_CHANGE는 importer로 전파
            if impact.level == ImpactLevel.STRUCTURAL_CHANGE:
                importers = self.importers_map.get(symbol_id, set())
                for importer in importers:
                    if importer not in affected:
                        affected.add(importer)
                        queue.append((importer, depth + 1))

        return affected

    def find_callers(self, symbol_id: str, max_depth: int = 3) -> set[str]:
        """특정 심볼의 caller 집합 (재귀)"""
        callers = set()
        queue = deque([(symbol_id, 0)])
        visited = set()

        while queue:
            current_id, depth = queue.popleft()

            if current_id in visited or depth >= max_depth:
                continue

            visited.add(current_id)

            direct_callers = self.callers_map.get(current_id, set())
            for caller in direct_callers:
                callers.add(caller)
                queue.append((caller, depth + 1))

        return callers

    def find_importers(self, symbol_id: str, max_depth: int = 3) -> set[str]:
        """특정 심볼의 importer 집합 (재귀)"""
        importers = set()
        queue = deque([(symbol_id, 0)])
        visited = set()

        while queue:
            current_id, depth = queue.popleft()

            if current_id in visited or depth >= max_depth:
                continue

            visited.add(current_id)

            direct_importers = self.importers_map.get(current_id, set())
            for importer in direct_importers:
                importers.add(importer)
                queue.append((importer, depth + 1))

        return importers

    def estimate_rebuild_cost(self, affected_symbols: set[str]) -> dict:
        """재빌드 비용 추정"""
        # Symbol 종류별로 분류
        # (실제로는 IR 문서를 참조해야 하지만 여기서는 단순화)

        return {
            "affected_count": len(affected_symbols),
            "estimated_files": len(affected_symbols) // 10,  # 대략적 추정
            "estimated_time_ms": len(affected_symbols) * 5,  # 심볼당 5ms 가정
        }
