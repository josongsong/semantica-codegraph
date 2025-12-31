"""
ImpactAnalyzer - 변경 영향 전파 분석

GraphDocument의 call graph + data flow를 기반으로 영향 분석

Performance: O(V+E) - 인접 리스트 인덱스 사용
- 이전: O(V*E) - 매 노드마다 전체 엣지 순회
- 현재: O(V+E) - 인덱스 기반 O(1) 이웃 조회

Phase 2 Optimization: Lazy evaluation
- Paths are computed lazily (only when accessed)
- Batch analysis with parallel processing
"""

import logging
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdgeKind,
    GraphNode,
)

from ...domain.effect_models import EffectDiff
from ...domain.impact_models import ImpactLevel, ImpactNode, ImpactPath, ImpactReport, PropagationType

logger = logging.getLogger(__name__)


# Impact analysis constants
CONFIDENCE_DECAY_CALL = 0.9  # Confidence decay for direct calls
CONFIDENCE_DECAY_INHERITANCE = 0.8  # Confidence decay for inheritance
CONFIDENCE_THRESHOLD_LOW = 0.5  # Below this, downgrade impact level
CRITICAL_HIGH_COUNT_THRESHOLD = 5  # High-impact nodes needed for critical
HIGH_COUNT_THRESHOLD = 2  # High-impact nodes needed for high total


# =========================================================================
# Phase 2: Lazy Evaluation Classes
# =========================================================================


class LazyPaths:
    """
    Lazy path computation wrapper.

    Phase 2 Optimization: Paths are only computed when accessed.
    This saves computation when only impact nodes are needed, not full paths.

    Usage:
        paths = LazyPaths(compute_fn)
        # Computation happens here:
        for path in paths:
            print(path)
    """

    def __init__(self, compute_fn: Callable[[], list[ImpactPath]]):
        self._compute_fn = compute_fn
        self._paths: list[ImpactPath] | None = None
        self._computed = False

    def _ensure_computed(self) -> None:
        if not self._computed:
            self._paths = self._compute_fn()
            self._computed = True

    def __iter__(self) -> Iterator[ImpactPath]:
        self._ensure_computed()
        return iter(self._paths or [])

    def __len__(self) -> int:
        self._ensure_computed()
        return len(self._paths or [])

    def __getitem__(self, index: int) -> ImpactPath:
        self._ensure_computed()
        if self._paths is None:
            raise IndexError("No paths computed")
        return self._paths[index]

    def __bool__(self) -> bool:
        self._ensure_computed()
        return bool(self._paths)

    @property
    def is_computed(self) -> bool:
        """Check if paths have been computed."""
        return self._computed

    def to_list(self) -> list[ImpactPath]:
        """Force computation and return list."""
        self._ensure_computed()
        return self._paths or []


