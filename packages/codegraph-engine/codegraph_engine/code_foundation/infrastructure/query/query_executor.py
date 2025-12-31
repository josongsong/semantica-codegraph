"""
QueryExecutor

Executes PathQuery and returns results.

Architecture:
- Infrastructure layer (uses TraversalEngine)
- Applies constraints (.where, .within, .excluding)
- Applies safety limits (timeout, path/node limits)
- Returns PathSet or VerificationResult

Contract:
- Always returns valid result (never raises except on timeout)
- Respects all safety limits
- Applies constraints in order
"""

import time
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.exceptions import NodeLimitExceededError, QueryTimeoutError
from codegraph_engine.code_foundation.domain.query.results import (
    PathResult,
    PathSet,
    TruncationReason,
    VerificationResult,
)
from codegraph_engine.code_foundation.domain.query.types import ConstraintType, EdgeType, TraversalDirection

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import PathQuery
    from codegraph_engine.code_foundation.domain.query.selectors import EdgeSelector

    from .edge_resolver import EdgeResolver
    from .graph_index import UnifiedGraphIndex
    from .node_matcher import NodeMatcher
    from .traversal_engine import TraversalEngine

logger = get_logger(__name__)


class QueryExecutor:
    """
    Executes PathQuery

    Pipeline:
    1. Parse query (source, target, edge_type, direction)
    2. Traverse graph (TraversalEngine)
    3. Apply constraints (.where, .within, .excluding)
    4. Apply safety limits
    5. Return PathSet or VerificationResult
    """

    def __init__(
        self,
        graph: "UnifiedGraphIndex",
        node_matcher: "NodeMatcher",
        edge_resolver: "EdgeResolver",
        traversal: "TraversalEngine",
    ):
        """
        Initialize executor

        Args:
            graph: Unified graph index
            node_matcher: Node matcher
            edge_resolver: Edge resolver
            traversal: Traversal engine
        """
        self.graph = graph
        self.node_matcher = node_matcher
        self.edge_resolver = edge_resolver
        self.traversal = traversal

    def execute_any_path(self, query: "PathQuery") -> PathSet:
        """
        Execute existential query (∃)

        Returns first N paths that satisfy all constraints.

        Args:
            query: Path query (domain) or FlowExpr (auto-converted)

        Returns:
            PathSet with found paths

        Raises:
            QueryTimeoutError: If timeout exceeded
        """
        start_time = time.time()

        # Auto-convert FlowExpr to PathQuery
        from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr, PathQuery

        if isinstance(query, FlowExpr):
            query = PathQuery.from_flow_expr(query)

        # Extract parameters
        flow = query.flow
        source = flow.source
        target = flow.target
        edge_type = flow.edge_type or self._get_default_edge_selector()
        direction = flow.direction
        max_depth = flow.depth_range[1]

        # Safety limits
        timeout_ms = query.safety.get("timeout_ms", 30000)  # Default 30s
        max_paths = query.safety.get("max_paths", 100)
        max_nodes = query.safety.get("max_nodes", 10000)

        # ✅ NEW: Cardinality-based optimization (2025-12)
        # Automatic direction selection for performance
        optimized_direction = direction
        if direction == TraversalDirection.FORWARD:
            # Measure cardinality
            source_nodes = self.node_matcher.match(source)
            target_nodes = self.node_matcher.match(target)

            # Optimize if significant imbalance (>10x)
            if len(target_nodes) > 0 and len(source_nodes) > 0:
                ratio = len(source_nodes) / len(target_nodes)
                if ratio > 10:
                    optimized_direction = TraversalDirection.BACKWARD
                    logger.info(
                        "query_direction_optimized",
                        original=TraversalDirection.FORWARD.value,
                        optimized=TraversalDirection.BACKWARD.value,
                        source_count=len(source_nodes),
                        target_count=len(target_nodes),
                        speedup_estimate=f"{ratio:.1f}x",
                    )

        # Traverse (with timeout support)
        try:
            paths = self.traversal.find_paths(
                source_selector=source,
                target_selector=target,
                edge_selector=edge_type,
                direction=optimized_direction,  # ✅ Optimized
                max_depth=max_depth,
                max_paths=max_paths,
                max_nodes=max_nodes,
                timeout_ms=timeout_ms,
                start_time=start_time,
            )
        except QueryTimeoutError:
            # Timeout during traversal - return partial results
            logger.warning("query_timeout_during_traversal")
            return PathSet(paths=[], complete=False, truncation_reason=TruncationReason.TIMEOUT)
        except NodeLimitExceededError:
            # Node limit exceeded - return partial results
            logger.warning("node_limit_exceeded_during_traversal")
            return PathSet(paths=[], complete=False, truncation_reason=TruncationReason.NODE_LIMIT)

        # Apply constraints
        paths = self._apply_constraints(paths, query.constraints)

        # Determine truncation
        complete = len(paths) < max_paths
        truncation_reason = None
        if not complete:
            truncation_reason = TruncationReason.PATH_LIMIT

        # Check timeout after constraints
        elapsed_ms = (time.time() - start_time) * 1000
        if elapsed_ms > timeout_ms:
            truncation_reason = TruncationReason.TIMEOUT
            complete = False

        logger.info(
            "query_executed",
            paths_found=len(paths),
            complete=complete,
            truncation=truncation_reason.value if truncation_reason else None,
            elapsed_ms=int(elapsed_ms),
        )

        # RFC-021 Phase 1: Use new PathSet signature
        from codegraph_engine.code_foundation.domain.query.results import StopReason

        stop_reason = StopReason.COMPLETE
        if truncation_reason == TruncationReason.TIMEOUT:
            stop_reason = StopReason.TIMEOUT
        elif truncation_reason == TruncationReason.PATH_LIMIT:
            stop_reason = StopReason.MAX_PATHS
        elif truncation_reason == TruncationReason.NODE_LIMIT:
            stop_reason = StopReason.MAX_NODES

        return PathSet(
            paths=paths,
            stop_reason=stop_reason,
            elapsed_ms=int(elapsed_ms),
            nodes_visited=0,
            diagnostics=(),
        )

    def execute_all_paths(self, query: "PathQuery") -> VerificationResult:
        """
        Execute universal query (∀)

        Checks if ALL paths satisfy constraints.

        Args:
            query: Path query (domain) or FlowExpr (auto-converted)

        Returns:
            VerificationResult (ok=True if all paths satisfy, ok=False with violation otherwise)

        Note:
        - This is expensive (must explore all paths)
        - Use with caution on large graphs
        """
        # Auto-convert FlowExpr to PathQuery
        from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr, PathQuery

        if isinstance(query, FlowExpr):
            query = PathQuery.from_flow_expr(query)

        # Execute as any_path with high limits
        modified_query = query
        modified_query.safety["max_paths"] = 10000  # High limit
        modified_query.safety["max_nodes"] = 100000

        path_set = self.execute_any_path(modified_query)

        # If not complete, we can't verify ALL paths
        if not path_set.complete:
            # Found paths but couldn't explore all - treat as violation
            return VerificationResult(ok=False, violation_path=None)

        # All paths explored and satisfy constraints
        return VerificationResult(ok=True, violation_path=None)

    def _apply_constraints(
        self, paths: list[PathResult], constraints: list[tuple[ConstraintType, Any]]
    ) -> list[PathResult]:
        """
        Apply constraints to paths

        Constraints:
        - WHERE: Predicate filter
        - WITHIN: Scope filter
        - EXCLUDING: Exclusion filter (path filter)
        - CLEANSED_BY: Sanitizer filter (taint removal) ✅ NEW
        """
        for constraint_type, constraint_value in constraints:
            if constraint_type == ConstraintType.WHERE:
                # Predicate filter
                predicate = constraint_value
                paths = [p for p in paths if predicate(p)]
            elif constraint_type == ConstraintType.WITHIN:
                # Scope filter (NOT IMPLEMENTED - requires complex scope checking)
                logger.warning("within_constraint_not_implemented")
            elif constraint_type == ConstraintType.EXCLUDING:
                # Exclusion filter: 노드 포함 시 경로 제외
                excluding_selector = constraint_value
                excluding_nodes = self.node_matcher.match(excluding_selector)
                excluding_ids = {n.id for n in excluding_nodes}
                paths = [p for p in paths if not any(node.id in excluding_ids for node in p.nodes)]
            elif constraint_type == ConstraintType.CLEANSED_BY:
                # ✅ NEW: Sanitizer filter (taint removal check)
                # 경로에 sanitizer가 있는 것만 유지 (excluding의 반대)
                sanitizer_selector = constraint_value
                sanitizer_nodes = self.node_matcher.match(sanitizer_selector)
                sanitizer_ids = {n.id for n in sanitizer_nodes}
                paths = [p for p in paths if any(node.id in sanitizer_ids for node in p.nodes)]

        return paths

    def _get_default_edge_selector(self) -> "EdgeSelector":
        """Get default edge selector (E.ALL)"""
        from codegraph_engine.code_foundation.domain.query.selectors import EdgeSelector

        return EdgeSelector(edge_type=EdgeType.ALL)
