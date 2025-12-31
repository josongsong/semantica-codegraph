"""
CompiledPolicy - Domain Value Object

Compiled policy representation for taint analysis.
Lives in Domain layer (not Infrastructure) to avoid circular dependencies.

Hexagonal Architecture:
- Domain Layer defines CompiledPolicy (this file)
- Infrastructure Layer creates CompiledPolicy via PolicyCompiler
- Domain Layer (TaintEngine) uses CompiledPolicy
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr


class CompiledPolicy:
    """
    Compiled policy (Value Object).

    Output of PolicyCompiler.

    Contains:
    - flow_query: FlowExpr for execution
    - constraints: Constraint dict for validation
    - metadata: Additional info

    Note:
        This is a Domain object, not Infrastructure.
        PolicyCompiler (Infrastructure) creates it,
        TaintEngine (Domain) consumes it.
    """

    def __init__(
        self,
        flow_query: "FlowExpr",
        constraints: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize CompiledPolicy.

        Args:
            flow_query: Compiled Q.DSL expression
            constraints: Constraint specifications
            metadata: Additional metadata
        """
        self.flow_query = flow_query
        self.constraints = constraints
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return f"CompiledPolicy(constraints={list(self.constraints.keys())})"
