"""
QueryPlan Executor

RFC-052: MCP Service Layer Architecture
Executes QueryPlan through QueryEngine.

Design Principles:
- QueryPlan → QueryDSL translation
- Budget enforcement
- Timeout handling
- Partial result support (future)

Execution Flow:
    QueryPlan → validate → translate to QueryDSL → QueryEngine.execute()

No string QueryDSL bypass - all queries go through QueryPlan.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.query_plan import PlanKind, QueryPlan

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import PathQuery
    from codegraph_engine.code_foundation.domain.query.results import PathSet
    from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

logger = get_logger(__name__)


class ExecutionStatus(str, Enum):
    """Execution status"""

    SUCCESS = "success"
    PARTIAL = "partial"  # Budget exceeded, partial results
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """
    Result of QueryPlan execution.

    Includes:
    - Status (success, partial, timeout, error)
    - Data (PathSet or other)
    - Metadata (timing, budget usage)
    - Cursor (for partial results)
    """

    status: ExecutionStatus
    data: Any = None
    error: str | None = None

    # Metadata
    execution_time_ms: float = 0.0
    nodes_visited: int = 0
    edges_traversed: int = 0
    paths_found: int = 0

    # Partial result support
    cursor: str | None = None  # For resuming partial results
    truncated_reason: str | None = None

    # Budget usage
    budget_exceeded: bool = False
    budget_used: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict"""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "nodes_visited": self.nodes_visited,
            "edges_traversed": self.edges_traversed,
            "paths_found": self.paths_found,
            "cursor": self.cursor,
            "truncated_reason": self.truncated_reason,
            "budget_exceeded": self.budget_exceeded,
            "budget_used": self.budget_used,
        }


