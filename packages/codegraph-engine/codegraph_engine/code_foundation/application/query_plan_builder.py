"""
QueryPlan Builder

RFC-052: MCP Service Layer Architecture
Converts raw input (dict, arguments) to canonical QueryPlan.

Design Principles:
- All queries must be normalized to QueryPlan
- No string QueryDSL direct execution
- Validation before execution
- Cost estimation before execution

Builder Pattern:
- Fluent API for easy construction
- Immutable result (QueryPlan)
- Validation at build time
"""

from typing import Any

from codegraph_engine.code_foundation.domain.query.query_plan import (
    Budget,
    PlanKind,
    QueryPattern,
    QueryPlan,
    SliceDirection,
    TraversalStrategy,
)


class QueryPlanBuilder:
    """
    Builder for QueryPlan.

    Fluent API for constructing QueryPlan from various inputs.

    Usage:
        builder = QueryPlanBuilder()
        plan = (builder
            .slice()
            .anchor("request.GET")
            .backward()
            .with_budget(Budget.light())
            .build())
    """

    def __init__(self):
        """Initialize builder"""
        self._kind: PlanKind | None = None
        self._patterns: list[QueryPattern] = []
        self._budget: Budget = Budget.default()
        self._file_scope: str | None = None
        self._function_scope: str | None = None
        self._edge_types: list[str] | None = None
        self._slice_direction: SliceDirection | None = None
        self._policy_id: str | None = None
        self._traversal_strategy: TraversalStrategy = TraversalStrategy.BFS
        self._metadata: dict[str, Any] = {}

    # ============================================================
    # Plan Kind Setters
    # ============================================================

    def slice(self) -> "QueryPlanBuilder":
        """Set plan kind to SLICE"""
        self._kind = PlanKind.SLICE
        self._slice_direction = SliceDirection.BACKWARD  # Default
        return self

    def dataflow(self) -> "QueryPlanBuilder":
        """Set plan kind to DATAFLOW"""
        self._kind = PlanKind.DATAFLOW
        self._edge_types = ["DFG"]
        return self

    def taint_proof(self) -> "QueryPlanBuilder":
        """Set plan kind to TAINT_PROOF"""
        self._kind = PlanKind.TAINT_PROOF
        self._edge_types = ["DFG"]
        return self

    def call_chain(self) -> "QueryPlanBuilder":
        """Set plan kind to CALL_CHAIN"""
        self._kind = PlanKind.CALL_CHAIN
        self._edge_types = ["CALL"]
        return self

    def data_dependency(self) -> "QueryPlanBuilder":
        """Set plan kind to DATA_DEPENDENCY"""
        self._kind = PlanKind.DATA_DEPENDENCY
        self._edge_types = ["DFG"]
        return self

    # ============================================================
    # Pattern Setters
    # ============================================================

    def anchor(self, pattern: str, pattern_type: str = "symbol") -> "QueryPlanBuilder":
        """Add anchor pattern (for slicing)"""
        self._patterns.append(QueryPattern(pattern=pattern, pattern_type=pattern_type))
        return self

    def source(self, pattern: str, pattern_type: str = "symbol") -> "QueryPlanBuilder":
        """Add source pattern"""
        self._patterns.append(QueryPattern(pattern=pattern, pattern_type=pattern_type))
        return self

    def sink(self, pattern: str, pattern_type: str = "symbol") -> "QueryPlanBuilder":
        """Add sink pattern"""
        self._patterns.append(QueryPattern(pattern=pattern, pattern_type=pattern_type))
        return self

    def from_func(self, pattern: str) -> "QueryPlanBuilder":
        """Add from_function pattern (for call chain)"""
        self._patterns.append(QueryPattern(pattern=pattern, pattern_type="symbol"))
        return self

    def to_func(self, pattern: str) -> "QueryPlanBuilder":
        """Add to_function pattern (for call chain)"""
        self._patterns.append(QueryPattern(pattern=pattern, pattern_type="symbol"))
        return self

    # ============================================================
    # Direction Setters (for slicing)
    # ============================================================

    def backward(self) -> "QueryPlanBuilder":
        """Set slice direction to BACKWARD"""
        self._slice_direction = SliceDirection.BACKWARD
        return self

    def forward(self) -> "QueryPlanBuilder":
        """Set slice direction to FORWARD"""
        self._slice_direction = SliceDirection.FORWARD
        return self

    def both_directions(self) -> "QueryPlanBuilder":
        """Set slice direction to BOTH"""
        self._slice_direction = SliceDirection.BOTH
        return self

    # ============================================================
    # Scope Setters
    # ============================================================

    def in_file(self, file_path: str) -> "QueryPlanBuilder":
        """Restrict to specific file"""
        self._file_scope = file_path
        return self

    def in_function(self, function_name: str) -> "QueryPlanBuilder":
        """Restrict to specific function"""
        self._function_scope = function_name
        return self

    # ============================================================
    # Budget Setter
    # ============================================================

    def with_budget(self, budget: Budget) -> "QueryPlanBuilder":
        """Set custom budget"""
        self._budget = budget
        return self

    def light_budget(self) -> "QueryPlanBuilder":
        """Use light budget (quick queries)"""
        self._budget = Budget.light()
        return self

    def heavy_budget(self) -> "QueryPlanBuilder":
        """Use heavy budget (deep analysis)"""
        self._budget = Budget.heavy()
        return self

    # ============================================================
    # Policy Setter (for taint)
    # ============================================================

    def with_policy(self, policy_id: str) -> "QueryPlanBuilder":
        """Set taint policy"""
        self._policy_id = policy_id
        return self

    # ============================================================
    # Metadata
    # ============================================================

    def with_metadata(self, key: str, value: Any) -> "QueryPlanBuilder":
        """Add metadata"""
        self._metadata[key] = value
        return self

    # ============================================================
    # Build
    # ============================================================

    def build(self) -> QueryPlan:
        """
        Build QueryPlan.

        Returns:
            Immutable QueryPlan

        Raises:
            ValueError: If validation fails
        """
        # Validate
        if not self._kind:
            raise ValueError("Plan kind must be set")

        if not self._patterns:
            raise ValueError("At least one pattern is required")

        # Build
        return QueryPlan(
            kind=self._kind,
            patterns=tuple(self._patterns),
            budget=self._budget,
            file_scope=self._file_scope,
            function_scope=self._function_scope,
            edge_types=tuple(self._edge_types) if self._edge_types else None,
            slice_direction=self._slice_direction,
            policy_id=self._policy_id,
            traversal_strategy=self._traversal_strategy,
            metadata=self._metadata,
        )

    # ============================================================
    # Factory Methods (from raw dict)
    # ============================================================

    @classmethod
    def from_slice_args(cls, arguments: dict[str, Any]) -> QueryPlan:
        """
        Build slice plan from MCP arguments.

        Args:
            arguments: {"anchor": str, "direction": str, "max_depth": int, ...}
        """
        builder = cls().slice()

        anchor = arguments.get("anchor")
        if not anchor:
            raise ValueError("anchor is required for slice")
        builder.anchor(anchor)

        direction = arguments.get("direction", "backward")
        if direction == "backward":
            builder.backward()
        elif direction == "forward":
            builder.forward()
        elif direction == "both":
            builder.both_directions()

        # Budget
        max_depth = arguments.get("max_depth", 5)
        max_lines = arguments.get("max_lines", 100)
        builder.with_budget(
            Budget(
                max_depth=max_depth,
                max_nodes=max_lines * 10,  # Estimate
                max_paths=100,
            )
        )

        # Scope
        if file_scope := arguments.get("file_scope"):
            builder.in_file(file_scope)

        return builder.build()

    @classmethod
    def from_dataflow_args(cls, arguments: dict[str, Any]) -> QueryPlan:
        """
        Build dataflow plan from MCP arguments.

        Args:
            arguments: {"source": str, "sink": str, "file_path": str, ...}
        """
        builder = cls().dataflow()

        source = arguments.get("source")
        sink = arguments.get("sink")
        if not source or not sink:
            raise ValueError("source and sink are required for dataflow")

        builder.source(source).sink(sink)

        # Budget
        max_depth = arguments.get("max_depth", 10)
        builder.with_budget(Budget(max_depth=max_depth))

        # Scope
        if file_path := arguments.get("file_path"):
            builder.in_file(file_path)

        # Policy
        if policy := arguments.get("policy"):
            builder = cls().taint_proof()  # Upgrade to taint proof
            builder.source(source).sink(sink).with_policy(policy)
            if file_path:
                builder.in_file(file_path)
            return builder.with_budget(Budget(max_depth=max_depth)).build()

        return builder.build()

    @classmethod
    def from_taint_proof_args(cls, arguments: dict[str, Any]) -> QueryPlan:
        """
        Build taint proof plan from MCP arguments.

        Args:
            arguments: {"source": str, "sink": str, "policy": str, ...}
        """
        builder = cls().taint_proof()

        source = arguments.get("source")
        sink = arguments.get("sink")
        policy = arguments.get("policy")

        if not source or not sink or not policy:
            raise ValueError("source, sink, and policy are required for taint_proof")

        builder.source(source).sink(sink).with_policy(policy)

        # Budget
        max_depth = arguments.get("max_depth", 10)
        builder.with_budget(Budget(max_depth=max_depth))

        return builder.build()
