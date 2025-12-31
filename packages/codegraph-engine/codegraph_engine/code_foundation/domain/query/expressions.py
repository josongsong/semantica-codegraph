"""
Query Expressions - Pure Domain

FlowExpr, PathQuery - defines query structure without IR dependencies.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .types import ConstraintMode, ConstraintType, ContextStrategy, SensitivityMode, TraversalDirection

if TYPE_CHECKING:
    from .results import PathSet, VerificationResult
    from .selectors import EdgeSelector, NodeSelector
    from .types import PathPredicate  # NEW: 2025-12


@dataclass
class FlowExpr:
    """
    Flow expression (structure definition)

    Created by operators: >>, >, <<
    NOT executable - must be converted to PathQuery with constraints.

    Type Transition:
        FlowExpr (immutable)
            ↓ (.where, .within, .excluding, etc)
        PathQuery (executable)

    Attributes:
        source: Source node selector
        target: Target node selector
        direction: Traversal direction (forward/backward)
        edge_type: Edge type selector (None = E.ALL)
        depth: (min, max) hop count
    """

    source: "NodeSelector"
    target: "NodeSelector"
    direction: TraversalDirection = TraversalDirection.FORWARD
    edge_type: "EdgeSelector | None" = None
    depth_range: tuple[int, int] = (1, 10)

    def via(self, edge: "EdgeSelector") -> "FlowExpr":
        """
        Edge type specification

        Returns new FlowExpr (immutable).

        Example:
            (source >> sink).via(E.DFG)  # Data-flow only
        """
        return FlowExpr(
            source=self.source,
            target=self.target,
            direction=self.direction,
            edge_type=edge,
            depth_range=self.depth_range,
        )

    def depth(self, max_hops: int, min_hops: int = 1) -> "FlowExpr":
        """
        Depth constraint

        Args:
            max_hops: Maximum hop count
            min_hops: Minimum hop count

        Example:
            (source >> sink).depth(5)  # Max 5 hops
        """
        return FlowExpr(
            source=self.source,
            target=self.target,
            direction=self.direction,
            edge_type=self.edge_type,
            depth_range=(min_hops, max_hops),
        )

    # ============================================================
    # Auto-promotion to PathQuery (first constraint)
    # ============================================================

    def where(self, predicate: "PathPredicate") -> "PathQuery":
        """
        Predicate filter (auto-promotes to PathQuery)

        Args:
            predicate: Path predicate (PathResult → bool)
                      Type-safe with PathPredicate protocol

        Example:
            (source >> sink).where(lambda p: len(p) > 5)
        """
        return PathQuery.from_flow_expr(self).where(predicate)

    def within(self, scope: "NodeSelector", mode: ConstraintMode = ConstraintMode.PRUNE) -> "PathQuery":
        """
        Scope constraint (auto-promotes to PathQuery)

        Args:
            scope: Scope selector
            mode: ConstraintMode.PRUNE (fast) or ConstraintMode.FILTER (exhaustive)

        Example:
            (source >> sink).within(Q.Module("core.*"))
        """
        return PathQuery.from_flow_expr(self).within(scope, mode)

    def excluding(self, nodes: "NodeSelector") -> "PathQuery":
        """
        Exclusion filter (auto-promotes to PathQuery)

        Args:
            nodes: Nodes to exclude from paths

        Example:
            (source >> sink).excluding(Q.Call("sanitize"))
        """
        return PathQuery.from_flow_expr(self).excluding(nodes)

    def cleansed_by(self, sanitizer: "NodeSelector") -> "PathQuery":
        """
        Sanitizer constraint (auto-promotes to PathQuery) - NEW: 2025-12

        Args:
            sanitizer: Sanitizer selector

        Example:
            (source >> sink).cleansed_by(Q.Call("escape_sql"))
        """
        return PathQuery.from_flow_expr(self).cleansed_by(sanitizer)

    def context_sensitive(self, k: int = 1, strategy: ContextStrategy = ContextStrategy.SUMMARY) -> "PathQuery":
        """
        Context sensitivity (auto-promotes to PathQuery)

        Args:
            k: Callsite depth (1 = direct caller)
            strategy: ContextStrategy.SUMMARY (fast) or ContextStrategy.CLONING (precise)

        Example:
            (source >> sink).context_sensitive(k=1)
        """
        return PathQuery.from_flow_expr(self).context_sensitive(k, strategy)

    def alias_sensitive(self, mode: SensitivityMode = SensitivityMode.MUST) -> "PathQuery":
        """
        Alias sensitivity (auto-promotes to PathQuery)

        Args:
            mode: SensitivityMode.MUST (conservative) or SensitivityMode.MAY (aggressive)

        Example:
            (source >> sink).alias_sensitive(mode=SensitivityMode.MUST)
        """
        return PathQuery.from_flow_expr(self).alias_sensitive(mode)

    def limit_paths(self, n: int) -> "PathQuery":
        """
        Path limit (auto-promotes to PathQuery)

        Example:
            (source >> sink).limit_paths(20)
        """
        return PathQuery.from_flow_expr(self).limit_paths(n)

    def limit_nodes(self, n: int) -> "PathQuery":
        """
        Node limit (auto-promotes to PathQuery)

        Example:
            (source >> sink).limit_nodes(1000)
        """
        return PathQuery.from_flow_expr(self).limit_nodes(n)

    def timeout(self, ms: int) -> "PathQuery":
        """
        Timeout (auto-promotes to PathQuery)

        Example:
            (source >> sink).timeout(ms=5000)
        """
        return PathQuery.from_flow_expr(self).timeout(ms)

    def __repr__(self) -> str:
        """Human-readable representation"""
        op = ">>" if self.direction == TraversalDirection.FORWARD else "<<"
        edge_str = f".via({self.edge_type})" if self.edge_type else ""
        return f"({self.source} {op} {self.target}){edge_str}"


@dataclass
class PathQuery:
    """
    Executable query (with constraints)

    Created by FlowExpr + constraint methods.
    Can execute: .any_path(), .all_paths()

    Type Transition:
        FlowExpr
            ↓ (first constraint)
        PathQuery (executable)
            ↓ (.any_path() or .all_paths())
        PathSet | VerificationResult

    Attributes:
        flow: Base flow expression
        constraints: List of constraints
        sensitivity: Sensitivity settings
        safety: Safety limits
    """

    flow: FlowExpr
    constraints: list = field(default_factory=list)
    sensitivity: dict = field(default_factory=dict)
    safety: dict = field(default_factory=dict)

    @classmethod
    def from_flow_expr(cls, flow: FlowExpr) -> "PathQuery":
        """Create PathQuery from FlowExpr (promotion)"""
        return cls(flow=flow)

    # ============================================================
    # Constraint methods (return self for chaining)
    # ============================================================

    def where(self, predicate: "PathPredicate") -> "PathQuery":
        """
        Predicate filter

        Args:
            predicate: Path predicate (PathResult → bool)
                      Type-safe with PathPredicate protocol

        Example:
            query.where(lambda p: len(p) > 5)
            query.where(lambda p: p.has_node(Q.Var("x")))
        """
        self.constraints.append((ConstraintType.WHERE, predicate))
        return self

    def within(self, scope: "NodeSelector", mode: ConstraintMode = ConstraintMode.PRUNE) -> "PathQuery":
        """
        Scope constraint

        Args:
            scope: Scope selector
            mode: ConstraintMode.PRUNE (search space) or ConstraintMode.FILTER (post-filter)

        Example:
            query.within(Q.Module("core.*"), mode=ConstraintMode.PRUNE)
        """
        self.constraints.append((ConstraintType.WITHIN, {"scope": scope, "mode": mode}))
        return self

    def excluding(self, nodes: "NodeSelector") -> "PathQuery":
        """
        Exclusion filter

        Args:
            nodes: Nodes to exclude

        Example:
            query.excluding(Q.Call("sanitize"))
        """
        self.constraints.append((ConstraintType.EXCLUDING, nodes))
        return self

    def cleansed_by(self, sanitizer: "NodeSelector") -> "PathQuery":
        """
        Sanitizer constraint (taint removal check) - NEW: 2025-12

        Different from .excluding():
        - excluding: 노드 포함 시 경로 제외 (path filter)
        - cleansed_by: Sanitizer 통과한 경로만 (taint removal)

        Args:
            sanitizer: Sanitizer node selector

        Example:
            query.cleansed_by(Q.Call("escape_sql"))
            # → escape_sql()을 거친 경로만 (safe paths)

            # vs excluding
            query.excluding(Q.Call("helper"))
            # → helper를 안 거친 경로만 (general filter)
        """
        self.constraints.append((ConstraintType.CLEANSED_BY, sanitizer))
        return self

    def context_sensitive(self, k: int = 1, strategy: ContextStrategy = ContextStrategy.SUMMARY) -> "PathQuery":
        """
        Inter-procedural context sensitivity

        Args:
            k: Callsite depth
            strategy: ContextStrategy.SUMMARY (fast) or ContextStrategy.CLONING (precise)

        Example:
            query.context_sensitive(k=1, strategy=ContextStrategy.SUMMARY)
        """
        self.sensitivity["context"] = {"k": k, "strategy": strategy}
        return self

    def alias_sensitive(self, mode: SensitivityMode = SensitivityMode.MUST) -> "PathQuery":
        """
        Alias sensitivity (pointer analysis)

        Args:
            mode: SensitivityMode.MUST (conservative) or SensitivityMode.MAY (aggressive)

        Example:
            query.alias_sensitive(mode=SensitivityMode.MUST)
        """
        self.sensitivity["alias"] = {"mode": mode}
        return self

    def limit_paths(self, n: int) -> "PathQuery":
        """
        Limit number of paths

        Example:
            query.limit_paths(20)
        """
        self.safety["max_paths"] = n
        return self

    def limit_nodes(self, n: int) -> "PathQuery":
        """
        Limit nodes visited

        Example:
            query.limit_nodes(1000)
        """
        self.safety["max_nodes"] = n
        return self

    def timeout(self, ms: int) -> "PathQuery":
        """
        Set timeout

        Example:
            query.timeout(ms=5000)
        """
        self.safety["timeout_ms"] = ms
        return self

    # ============================================================
    # Execution methods (delegates to infrastructure)
    # ============================================================

    def any_path(self) -> "PathSet":
        """
        Execute existential query (∃)

        Returns first N paths that satisfy constraints.
        Use for: Vulnerability detection, example extraction.

        Note: Must be executed through QueryEngine.
        """
        from ..query.exceptions import InvalidQueryError

        raise InvalidQueryError(
            "PathQuery.any_path() must be executed through QueryEngine",
            "Use: QueryEngine(ir_doc).execute(query) or pass query to engine",
        )

    def all_paths(self) -> "VerificationResult":
        """
        Execute universal query (∀)

        Checks if ALL paths satisfy constraints.
        Use for: Compliance verification, integrity checks.

        Note: Must be executed through QueryEngine.
        """
        from ..query.exceptions import InvalidQueryError

        raise InvalidQueryError(
            "PathQuery.all_paths() must be executed through QueryEngine",
            "Use: QueryEngine(ir_doc).execute(query) or pass query to engine",
        )

    def explain(self) -> str:
        """
        Query explanation (AI-friendly)

        Returns human-readable description of query.
        """
        parts = [
            f"Flow: {self.flow.source} → {self.flow.target}",
            f"Direction: {self.flow.direction}",
            f"Edge Type: {self.flow.edge_type or 'ALL'}",
            f"Depth: {self.flow.depth_range[0]}-{self.flow.depth_range[1]} hops",
        ]

        if self.constraints:
            parts.append(f"Constraints: {len(self.constraints)}")
            for constraint_type, constraint_value in self.constraints:
                parts.append(f"  - {constraint_type}: {constraint_value}")

        if self.sensitivity:
            parts.append("Sensitivity:")
            for key, value in self.sensitivity.items():
                parts.append(f"  - {key}: {value}")

        if self.safety:
            parts.append("Safety Limits:")
            for key, value in self.safety.items():
                parts.append(f"  - {key}: {value}")

        return "\n".join(parts)

    def __repr__(self) -> str:
        """Human-readable representation"""
        constraints_str = f" + {len(self.constraints)} constraints" if self.constraints else ""
        return f"PathQuery({self.flow}){constraints_str}"
