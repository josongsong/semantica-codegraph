"""
Node & Edge Selectors - Pure Domain Models

Selectors are pure domain objects with no IR knowledge.
They define WHAT to select, not HOW to select.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .types import EdgeType, SelectorType, TraversalDirection

if TYPE_CHECKING:
    from .expressions import FlowExpr


@dataclass
class NodeSelector:
    """
    Node selector (pure domain)

    Defines criteria for selecting nodes in the graph.
    No IR knowledge - infrastructure layer handles matching.

    Attributes:
        selector_type: Type of selector (var, func, call, etc)
        name: Node name pattern
        pattern: Glob pattern for matching
        attrs: Additional selector attributes
    """

    selector_type: SelectorType
    name: str | None = None
    pattern: str | None = None
    context: str | None = None  # Call context for context-sensitive analysis (k=1)
    attrs: dict = field(default_factory=dict)

    def __rshift__(self, other: "NodeSelector") -> "FlowExpr":
        """
        >> operator: N-hop forward reachability

        Example:
            source >> sink  # Find all paths from source to sink
        """
        from .expressions import FlowExpr

        return FlowExpr(source=self, target=other, direction=TraversalDirection.FORWARD)

    def __gt__(self, other: "NodeSelector") -> "FlowExpr":
        """
        > operator: 1-hop adjacency

        Example:
            caller > callee  # Direct call relationship
        """
        from .expressions import FlowExpr

        return FlowExpr(source=self, target=other, direction=TraversalDirection.FORWARD, depth_range=(1, 1))

    def __lshift__(self, other: "NodeSelector") -> "FlowExpr":
        """
        << operator: N-hop backward reachability

        Syntax sugar for backward traversal.

        Example:
            sink << source  # Find paths: source → sink (backward search)

        CRITICAL: Normalized to forward when target is wildcard
        Q.Var(None) << Q.Var("x") → Q.Var(None) >> Q.Var("x") (same meaning)
        """
        from .expressions import FlowExpr

        # CRITICAL FIX: Normalize wildcard target with backward to forward
        # Q.Var(None) << Q.Var("x"): self=Q.Var(None), other=Q.Var("x")
        # Means "find all that flow TO x"
        # This is identical to Q.Var(None) >> Q.Var("x")
        if self.name is None and self.selector_type in (SelectorType.VAR, SelectorType.ANY):
            # Wildcard target (self) with backward → use forward instead
            return FlowExpr(source=self, target=other, direction=TraversalDirection.FORWARD)

        return FlowExpr(source=other, target=self, direction=TraversalDirection.BACKWARD)

    def __or__(self, other: "NodeSelector") -> "NodeSelector":
        """
        | operator: Union

        Example:
            Q.Var("x") | Q.Var("y")  # Match x OR y
        """
        return NodeSelector(selector_type=SelectorType.UNION, attrs={"operands": [self, other]})

    def __and__(self, other: "NodeSelector") -> "NodeSelector":
        """
        & operator: Intersection

        Example:
            Q.Var("x") & Q.Tainted()  # Match x AND tainted
        """
        return NodeSelector(selector_type=SelectorType.INTERSECTION, attrs={"operands": [self, other]})

    def within(self, scope: "NodeSelector") -> "NodeSelector":
        """
        Scope constraint (structural)

        Example:
            Q.Func("process").within(Q.Module("core.*"))
        """
        return NodeSelector(
            selector_type=self.selector_type,
            name=self.name,
            pattern=self.pattern,
            attrs={**self.attrs, "scope": scope},
        )

    def __repr__(self) -> str:
        """Human-readable representation"""
        if self.name:
            return f"Q.{self.selector_type.capitalize()}({self.name!r})"
        elif self.pattern:
            return f"Q.{self.selector_type.capitalize()}({self.pattern!r})"
        else:
            return f"Q.{self.selector_type.capitalize()}()"


@dataclass
class EdgeSelector:
    """
    Edge selector (pure domain)

    Defines criteria for selecting edges in the graph.

    Attributes:
        edge_type: Type of edge (dfg, cfg, call, all)
        is_backward: Backward traversal flag
        min_depth: Minimum depth
        max_depth: Maximum depth
        attrs: Additional edge attributes
    """

    edge_type: EdgeType  # EdgeType enum (UNION is now part of EdgeType)
    is_backward: bool = False
    min_depth: int = 1
    max_depth: int = 10
    attrs: dict = field(default_factory=dict)

    def backward(self) -> "EdgeSelector":
        """
        Backward traversal

        Reverses edge direction semantics:
        - DFG: Use → Definition
        - CFG: Successor → Predecessor
        - CALL: Callee → Caller

        Example:
            E.DFG.backward()  # Trace data flow backward
        """
        return EdgeSelector(
            edge_type=self.edge_type,
            is_backward=True,
            min_depth=self.min_depth,
            max_depth=self.max_depth,
            attrs=self.attrs.copy(),
        )

    def depth(self, max: int, min: int = 1) -> "EdgeSelector":
        """
        Depth constraint

        Args:
            max: Maximum hop count
            min: Minimum hop count (default: 1)

        Example:
            E.DFG.depth(5)  # Max 5 hops
            E.CFG.depth(1, 3)  # Between 1-3 hops
        """
        return EdgeSelector(
            edge_type=self.edge_type,
            is_backward=self.is_backward,
            min_depth=min,
            max_depth=max,
            attrs=self.attrs.copy(),
        )

    def __or__(self, other: "EdgeSelector") -> "EdgeSelector":
        """
        | operator: Union

        Example:
            E.DFG | E.CALL  # Data-flow OR call edges
        """
        return EdgeSelector(edge_type=EdgeType.UNION, attrs={"operands": [self, other]})

    def __repr__(self) -> str:
        """Human-readable representation"""
        backward_str = ".backward()" if self.is_backward else ""
        depth_str = f".depth({self.max_depth})" if self.max_depth != 10 else ""
        return f"E.{self.edge_type.upper()}{backward_str}{depth_str}"
