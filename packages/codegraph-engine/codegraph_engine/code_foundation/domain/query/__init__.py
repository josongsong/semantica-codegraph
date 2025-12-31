"""
Query DSL Domain Models

Pure business logic for CodeGraph Query Engine.
No external dependencies (IR-agnostic).

Public API:
- Q: NodeSelector factory
- E: EdgeSelector factory
- FlowExpr: Flow expression (>>, >, <<)
- PathQuery: Executable query with constraints
- PathResult, PathSet: Query results
"""

from .exceptions import InvalidQueryError, PathLimitExceededError, QueryTimeoutError
from .expressions import FlowExpr, PathQuery
from .factories import E, Q
from .options import PRESETS, QueryOptions, ScopeSpec
from .ports import CodeTraceProvider, EdgeResolverPort, GraphIndexPort, NodeMatcherPort, TraversalPort
from .results import (
    PathResult,
    PathSet,
    StopReason,
    TruncationReason,
    UncertainReason,
    UnifiedEdge,
    UnifiedNode,
    VerificationResult,
)
from .selectors import EdgeSelector, NodeSelector
from .strategies import ExecutionMode, QueryExecutionStrategy, StrategySelector
from .types import (
    BlockKind,
    ConstraintMode,
    ConstraintType,
    ContextStrategy,
    EdgeKind,  # RFC-031: Canonical from ir/models/kinds.py
    EdgeType,
    NodeKind,  # RFC-031: Canonical from ir/models/kinds.py
    SelectorType,
    SensitivityMode,
    TraversalDirection,
)

__all__ = [
    # Factories
    "Q",
    "E",
    # Expressions
    "FlowExpr",
    "PathQuery",
    # Selectors
    "NodeSelector",
    "EdgeSelector",
    # Options (RFC-021 Phase 1)
    "QueryOptions",
    "ScopeSpec",
    "PRESETS",
    # Results
    "PathResult",
    "PathSet",
    "VerificationResult",
    "UnifiedNode",
    "UnifiedEdge",
    "TruncationReason",  # Legacy
    "StopReason",  # RFC-021
    "UncertainReason",  # RFC-021
    # Types
    "NodeKind",  # RFC-031: Canonical
    "EdgeKind",  # RFC-031: Canonical
    "EdgeType",
    "SelectorType",
    "TraversalDirection",
    "BlockKind",
    "ConstraintType",
    "ConstraintMode",
    "SensitivityMode",
    "ContextStrategy",
    # Ports
    "GraphIndexPort",
    "NodeMatcherPort",
    "EdgeResolverPort",
    "TraversalPort",
    "CodeTraceProvider",
    # Strategies
    "ExecutionMode",
    "QueryExecutionStrategy",
    "StrategySelector",
    # Exceptions
    "InvalidQueryError",
    "QueryTimeoutError",
    "PathLimitExceededError",
]
