"""
QueryPlan IR - Canonical Form for Query Execution

RFC-052: MCP Service Layer Architecture
All queries must be normalized to QueryPlan before execution.

Design Principles:
- Immutable (frozen dataclass)
- Hashable (for caching)
- Rewritable (can be optimized)
- Canonical (same logical query → same plan)

Rules:
- No string QueryDSL direct execution
- All execution paths go through QueryPlan
- Plan hash is stable across restarts
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlanKind(str, Enum):
    """QueryPlan types"""

    SLICE = "slice"  # Program slicing
    DATAFLOW = "dataflow"  # Source → Sink reachability
    TAINT_PROOF = "taint_proof"  # Taint analysis with policy
    CALL_CHAIN = "call_chain"  # Function A → Function B
    DATA_DEPENDENCY = "data_dependency"  # Variable dependency
    IMPACT_ANALYSIS = "impact_analysis"  # Change impact
    TYPE_INFERENCE = "type_inference"  # Type at program point
    PRIMITIVE = "primitive"  # Simple queries (get_callers, get_definition, etc.)


class SliceDirection(str, Enum):
    """Program slicing direction"""

    BACKWARD = "backward"
    FORWARD = "forward"
    BOTH = "both"


class TraversalStrategy(str, Enum):
    """Graph traversal strategy"""

    BFS = "bfs"
    DFS = "dfs"
    BIDIRECTIONAL = "bidirectional"


@dataclass(frozen=True)
class QueryPattern:
    """
    Query pattern (source/sink/anchor).

    Normalized representation:
    - Symbol name (e.g., "request.GET")
    - File + line (e.g., "auth.py:42")
    - Node ID (e.g., "node_12345")
    """

    pattern: str
    pattern_type: str = "symbol"  # symbol | file_line | node_id
    scope: str | None = None  # Optional scope restriction

    def __hash__(self) -> int:
        return hash((self.pattern, self.pattern_type, self.scope))


@dataclass(frozen=True)
class Budget:
    """
    Execution budget constraints.

    Prevents runaway queries.
    """

    max_nodes: int = 1000
    max_edges: int = 5000
    max_paths: int = 100
    max_depth: int = 10
    timeout_ms: int = 30000  # 30 seconds

    def __hash__(self) -> int:
        return hash((self.max_nodes, self.max_edges, self.max_paths, self.max_depth, self.timeout_ms))

    @classmethod
    def default(cls) -> Budget:
        """Default budget for normal queries (from config if available)"""
        try:
            # Try to get from config (Infrastructure dependency)
            # Domain models should not depend on config, so we provide sensible defaults
            # Config can override via factory functions in Infrastructure layer
            pass
        except Exception:
            pass

        return cls()

    @classmethod
    def light(cls) -> Budget:
        """Light budget for quick queries"""
        return cls(
            max_nodes=100,
            max_edges=500,
            max_paths=10,
            max_depth=5,
            timeout_ms=5000,
        )

    @classmethod
    def heavy(cls) -> Budget:
        """Heavy budget for deep analysis"""
        return cls(
            max_nodes=10000,
            max_edges=50000,
            max_paths=500,
            max_depth=20,
            timeout_ms=120000,
        )

    @classmethod
    def from_config(cls, profile: str = "default") -> Budget:
        """
        Create budget from config (Infrastructure layer helper).

        Note: This is a convenience method that breaks pure Domain isolation.
        For strict Clean Architecture, use BudgetFactory in Infrastructure layer.

        Args:
            profile: "light" | "default" | "heavy"
        """
        if profile == "light":
            return cls.light()
        elif profile == "heavy":
            return cls.heavy()
        else:
            return cls.default()


@dataclass(frozen=True)
class QueryPlan:
    """
    Canonical Query Execution Plan.

    All queries are normalized to this form before execution.

    Immutable + Hashable for caching.
    """

    kind: PlanKind
    patterns: tuple[QueryPattern, ...]  # Source, sink, anchor, etc.
    budget: Budget = field(default_factory=Budget.default)

    # Optional filters
    file_scope: str | None = None  # Restrict to specific file
    function_scope: str | None = None  # Restrict to specific function
    edge_types: tuple[str, ...] | None = None  # CFG, DFG, CALL, etc.

    # Slicing-specific
    slice_direction: SliceDirection | None = None

    # Taint-specific
    policy_id: str | None = None

    # Traversal
    traversal_strategy: TraversalStrategy = TraversalStrategy.BFS

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate plan after creation"""
        if not self.patterns:
            raise ValueError("QueryPlan must have at least one pattern")

        if self.kind == PlanKind.SLICE and not self.slice_direction:
            # Default to backward slicing
            object.__setattr__(self, "slice_direction", SliceDirection.BACKWARD)

    def compute_hash(self) -> str:
        """
        Compute stable hash of the plan.

        Used for:
        - Caching
        - Duplicate detection
        - Cost estimation reuse

        Hash is stable across process restarts.
        """
        # Canonical representation (sorted, deterministic)
        canonical = {
            "kind": self.kind.value,
            "patterns": [
                {"pattern": p.pattern, "type": p.pattern_type, "scope": p.scope}
                for p in sorted(self.patterns, key=lambda x: x.pattern)
            ],
            "budget": {
                "max_nodes": self.budget.max_nodes,
                "max_edges": self.budget.max_edges,
                "max_paths": self.budget.max_paths,
                "max_depth": self.budget.max_depth,
                "timeout_ms": self.budget.timeout_ms,
            },
            "file_scope": self.file_scope,
            "function_scope": self.function_scope,
            "edge_types": sorted(self.edge_types) if self.edge_types else None,
            "slice_direction": self.slice_direction.value if self.slice_direction else None,
            "policy_id": self.policy_id,
            "traversal_strategy": self.traversal_strategy.value,
        }

        # Deterministic JSON (sorted keys)
        json_str = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def with_budget(self, budget: Budget) -> QueryPlan:
        """Create new plan with different budget"""
        return QueryPlan(
            kind=self.kind,
            patterns=self.patterns,
            budget=budget,
            file_scope=self.file_scope,
            function_scope=self.function_scope,
            edge_types=self.edge_types,
            slice_direction=self.slice_direction,
            policy_id=self.policy_id,
            traversal_strategy=self.traversal_strategy,
            metadata=self.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (for storage/transport)"""
        return {
            "kind": self.kind.value,
            "patterns": [{"pattern": p.pattern, "type": p.pattern_type, "scope": p.scope} for p in self.patterns],
            "budget": {
                "max_nodes": self.budget.max_nodes,
                "max_edges": self.budget.max_edges,
                "max_paths": self.budget.max_paths,
                "max_depth": self.budget.max_depth,
                "timeout_ms": self.budget.timeout_ms,
            },
            "file_scope": self.file_scope,
            "function_scope": self.function_scope,
            "edge_types": list(self.edge_types) if self.edge_types else None,
            "slice_direction": self.slice_direction.value if self.slice_direction else None,
            "policy_id": self.policy_id,
            "traversal_strategy": self.traversal_strategy.value,
            "metadata": self.metadata,
            "plan_hash": self.compute_hash(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryPlan:
        """Deserialize from dict"""
        patterns = tuple(
            QueryPattern(
                pattern=p["pattern"],
                pattern_type=p["type"],
                scope=p.get("scope"),
            )
            for p in data["patterns"]
        )

        budget_data = data["budget"]
        budget = Budget(
            max_nodes=budget_data["max_nodes"],
            max_edges=budget_data["max_edges"],
            max_paths=budget_data["max_paths"],
            max_depth=budget_data["max_depth"],
            timeout_ms=budget_data["timeout_ms"],
        )

        return cls(
            kind=PlanKind(data["kind"]),
            patterns=patterns,
            budget=budget,
            file_scope=data.get("file_scope"),
            function_scope=data.get("function_scope"),
            edge_types=tuple(data["edge_types"]) if data.get("edge_types") else None,
            slice_direction=SliceDirection(data["slice_direction"]) if data.get("slice_direction") else None,
            policy_id=data.get("policy_id"),
            traversal_strategy=TraversalStrategy(data["traversal_strategy"]),
            metadata=data.get("metadata", {}),
        )


# ============================================================
# Factory Functions (Convenience)
# ============================================================


def slice_plan(
    anchor: str,
    direction: SliceDirection = SliceDirection.BACKWARD,
    budget: Budget | None = None,
    file_scope: str | None = None,
) -> QueryPlan:
    """Create a program slicing plan"""
    return QueryPlan(
        kind=PlanKind.SLICE,
        patterns=(QueryPattern(pattern=anchor),),
        budget=budget or Budget.default(),
        slice_direction=direction,
        file_scope=file_scope,
    )


def dataflow_plan(
    source: str,
    sink: str,
    budget: Budget | None = None,
    file_scope: str | None = None,
) -> QueryPlan:
    """Create a dataflow analysis plan"""
    return QueryPlan(
        kind=PlanKind.DATAFLOW,
        patterns=(
            QueryPattern(pattern=source, pattern_type="symbol"),
            QueryPattern(pattern=sink, pattern_type="symbol"),
        ),
        budget=budget or Budget.default(),
        file_scope=file_scope,
        edge_types=("DFG",),
    )


def taint_proof_plan(
    source: str,
    sink: str,
    policy_id: str,
    budget: Budget | None = None,
) -> QueryPlan:
    """Create a taint proof plan"""
    return QueryPlan(
        kind=PlanKind.TAINT_PROOF,
        patterns=(
            QueryPattern(pattern=source),
            QueryPattern(pattern=sink),
        ),
        budget=budget or Budget.default(),
        policy_id=policy_id,
        edge_types=("DFG",),
    )
