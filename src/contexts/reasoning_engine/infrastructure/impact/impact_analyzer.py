"""
ImpactAnalyzer - 변경 영향 전파 분석

GraphDocument의 call graph + data flow를 기반으로 영향 분석
"""

import logging
from collections import deque

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdgeKind,
    GraphNode,
)

from ...domain.effect_models import EffectDiff
from ...domain.impact_models import ImpactLevel, ImpactNode, ImpactPath, ImpactReport, PropagationType

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    """
    변경 영향 분석

    Example:
        analyzer = ImpactAnalyzer(graph_doc)
        report = analyzer.analyze_impact("func1")

        for node in report.get_critical_nodes():
            print(f"Critical impact: {node.name}")
    """

    def __init__(self, graph: GraphDocument, max_depth: int = 5, min_confidence: float = 0.3):
        """
        Initialize ImpactAnalyzer

        Args:
            graph: GraphDocument
            max_depth: Maximum propagation depth
            min_confidence: Minimum confidence threshold
        """
        self.graph = graph
        self.max_depth = max_depth
        self.min_confidence = min_confidence
        logger.info(f"ImpactAnalyzer initialized (max_depth={max_depth})")

    def analyze_impact(self, source_id: str, effect_diff: EffectDiff | None = None) -> ImpactReport:
        """
        변경 영향 분석

        Args:
            source_id: Source symbol ID
            effect_diff: Optional EffectDiff for severity calculation

        Returns:
            ImpactReport
        """
        logger.info(f"Analyzing impact from {source_id}")

        # BFS로 영향 전파
        impacted_nodes = self._propagate_impact(source_id, effect_diff)

        # Impact paths 계산
        paths = self._calculate_paths(source_id, impacted_nodes)

        # Total impact 계산
        total_impact = self._calculate_total_impact(impacted_nodes, effect_diff)

        report = ImpactReport(
            source_id=source_id,
            impacted_nodes=impacted_nodes,
            impact_paths=paths,
            total_impact=total_impact,
            metadata={"max_depth": self.max_depth, "effect_diff": effect_diff.summary() if effect_diff else None},
        )

        logger.info(f"Impact analysis complete: {len(impacted_nodes)} nodes, total_impact={total_impact.value}")

        return report

    def _propagate_impact(self, source_id: str, effect_diff: EffectDiff | None) -> list[ImpactNode]:
        """
        BFS로 영향 전파

        Returns:
            List of ImpactNode
        """
        visited: set[str] = set()
        queue = deque([(source_id, 0, 1.0, PropagationType.DIRECT_CALL)])  # (id, depth, confidence, type)
        impacted: list[ImpactNode] = []

        while queue:
            current_id, depth, confidence, prop_type = queue.popleft()

            if current_id in visited:
                continue

            if depth > self.max_depth:
                continue

            if confidence < self.min_confidence:
                continue

            visited.add(current_id)

            # Get node from graph
            node = self.graph.get_node(current_id)
            if not node:
                continue

            # Skip source itself
            if current_id == source_id:
                # Add to queue for propagation
                self._add_neighbors_to_queue(current_id, depth, confidence, queue)
                continue

            # Calculate impact level
            impact_level = self._calculate_impact_level(node, depth, confidence, effect_diff)

            # Create ImpactNode
            impact_node = ImpactNode(
                symbol_id=current_id,
                name=node.name,
                kind=node.kind.value,
                file_path=node.path,
                impact_level=impact_level,
                distance=depth,
                propagation_type=prop_type,
                confidence=confidence,
                metadata={"fqn": node.fqn},
            )

            impacted.append(impact_node)

            # Continue propagation
            self._add_neighbors_to_queue(current_id, depth, confidence, queue)

        logger.debug(f"Propagated to {len(impacted)} nodes")
        return impacted

    def _add_neighbors_to_queue(self, node_id: str, depth: int, confidence: float, queue: deque):
        """Queue에 이웃 노드 추가"""
        # Direct calls (callers)
        for edge in self.graph.graph_edges:
            if edge.kind == GraphEdgeKind.CALLS and edge.target_id == node_id:
                # Caller는 영향받음
                new_confidence = confidence * 0.9  # 거리에 따라 confidence 감소
                queue.append((edge.source_id, depth + 1, new_confidence, PropagationType.DIRECT_CALL))

        # Data flow (참조 관계는 추후 확장)
        # 현재는 CALLS만 지원

        # Type dependencies
        for edge in self.graph.graph_edges:
            if edge.kind == GraphEdgeKind.INHERITS and edge.source_id == node_id:
                # 상속받는 클래스
                new_confidence = confidence * 0.8
                queue.append((edge.target_id, depth + 1, new_confidence, PropagationType.INHERITANCE))

    def _calculate_impact_level(
        self, node: GraphNode, distance: int, confidence: float, effect_diff: EffectDiff | None
    ) -> ImpactLevel:
        """
        Impact level 계산

        거리, confidence, effect severity 고려
        """
        # Base impact by distance
        if distance == 1:
            base_impact = ImpactLevel.HIGH
        elif distance == 2:
            base_impact = ImpactLevel.MEDIUM
        else:
            base_impact = ImpactLevel.LOW

        # Adjust by confidence
        if confidence < 0.5:
            if base_impact == ImpactLevel.HIGH:
                base_impact = ImpactLevel.MEDIUM
            elif base_impact == ImpactLevel.MEDIUM:
                base_impact = ImpactLevel.LOW

        # Adjust by effect diff
        if effect_diff:
            if effect_diff.severity == "critical":
                if base_impact == ImpactLevel.MEDIUM:
                    base_impact = ImpactLevel.HIGH
                elif base_impact == ImpactLevel.HIGH:
                    base_impact = ImpactLevel.CRITICAL
            elif effect_diff.is_breaking:
                if base_impact == ImpactLevel.LOW:
                    base_impact = ImpactLevel.MEDIUM

        return base_impact

    def _calculate_paths(self, source_id: str, impacted_nodes: list[ImpactNode]) -> list[ImpactPath]:
        """
        영향 경로 계산

        각 impacted node까지의 최단 경로
        """
        paths = []

        for node in impacted_nodes:
            # BFS로 최단 경로 찾기
            path = self._find_shortest_path(source_id, node.symbol_id)
            if path:
                paths.append(path)

        return paths

    def _find_shortest_path(self, source: str, target: str) -> ImpactPath | None:
        """BFS로 최단 경로"""
        visited = set()
        queue = deque([(source, [source], [])])  # (current, path, types)

        while queue:
            current, path, types = queue.popleft()

            if current == target:
                return ImpactPath(source=source, target=target, nodes=path, propagation_types=types)

            if current in visited:
                continue

            visited.add(current)

            # Explore neighbors
            for edge in self.graph.graph_edges:
                if edge.source_id == current or edge.target_id == current:
                    next_node = edge.target_id if edge.source_id == current else edge.source_id

                    if next_node not in visited:
                        prop_type = self._edge_to_propagation_type(edge.kind)
                        queue.append((next_node, path + [next_node], types + [prop_type]))

        return None

    def _edge_to_propagation_type(self, edge_kind: GraphEdgeKind) -> PropagationType:
        """GraphEdgeKind → PropagationType"""
        if edge_kind == GraphEdgeKind.CALLS:
            return PropagationType.DIRECT_CALL
        elif edge_kind == GraphEdgeKind.INHERITS:
            return PropagationType.INHERITANCE
        elif edge_kind == GraphEdgeKind.IMPORTS:
            return PropagationType.IMPORT
        else:
            return PropagationType.DIRECT_CALL

    def _calculate_total_impact(self, impacted_nodes: list[ImpactNode], effect_diff: EffectDiff | None) -> ImpactLevel:
        """
        전체 impact level 계산

        가장 높은 impact + 영향받는 노드 수 고려
        """
        if not impacted_nodes:
            return ImpactLevel.NONE

        # Max impact
        max_impact = max(n.impact_level for n in impacted_nodes)

        # Count by level
        critical_count = len([n for n in impacted_nodes if n.impact_level == ImpactLevel.CRITICAL])
        high_count = len([n for n in impacted_nodes if n.impact_level == ImpactLevel.HIGH])

        # Upgrade if many high-impact nodes
        if critical_count > 0:
            return ImpactLevel.CRITICAL

        if high_count >= 5:
            return ImpactLevel.CRITICAL

        if high_count >= 2:
            return ImpactLevel.HIGH

        return max_impact

    def batch_analyze(
        self, source_ids: list[str], effect_diffs: dict[str, EffectDiff] | None = None
    ) -> dict[str, ImpactReport]:
        """
        여러 source 동시 분석

        Args:
            source_ids: List of source IDs
            effect_diffs: Optional {source_id: EffectDiff}

        Returns:
            {source_id: ImpactReport}
        """
        reports = {}

        for source_id in source_ids:
            effect_diff = effect_diffs.get(source_id) if effect_diffs else None
            report = self.analyze_impact(source_id, effect_diff)
            reports[source_id] = report

        logger.info(f"Batch analyzed {len(reports)} sources")
        return reports
