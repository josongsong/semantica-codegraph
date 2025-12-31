"""
TraversalEngine

Graph traversal using BFS/DFS.

Architecture:
- Infrastructure layer (uses UnifiedGraphIndex)
- BFS for shortest paths (breadth-first)
- Handles forward/backward traversal
- Handles loops (visited tracking)
- Respects depth and path limits

Contract:
- Returns paths in order of discovery (BFS = shortest first)
- No duplicate paths
- Respects all safety limits
- Handles cycles correctly
"""

from collections import deque
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.results import PathResult, UnifiedNode
from codegraph_engine.code_foundation.domain.query.types import TraversalDirection

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.selectors import EdgeSelector, NodeSelector

    from .edge_resolver import EdgeResolver
    from .graph_index import UnifiedGraphIndex
    from .node_matcher import NodeMatcher

logger = get_logger(__name__)


class TraversalEngine:
    """
    Graph traversal engine

    Uses BFS for finding shortest paths first.
    Tracks visited nodes to prevent infinite loops.

    Performance:
    - BFS: O(V + E) where V = nodes, E = edges
    - With limits: O(min(V+E, limit))
    - Memory: O(max_depth * max_paths) for path storage
    """

    def __init__(self, graph: "UnifiedGraphIndex", node_matcher: "NodeMatcher", edge_resolver: "EdgeResolver"):
        """
        Initialize traversal engine

        Args:
            graph: Unified graph index
            node_matcher: Node matcher
            edge_resolver: Edge resolver

        RFC-021 Day 1:
            - Added SCCP baseline support (lazy loading)
            - Unreachable block detection
            - Constant condition evaluation
        """
        self.graph = graph
        self.node_matcher = node_matcher
        self.edge_resolver = edge_resolver

        # RFC-021 Day 1: SCCP Baseline support (lazy loading!)
        # Note: SCCP is loaded on-demand in _ensure_sccp_loaded()
        # because SCCP runs in QueryEngine.execute_flow(), not at __init__ time
        self._sccp_result = None
        self._sccp_loaded = False

    def find_paths(
        self,
        source_selector: "NodeSelector",
        target_selector: "NodeSelector",
        edge_selector: "EdgeSelector",
        direction: TraversalDirection = TraversalDirection.FORWARD,
        max_depth: int = 10,
        max_paths: int = 100,
        max_nodes: int = 10000,
        timeout_ms: int | None = None,
        start_time: float | None = None,
    ) -> list[PathResult]:
        """
        Find paths from source to target

        Args:
            source_selector: Source node selector
            target_selector: Target node selector
            edge_selector: Edge selector
            direction: TraversalDirection.FORWARD or TraversalDirection.BACKWARD
            max_depth: Maximum path length (hops)
            max_paths: Maximum number of paths
            max_nodes: Maximum nodes to visit (safety)

        Returns:
            List of paths (empty if no paths found)

        Raises:
            No exceptions (returns empty list on failure)
        """
        # 1. Match source and target nodes
        source_nodes = self.node_matcher.match(source_selector)
        target_nodes = self.node_matcher.match(target_selector)

        if not source_nodes or not target_nodes:
            logger.debug("find_paths_empty", source_count=len(source_nodes), target_count=len(target_nodes))
            return []

        # 2. BFS traversal
        if direction == TraversalDirection.BACKWARD:
            # Backward: Start from TARGET, find SOURCE
            source_ids = {n.id for n in source_nodes}
            target_ids = {n.id for n in target_nodes}

            paths = self._bfs_backward(
                start_nodes=target_nodes,
                end_node_ids=source_ids,
                edge_selector=edge_selector,
                max_depth=max_depth,
                max_paths=max_paths,
                max_nodes=max_nodes,
                timeout_ms=timeout_ms,
                start_time=start_time,
            )
        else:
            # Forward: Start from SOURCE, find TARGET
            target_ids = {n.id for n in target_nodes}

            paths = self._bfs_forward(
                source_nodes, target_ids, edge_selector, max_depth, max_paths, max_nodes, timeout_ms, start_time
            )

        logger.info(
            "find_paths_complete",
            source_count=len(source_nodes),
            target_count=len(target_nodes),
            paths_found=len(paths),
            max_depth=max_depth,
        )

        return paths

    def _bfs_forward(
        self,
        start_nodes: list[UnifiedNode],
        end_node_ids: set[str],
        edge_selector: "EdgeSelector",
        max_depth: int,
        max_paths: int,
        max_nodes: int,
        timeout_ms: int | None = None,
        start_time: float | None = None,
    ) -> list[PathResult]:
        """
        Forward BFS traversal (RFC-021 Phase 1.5: Uses PathCollector)

        Queue item: (current_node, path_nodes, path_edges, depth)

        RFC-021 Phase 1.5:
        - Budget checking delegated to PathCollector
        - Cleaner separation of concerns
        """
        from codegraph_engine.code_foundation.domain.query.options import QueryOptions
        from codegraph_engine.code_foundation.infrastructure.query.path_collector import PathCollector

        # Create PathCollector with legacy parameters
        options = QueryOptions(
            max_depth=max_depth,
            max_paths=max_paths,
            max_nodes=max_nodes,
            timeout_ms=timeout_ms or 30000,  # Default 30s
        )
        collector = PathCollector(options)

        visited_global = set()  # Global visited (for cycle detection)
        queue = deque()

        # Initialize queue
        for start_node in start_nodes:
            queue.append((start_node, [start_node], [], 0))
            visited_global.add(start_node.id)
            collector.increment_visited()

        # CRITICAL FIX: Remove overlap (prevents 0-length paths)
        start_node_ids = {n.id for n in start_nodes}
        actual_end_ids = end_node_ids - start_node_ids
        # Special case: if all targets were removed, keep original (Q.Var(None) >> Q.Var(None))
        if not actual_end_ids:
            actual_end_ids = end_node_ids

        while queue:
            # Check budget
            should_stop, stop_reason = collector.should_stop()
            if should_stop:
                logger.debug("traversal_stopped", reason=stop_reason.value, collector=str(collector))
                break

            current_node, path_nodes, path_edges, depth = queue.popleft()

            # Check if reached target (depth > 0 for Q.Var(None) >> Q.Var(None))
            if current_node.id in actual_end_ids and (actual_end_ids != end_node_ids or depth > 0):
                from codegraph_engine.code_foundation.domain.query.results import PathResult

                collector.add_path(PathResult(nodes=path_nodes, edges=path_edges))
                continue  # Found target, don't expand further

            # Check depth limit
            if depth >= max_depth:
                continue

            # Get outgoing edges
            edges = self.edge_resolver.resolve(current_node.id, edge_selector, backward=False)

            # Expand to neighbors
            for edge in edges:
                next_node = self.graph.get_node(edge.to_node)
                if not next_node:
                    continue

                # RFC-021 Day 1: Skip unreachable nodes
                if self._is_unreachable_node(next_node.id):
                    logger.debug("skipped_unreachable_node", node_id=next_node.id)
                    continue

                # Prevent revisiting in THIS path (cycle detection)
                if next_node.id in {n.id for n in path_nodes}:
                    continue

                # Track globally visited
                if next_node.id not in visited_global:
                    visited_global.add(next_node.id)
                    collector.increment_visited()

                # Create new path
                new_path_nodes = path_nodes + [next_node]
                new_path_edges = path_edges + [edge]

                queue.append((next_node, new_path_nodes, new_path_edges, depth + 1))

        # Return collected paths (legacy return type)
        return collector.paths

    def _bfs_backward(
        self,
        start_nodes: list[UnifiedNode],
        end_node_ids: set[str],
        edge_selector: "EdgeSelector",
        max_depth: int,
        max_paths: int,
        max_nodes: int,
        timeout_ms: int | None = None,
        start_time: float | None = None,
    ) -> list[PathResult]:
        """
        Backward BFS traversal (RFC-021 Phase 1.5: Uses PathCollector)

        Similar to _bfs_forward but traverses backward edges.
        """
        from codegraph_engine.code_foundation.domain.query.options import QueryOptions
        from codegraph_engine.code_foundation.infrastructure.query.path_collector import PathCollector

        # Create PathCollector
        options = QueryOptions(
            max_depth=max_depth,
            max_paths=max_paths,
            max_nodes=max_nodes,
            timeout_ms=timeout_ms or 30000,
        )
        collector = PathCollector(options)

        visited_global = set()
        queue = deque()

        # Initialize queue
        for start_node in start_nodes:
            queue.append((start_node, [start_node], [], 0))
            visited_global.add(start_node.id)
            collector.increment_visited()

        # Remove overlap
        start_node_ids = {n.id for n in start_nodes}
        actual_end_ids = end_node_ids - start_node_ids
        if not actual_end_ids:
            actual_end_ids = end_node_ids

        while queue:
            # Check budget
            should_stop, stop_reason = collector.should_stop()
            if should_stop:
                logger.debug("backward_traversal_stopped", reason=stop_reason.value)
                break

            current_node, path_nodes, path_edges, depth = queue.popleft()

            # Check if reached target
            if current_node.id in actual_end_ids and (actual_end_ids != end_node_ids or depth > 0):
                from codegraph_engine.code_foundation.domain.query.results import PathResult

                # Reverse path for backward traversal
                collector.add_path(PathResult(nodes=list(reversed(path_nodes)), edges=list(reversed(path_edges))))
                continue

            # Check depth limit
            if depth >= max_depth:
                continue

            # Get incoming edges (backward=True)
            edges = self.edge_resolver.resolve(current_node.id, edge_selector, backward=True)

            # Expand to predecessors
            for edge in edges:
                next_node = self.graph.get_node(edge.from_node)
                if not next_node:
                    continue

                # RFC-021 Day 1: Skip unreachable nodes
                if self._is_unreachable_node(next_node.id):
                    logger.debug("skipped_unreachable_node_backward", node_id=next_node.id)
                    continue

                # Cycle detection
                if next_node.id in {n.id for n in path_nodes}:
                    continue

                # Track visited
                if next_node.id not in visited_global:
                    visited_global.add(next_node.id)
                    collector.increment_visited()

                # Create new path
                new_path_nodes = path_nodes + [next_node]
                new_path_edges = path_edges + [edge]

                queue.append((next_node, new_path_nodes, new_path_edges, depth + 1))

        return collector.paths

    # ============================================================
    # RFC-021 Day 1: SCCP Baseline Integration
    # ============================================================

    def _ensure_sccp_loaded(self):
        """
        Ensure SCCP result is loaded (RFC-021 Day 1)

        Lazy loading strategy:
            - Load on first use (not at __init__ time)
            - SCCP runs in QueryEngine.execute_flow()
            - TraversalEngine reads from ir_doc.meta

        Thread Safety:
            Not thread-safe (called from find_paths which is protected by QueryEngine._lock)

        Performance:
            - First call: O(1) dict lookup
            - Subsequent calls: O(1) flag check
        """
        if self._sccp_loaded:
            return

        try:
            ir_doc = self.graph.ir_doc
            if hasattr(ir_doc, "meta") and "constant_propagation" in ir_doc.meta:
                self._sccp_result = ir_doc.meta["constant_propagation"]
                logger.debug(
                    "sccp_result_loaded",
                    unreachable_blocks=len(self._sccp_result.unreachable_blocks),
                    constants_found=self._sccp_result.constants_found,
                )
            self._sccp_loaded = True
        except Exception as e:
            logger.warning("sccp_result_load_failed", error=str(e))
            self._sccp_result = None
            self._sccp_loaded = True  # Mark as attempted

    def _is_unreachable_node(self, node_id: str) -> bool:
        """
        Check if node is in unreachable block (RFC-021 Day 1)

        Args:
            node_id: Node ID to check

        Returns:
            True if node is in unreachable block (should skip)
            False if node is reachable or block_id unavailable

        Performance:
            O(1) set lookup

        Safety:
            - Lazy loads SCCP result on first use
            - Checks SCCP result existence
            - Validates node.block_id is not None (critical!)
            - Handles AttributeError gracefully
            - Safe for non-CFG nodes (e.g., global variables)

        Edge Cases:
            - SCCP not run → False (safe default)
            - Node not found → False
            - Node without block_id → False (non-CFG node)
            - block_id is None → False (explicit check)
        """
        # Lazy load SCCP result
        self._ensure_sccp_loaded()

        if not self._sccp_result:
            return False

        node = self.graph.get_node(node_id)
        if not node:
            return False

        # Critical: block_id can be None for non-CFG nodes
        # (e.g., global variables, module-level constants)
        # Node stores block_id in attrs dict
        block_id = node.attrs.get("block_id", None)
        if block_id is None:
            return False

        # Type safety: unreachable_blocks is set[str]
        return block_id in self._sccp_result.unreachable_blocks