class ImpactAnalyzer:
    """
    변경 영향 분석 (O(V+E) 최적화)

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

        # Build adjacency indices for O(1) neighbor lookup (one-time O(E) cost)
        self._build_indices()

        logger.info(f"ImpactAnalyzer initialized (max_depth={max_depth}, indexed)")

    def _build_indices(self) -> None:
        """
        Build adjacency list indices for O(1) neighbor access

        Complexity: O(E) one-time cost (uses GraphDocument's pre-built indexes where possible)
        """
        # Callers: target → [(source, edge_kind), ...] (who calls this)
        self._callers: dict[str, list[tuple[str, GraphEdgeKind]]] = {}
        # Callees: source → [(target, edge_kind), ...] (who this calls)
        self._callees: dict[str, list[tuple[str, GraphEdgeKind]]] = {}
        # Neighbors: both directions for path finding
        self._neighbors: dict[str, list[tuple[str, GraphEdgeKind]]] = {}

        # Use GraphDocument's pre-built indexes for efficient iteration
        for node_id in self.graph.graph_nodes:
            # Forward edges (callees) - use outgoing index
            outgoing_edge_ids = self.graph.indexes.outgoing.get(node_id, [])
            for edge_id in outgoing_edge_ids:
                edge = self.graph.edge_by_id.get(edge_id)
                if not edge:
                    continue
                # Support both infrastructure.graph.models.GraphEdge (target_id, kind)
                # and domain.models.GraphEdge (target, type)
                target_id = getattr(edge, "target_id", None) or getattr(edge, "target", None)
                edge_kind = getattr(edge, "kind", None) or getattr(edge, "type", None)

                if node_id not in self._callees:
                    self._callees[node_id] = []
                self._callees[node_id].append((target_id, edge_kind))

                # Forward neighbor
                if node_id not in self._neighbors:
                    self._neighbors[node_id] = []
                self._neighbors[node_id].append((target_id, edge_kind))

            # Backward edges (callers) - use incoming index
            incoming_edge_ids = self.graph.indexes.incoming.get(node_id, [])
            for edge_id in incoming_edge_ids:
                edge = self.graph.edge_by_id.get(edge_id)
                if not edge:
                    continue
                # Support both infrastructure.graph.models.GraphEdge (source_id, kind)
                # and domain.models.GraphEdge (source, type)
                source_id = getattr(edge, "source_id", None) or getattr(edge, "source", None)
                edge_kind = getattr(edge, "kind", None) or getattr(edge, "type", None)

                if node_id not in self._callers:
                    self._callers[node_id] = []
                self._callers[node_id].append((source_id, edge_kind))

                # Backward neighbor
                if node_id not in self._neighbors:
                    self._neighbors[node_id] = []
                self._neighbors[node_id].append((source_id, edge_kind))

    def analyze_impact(
        self, source_id: str, effect_diff: EffectDiff | None = None, lazy_paths: bool = True
    ) -> ImpactReport:
        """
        변경 영향 분석

        Phase 2 Optimization: Lazy path computation
        - When lazy_paths=True, paths are computed only when accessed
        - This speeds up analysis when only impact nodes are needed

        Args:
            source_id: Source symbol ID
            effect_diff: Optional EffectDiff for severity calculation
            lazy_paths: If True, defer path computation until accessed (default: True)

        Returns:
            ImpactReport
        """
        logger.info(f"Analyzing impact from {source_id} (lazy_paths={lazy_paths})")

        # BFS로 영향 전파
        impacted_nodes = self._propagate_impact(source_id, effect_diff)

        # Total impact 계산 (always computed)
        total_impact = self._calculate_total_impact(impacted_nodes, effect_diff)

        # Phase 2: Lazy path computation
        if lazy_paths:
            # Create lazy paths wrapper - computation deferred
            lazy_path_wrapper = LazyPaths(lambda: self._calculate_paths(source_id, impacted_nodes))
            # Note: We still need to pass a list to ImpactReport
            # The lazy wrapper will be stored in metadata for advanced use
            paths: list[ImpactPath] = []  # Empty initially
            metadata = {
                "max_depth": self.max_depth,
                "effect_diff": effect_diff.summary() if effect_diff else None,
                "lazy_paths": lazy_path_wrapper,
                "paths_computed": False,
            }
        else:
            # Eager path computation (original behavior)
            paths = self._calculate_paths(source_id, impacted_nodes)
            metadata = {
                "max_depth": self.max_depth,
                "effect_diff": effect_diff.summary() if effect_diff else None,
                "paths_computed": True,
            }

        report = ImpactReport(
            source_id=source_id,
            impacted_nodes=impacted_nodes,
            impact_paths=paths,
            total_impact=total_impact,
            metadata=metadata,
        )

        logger.info(f"Impact analysis complete: {len(impacted_nodes)} nodes, total_impact={total_impact.value}")

        return report

    def get_paths_from_report(self, report: ImpactReport) -> list[ImpactPath]:
        """
        Get paths from report, computing lazily if needed.

        Phase 2 Optimization: Trigger lazy computation.

        Args:
            report: ImpactReport (may have lazy paths)

        Returns:
            List of ImpactPath
        """
        if report.impact_paths:
            return report.impact_paths

        # Check for lazy paths in metadata
        lazy_wrapper = report.metadata.get("lazy_paths")
        if isinstance(lazy_wrapper, LazyPaths):
            return lazy_wrapper.to_list()

        return []

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
            # Handle both GraphNode (type) and IR Node (kind)
            node_kind = getattr(node, "kind", None) or getattr(node, "type", "unknown")
            if hasattr(node_kind, "value"):
                node_kind = node_kind.value

            node_path = getattr(node, "path", None) or getattr(node, "file_path", "")
            node_fqn = getattr(node, "fqn", "")

            impact_node = ImpactNode(
                symbol_id=current_id,
                name=node.name,
                kind=str(node_kind),
                file_path=node_path,
                impact_level=impact_level,
                distance=depth,
                propagation_type=prop_type,
                confidence=confidence,
                metadata={"fqn": node_fqn},
            )

            impacted.append(impact_node)

            # Continue propagation
            self._add_neighbors_to_queue(current_id, depth, confidence, queue)

        logger.debug(f"Propagated to {len(impacted)} nodes")
        return impacted

    def _add_neighbors_to_queue(self, node_id: str, depth: int, confidence: float, queue: deque):
        """
        Queue에 이웃 노드 추가 (O(1) indexed lookup)

        이전: O(E) - 전체 엣지 순회
        현재: O(deg(v)) - 해당 노드의 이웃만 순회
        """
        # Callers (reverse direction - who calls this node) - O(deg)
        for caller_id, edge_kind in self._callers.get(node_id, []):
            if edge_kind == GraphEdgeKind.CALLS:
                new_confidence = confidence * CONFIDENCE_DECAY_CALL
                queue.append((caller_id, depth + 1, new_confidence, PropagationType.DIRECT_CALL))

        # Callees for inheritance propagation - O(deg)
        for target_id, edge_kind in self._callees.get(node_id, []):
            if edge_kind == GraphEdgeKind.INHERITS:
                new_confidence = confidence * CONFIDENCE_DECAY_INHERITANCE
                queue.append((target_id, depth + 1, new_confidence, PropagationType.INHERITANCE))

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
        if confidence < CONFIDENCE_THRESHOLD_LOW:
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
        """
        BFS로 최단 경로 (O(V+E) indexed lookup)

        이전: O(E) per node - 전체 엣지 순회
        현재: O(deg(v)) per node - 인덱스 사용
        """
        visited = set()
        queue = deque([(source, [source], [])])  # (current, path, types)

        while queue:
            current, path, types = queue.popleft()

            if current == target:
                return ImpactPath(source=source, target=target, nodes=path, propagation_types=types)

            if current in visited:
                continue

            visited.add(current)

            # Explore neighbors using index - O(deg)
            for neighbor_id, edge_kind in self._neighbors.get(current, []):
                if neighbor_id not in visited:
                    prop_type = self._edge_to_propagation_type(edge_kind)
                    queue.append((neighbor_id, path + [neighbor_id], types + [prop_type]))

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

        if high_count >= CRITICAL_HIGH_COUNT_THRESHOLD:
            return ImpactLevel.CRITICAL

        if high_count >= HIGH_COUNT_THRESHOLD:
            return ImpactLevel.HIGH

        return max_impact

    def batch_analyze(
        self,
        source_ids: list[str],
        effect_diffs: dict[str, EffectDiff] | None = None,
        parallel: bool = True,
        max_workers: int | None = None,
        lazy_paths: bool = True,
    ) -> dict[str, ImpactReport]:
        """
        여러 source 동시 분석

        Phase 2 Optimization: Parallel batch analysis
        - When parallel=True, analyze multiple sources concurrently
        - Combined with lazy_paths for maximum performance

        Args:
            source_ids: List of source IDs
            effect_diffs: Optional {source_id: EffectDiff}
            parallel: If True, use parallel processing (default: True)
            max_workers: Max parallel workers (default: min(4, len(source_ids)))
            lazy_paths: If True, defer path computation (default: True)

        Returns:
            {source_id: ImpactReport}
        """
        if not source_ids:
            return {}

        # Sequential for small batches
        if not parallel or len(source_ids) <= 2:
            reports = {}
            for source_id in source_ids:
                effect_diff = effect_diffs.get(source_id) if effect_diffs else None
                report = self.analyze_impact(source_id, effect_diff, lazy_paths=lazy_paths)
                reports[source_id] = report
            logger.info(f"Batch analyzed {len(reports)} sources (sequential)")
            return reports

        # Parallel for larger batches
        workers = max_workers or min(4, len(source_ids))
        reports: dict[str, ImpactReport] = {}

        def analyze_single(source_id: str) -> tuple[str, ImpactReport]:
            effect_diff = effect_diffs.get(source_id) if effect_diffs else None
            report = self.analyze_impact(source_id, effect_diff, lazy_paths=lazy_paths)
            return (source_id, report)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(analyze_single, sid) for sid in source_ids]

            for future in as_completed(futures):
                source_id, report = future.result()
                reports[source_id] = report

        logger.info(f"Batch analyzed {len(reports)} sources (parallel, workers={workers})")
        return reports
