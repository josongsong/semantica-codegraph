"""
DefaultExecutionStrategy - L11급 SOTA

Default query execution strategy (wraps existing QueryExecutor).

Responsibilities:
- Execute queries using existing infrastructure
- Provide cost estimation
- Serve as baseline for other strategies

SOLID:
- S: Query execution only
- O: Extensible via subclassing
- L: Implements QueryExecutionStrategy
- I: Focused interface
- D: Depends on Port abstraction
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.strategies import ExecutionMode

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import PathQuery
    from codegraph_engine.code_foundation.domain.query.results import PathSet, VerificationResult
    from codegraph_engine.code_foundation.infrastructure.query.graph_index import UnifiedGraphIndex
    from codegraph_engine.code_foundation.infrastructure.query.query_executor import QueryExecutor

logger = get_logger(__name__)


class DefaultExecutionStrategy:
    """
    Default execution strategy

    Wraps existing QueryExecutor for backward compatibility.

    Characteristics:
    - Depth-first-like traversal
    - Eager evaluation
    - Standard caching

    Performance:
    - Good for most queries
    - May be suboptimal for very deep or very wide queries

    Thread Safety:
        Stateless. Safe for concurrent use if executor is thread-safe.

    Example:
        strategy = DefaultExecutionStrategy(executor)
        result = strategy.execute_any_path(query)
    """

    def __init__(self, executor: "QueryExecutor"):
        """
        Initialize strategy

        Args:
            executor: Query executor to wrap
        """
        self._executor = executor
        logger.debug("default_execution_strategy_initialized")

    def execute_any_path(self, query: "PathQuery") -> "PathSet":
        """
        Execute existential query

        Args:
            query: Path query

        Returns:
            PathSet with found paths
        """
        return self._executor.execute_any_path(query)

    def execute_all_paths(self, query: "PathQuery") -> "VerificationResult":
        """
        Execute universal query

        Args:
            query: Path query

        Returns:
            VerificationResult
        """
        return self._executor.execute_all_paths(query)

    def estimate_cost(self, query: "PathQuery") -> float:
        """
        Estimate execution cost

        Cost factors:
        - Number of selectors (steps)
        - Depth limit
        - Edge types

        Returns:
            Estimated cost (arbitrary units, lower is better)

        Formula:
            cost = num_selectors * depth * edge_complexity

        Example:
            Query with 3 selectors, depth 5, simple edges:
            cost = 3 * 5 * 1 = 15
        """
        num_selectors = len(query.path) if hasattr(query, "path") else 1
        depth = query.depth if hasattr(query, "depth") and query.depth else 10

        # Edge type complexity (simple heuristic)
        edge_complexity = 1.0
        if hasattr(query, "via_edge") and query.via_edge:
            # DFG/CFG edges are cheaper than Call/Ref
            edge_type = str(query.via_edge.edge_type)
            if "call" in edge_type.lower() or "ref" in edge_type.lower():
                edge_complexity = 2.0

        cost = float(num_selectors * depth * edge_complexity)
        return cost

    def get_mode(self) -> ExecutionMode:
        """
        Get execution mode

        Returns:
            DEPTH_FIRST (default behavior)
        """
        return ExecutionMode.DEPTH_FIRST


class CostBasedExecutionStrategy:
    """
    Cost-based execution strategy

    Selects query plan based on estimated costs.

    Optimizations:
    - Index selection (semantic vs traversal)
    - Operation reordering
    - Cache-aware planning

    Example:
        strategy = CostBasedExecutionStrategy(executor, graph_index)
        result = strategy.execute_any_path(query)
    """

    def __init__(self, executor: "QueryExecutor", graph_index: "UnifiedGraphIndex"):
        """
        Initialize cost-based strategy

        Args:
            executor: Query executor
            graph_index: Graph index (for statistics)
        """
        self._executor = executor
        self._graph_index = graph_index
        logger.debug("cost_based_execution_strategy_initialized")

    def execute_any_path(self, query: "PathQuery") -> "PathSet":
        """
        Execute with cost-based optimization

        Optimizations:
        1. Choose semantic index if available
        2. Reorder steps for minimal cost
        3. Use cache hints

        Args:
            query: Path query

        Returns:
            PathSet
        """
        # TODO: Add actual cost-based optimization
        # For now, delegate to default executor
        return self._executor.execute_any_path(query)

    def execute_all_paths(self, query: "PathQuery") -> "VerificationResult":
        """Execute universal query with cost optimization"""
        return self._executor.execute_all_paths(query)

    def estimate_cost(self, query: "PathQuery") -> float:
        """
        Estimate cost with graph statistics

        Uses actual graph stats for better estimation.

        Returns:
            Estimated cost
        """
        stats = self._graph_index.get_stats()

        num_selectors = len(query.path) if hasattr(query, "path") else 1
        depth = query.depth if hasattr(query, "depth") and query.depth else 10

        # Factor in graph size
        total_nodes = stats.get("total_nodes", 1000)
        total_edges = stats.get("total_edges", 5000)

        # Cost increases with graph size
        size_factor = (total_nodes + total_edges) / 1000.0

        cost = num_selectors * depth * size_factor
        return cost

    def get_mode(self) -> ExecutionMode:
        """Get execution mode"""
        return ExecutionMode.COST_BASED


__all__ = ["DefaultExecutionStrategy", "CostBasedExecutionStrategy"]