class QueryPlanExecutor:
    """
    Executes QueryPlan through QueryEngine (with cache).

    Single execution path - no bypass.

    SOTA Features:
    - Result caching (snapshot + plan_hash)
    - Trace context integration
    - Evidence reuse on cache hit
    """

    def __init__(self, query_engine: "QueryEngine", cache: "QueryPlanCache | None" = None):
        """
        Initialize executor.

        Args:
            query_engine: QueryEngine instance
            cache: Optional QueryPlanCache for result caching
        """
        self.query_engine = query_engine
        self.cache = cache

    async def execute(self, plan: QueryPlan, snapshot_id: str | None = None) -> ExecutionResult:
        """
        Execute QueryPlan (with cache support).

        Args:
            plan: QueryPlan to execute
            snapshot_id: Snapshot ID for cache key (optional)

        Returns:
            ExecutionResult with status, data, metadata
        """
        from codegraph_engine.code_foundation.infrastructure.monitoring import get_trace_context

        start_time = time.time()
        trace = get_trace_context()

        try:
            # Validate plan
            self._validate_plan(plan)

            # Check cache if snapshot_id provided
            if self.cache and snapshot_id:
                cached = self.cache.get(snapshot_id, plan)
                if cached:
                    logger.info(
                        "query_plan_cache_hit",
                        plan_hash=plan.compute_hash(),
                        snapshot_id=snapshot_id,
                        trace_id=trace.trace_id,
                    )
                    return ExecutionResult(
                        status=ExecutionStatus.SUCCESS,
                        data=cached.result,
                        execution_time_ms=(time.time() - start_time) * 1000,
                        paths_found=len(cached.result.paths) if hasattr(cached.result, "paths") else 0,
                    )

            # Cache miss - execute query
            logger.info(
                "query_plan_executing",
                plan_hash=plan.compute_hash(),
                plan_kind=plan.kind.value,
                trace_id=trace.trace_id,
            )

            # Translate QueryPlan → QueryDSL
            query = self._translate_to_query_dsl(plan)

            # Execute through QueryEngine
            result = self._execute_query(query, plan)

            # Extract metadata
            execution_time_ms = (time.time() - start_time) * 1000

            # Check budget
            budget_exceeded = self._check_budget_exceeded(result, plan)

            exec_result = ExecutionResult(
                status=ExecutionStatus.PARTIAL if budget_exceeded else ExecutionStatus.SUCCESS,
                data=result,
                execution_time_ms=execution_time_ms,
                paths_found=len(result.paths) if hasattr(result, "paths") else 0,
                budget_exceeded=budget_exceeded,
                truncated_reason="Budget exceeded" if budget_exceeded else None,
            )

            # Cache result if successful and snapshot_id provided
            if self.cache and snapshot_id and exec_result.status == ExecutionStatus.SUCCESS:
                self.cache.put(snapshot_id, plan, result)
                logger.debug("query_plan_cached", plan_hash=plan.compute_hash())

            return exec_result

        except TimeoutError as e:
            logger.warning("query_plan_timeout", error=str(e), trace_id=trace.trace_id)
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except ValueError as e:
            # Validation error
            logger.error("query_plan_validation_failed", error=str(e), trace_id=trace.trace_id)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=f"Validation failed: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(
                "query_plan_execution_failed",
                error=str(e),
                plan_hash=plan.compute_hash(),
                trace_id=trace.trace_id,
                exc_info=True,
            )
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _validate_plan(self, plan: QueryPlan) -> None:
        """
        Validate QueryPlan before execution.

        Raises:
            ValueError: If plan is invalid
        """
        # Check patterns
        if not plan.patterns:
            raise ValueError("QueryPlan must have at least one pattern")

        # Check kind-specific requirements
        if plan.kind == PlanKind.SLICE:
            if len(plan.patterns) != 1:
                raise ValueError("Slice plan must have exactly one anchor pattern")

        if plan.kind in (PlanKind.DATAFLOW, PlanKind.TAINT_PROOF):
            if len(plan.patterns) != 2:
                raise ValueError(f"{plan.kind} plan must have exactly two patterns (source, sink)")

        # Budget sanity check
        if plan.budget.max_depth < 1:
            raise ValueError("Budget max_depth must be >= 1")

        if plan.budget.max_nodes < 1:
            raise ValueError("Budget max_nodes must be >= 1")

    def _translate_to_query_dsl(self, plan: QueryPlan) -> "PathQuery":
        """
        Translate QueryPlan to QueryDSL.

        Args:
            plan: QueryPlan

        Returns:
            PathQuery (Q, E expression)
        """
        from codegraph_engine.code_foundation.domain.query.factories import E, Q

        # Map plan kind to QueryDSL
        if plan.kind == PlanKind.SLICE:
            # Slicing: anchor node (single pattern)
            anchor = plan.patterns[0].pattern
            # Note: Slicing is handled by SlicerAdapter, not QueryDSL
            # For now, return a simple path query
            return Q.Func(anchor).depth(plan.budget.max_depth)

        if plan.kind == PlanKind.DATAFLOW:
            # Dataflow: source >> sink via DFG
            source = plan.patterns[0].pattern
            sink = plan.patterns[1].pattern
            return (Q.Var(source) >> Q.Var(sink)).via(E.DFG).depth(plan.budget.max_depth)

        if plan.kind == PlanKind.TAINT_PROOF:
            # Taint: source >> sink via DFG with policy
            source = plan.patterns[0].pattern
            sink = plan.patterns[1].pattern
            return (Q.Source(source) >> Q.Sink(sink)).via(E.DFG).depth(plan.budget.max_depth)

        if plan.kind == PlanKind.CALL_CHAIN:
            # Call chain: func A >> func B via CALL
            from_func = plan.patterns[0].pattern
            to_func = plan.patterns[1].pattern
            return (Q.Func(from_func) >> Q.Func(to_func)).via(E.CALL).depth(plan.budget.max_depth)

        if plan.kind == PlanKind.DATA_DEPENDENCY:
            # Data dependency: var A >> var B via DFG
            from_var = plan.patterns[0].pattern
            to_var = plan.patterns[1].pattern
            return (Q.Var(from_var) >> Q.Var(to_var)).via(E.DFG).depth(plan.budget.max_depth)

        raise NotImplementedError(f"QueryPlan kind {plan.kind} not yet supported")

    def _execute_query(self, query: "PathQuery", plan: QueryPlan) -> "PathSet":
        """
        Execute query through QueryEngine.

        Args:
            query: QueryDSL query
            plan: Original QueryPlan (for budget)

        Returns:
            PathSet result
        """
        # Execute with timeout
        # Note: QueryEngine doesn't have native timeout support yet
        # For now, we rely on budget constraints

        result = self.query_engine.execute_any_path(query)

        # Truncate results if exceeds budget
        if len(result.paths) > plan.budget.max_paths:
            result.paths = result.paths[: plan.budget.max_paths]

        return result

    def _check_budget_exceeded(self, result: Any, plan: QueryPlan) -> bool:
        """
        Check if budget was exceeded.

        Args:
            result: Query result
            plan: QueryPlan with budget

        Returns:
            True if budget exceeded
        """
        if not hasattr(result, "paths"):
            return False

        # Check path count
        if len(result.paths) >= plan.budget.max_paths:
            return True

        # Note: We don't have node/edge counts from QueryEngine yet
        # Future: Add instrumentation to QueryEngine

        return False
