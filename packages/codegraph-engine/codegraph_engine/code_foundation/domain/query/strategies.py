"""
Query Execution Strategies - L11급 SOTA

Strategy Pattern for different query execution approaches.

Strategies:
1. DepthFirstStrategy: Deep traversal first
2. BreadthFirstStrategy: Wide exploration first
3. CostBasedStrategy: Choose based on estimated cost
4. LazyEvaluationStrategy: Evaluate only when needed

SOLID:
- S: Each strategy handles one execution approach
- O: Easy to add new strategies
- L: All implement QueryExecutionStrategy protocol
- I: Focused interface
- D: Depends on abstraction (Port)

Design Pattern: Strategy Pattern
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import PathQuery
    from codegraph_engine.code_foundation.domain.query.results import PathSet, VerificationResult


class ExecutionMode(StrEnum):
    """
    Query execution modes

    Values:
        DEPTH_FIRST: Explore depth before breadth
        BREADTH_FIRST: Explore breadth before depth
        COST_BASED: Choose based on cost estimation
        LAZY: Evaluate only when needed
    """

    DEPTH_FIRST = "depth_first"
    BREADTH_FIRST = "breadth_first"
    COST_BASED = "cost_based"
    LAZY = "lazy"


class QueryExecutionStrategy(Protocol):
    """
    Strategy interface for query execution

    Hexagonal Architecture: Port for different execution strategies.

    Implementations:
    - DepthFirstStrategy: Deep first
    - BreadthFirstStrategy: Wide first
    - CostBasedStrategy: Cost-aware
    - LazyEvaluationStrategy: On-demand
    """

    def execute_any_path(self, query: "PathQuery") -> "PathSet":
        """
        Execute existential query with this strategy

        Args:
            query: Path query to execute

        Returns:
            PathSet with found paths
        """
        ...

    def execute_all_paths(self, query: "PathQuery") -> "VerificationResult":
        """
        Execute universal query with this strategy

        Args:
            query: Path query to execute

        Returns:
            VerificationResult
        """
        ...

    def estimate_cost(self, query: "PathQuery") -> float:
        """
        Estimate execution cost

        Args:
            query: Path query

        Returns:
            Estimated cost (lower is better)

        Cost factors:
            - Number of nodes to visit
            - Number of edges to traverse
            - Memory usage
            - Expected result size
        """
        ...

    def get_mode(self) -> ExecutionMode:
        """
        Get execution mode

        Returns:
            ExecutionMode enum
        """
        ...


class StrategySelector:
    """
    Selects best strategy for a query

    Responsibilities:
    - Analyze query characteristics
    - Estimate costs
    - Select optimal strategy

    Example:
        selector = StrategySelector(strategies)
        strategy = selector.select(query)
        result = strategy.execute_any_path(query)
    """

    def __init__(self, strategies: list[QueryExecutionStrategy]):
        """
        Initialize selector

        Args:
            strategies: Available strategies
        """
        self._strategies = {s.get_mode(): s for s in strategies}

    def select(self, query: "PathQuery", mode: ExecutionMode | None = None) -> QueryExecutionStrategy:
        """
        Select best strategy

        Args:
            query: Path query
            mode: Explicit mode (optional)

        Returns:
            Selected strategy

        Selection Logic:
            1. If mode specified, use that
            2. If query.depth > 5, use depth-first
            3. If query.depth <= 2, use breadth-first
            4. Otherwise, use cost-based
        """
        # Explicit mode
        if mode:
            strategy = self._strategies.get(mode)
            if strategy:
                return strategy

        # Auto-select based on query characteristics
        if hasattr(query, "depth"):
            depth = query.depth
            if depth and depth > 5:
                # Deep query → depth-first
                return self._strategies.get(ExecutionMode.DEPTH_FIRST, self._default_strategy())
            elif depth and depth <= 2:
                # Shallow query → breadth-first
                return self._strategies.get(ExecutionMode.BREADTH_FIRST, self._default_strategy())

        # Fallback: cost-based
        return self._strategies.get(ExecutionMode.COST_BASED, self._default_strategy())

    def _default_strategy(self) -> QueryExecutionStrategy:
        """Get default strategy (first available)"""
        if self._strategies:
            return next(iter(self._strategies.values()))
        raise RuntimeError("No strategies available")

    def get_available_modes(self) -> list[ExecutionMode]:
        """Get list of available execution modes"""
        return list(self._strategies.keys())

    def add_strategy(self, strategy: QueryExecutionStrategy) -> None:
        """
        Add new strategy

        Args:
            strategy: Strategy to add
        """
        self._strategies[strategy.get_mode()] = strategy

    def remove_strategy(self, mode: ExecutionMode) -> None:
        """
        Remove strategy

        Args:
            mode: Mode to remove
        """
        self._strategies.pop(mode, None)


__all__ = [
    "ExecutionMode",
    "QueryExecutionStrategy",
    "StrategySelector",
]
