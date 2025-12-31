"""
Query Type Definitions - Pure Domain

Type-safe enums and type aliases to eliminate magic strings.

RFC-031 Compliance:
- NodeKind: Re-exported from canonical ir/models/kinds.py
- SelectorType: Query-specific selector logic (not NodeKind)
- EdgeType: Query-specific edge abstraction (DFG/CFG/CALL)
"""

from enum import StrEnum
from typing import NewType

# ============================================================
# Type Aliases (for better type checking)
# ============================================================

NodeId = NewType("NodeId", str)
"""Unique node identifier"""

EdgeId = NewType("EdgeId", str)
"""Unique edge identifier"""


# ============================================================
# Canonical NodeKind (RFC-031)
# Re-export from single source of truth
# ============================================================

from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import (
    EdgeKind,
    NodeKind,
)

# ============================================================
# Protocol Types (NEW: 2025-12)
# ============================================================

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .results import PathResult, UnifiedNode


class PathPredicate(Protocol):
    """
    Path predicate function protocol

    Used in PathQuery.where() for type-safe predicate filtering.

    Example:
        def my_predicate(path: PathResult) -> bool:
            return len(path.nodes) > 5

        query.where(my_predicate)
    """

    def __call__(self, path: "PathResult") -> bool: ...


class NodePredicate(Protocol):
    """
    Node predicate function protocol

    Used for node-level filtering.

    Example:
        def is_tainted(node: UnifiedNode) -> bool:
            return node.attrs.get("is_tainted", False)
    """

    def __call__(self, node: "UnifiedNode") -> bool: ...


class EdgeType(StrEnum):
    """
    Edge types in unified graph

    - DFG: Data-flow edges (variable → variable)
    - CFG: Control-flow edges (block → block)
    - CALL: Call-graph edges (function → function)
    - BINDS: Variable → Template slot binding (RFC-051)
    - RENDERS: Function → Template document (RFC-051)
    - ESCAPES: Sanitizer → Template slot (RFC-051)
    - ALL: Union of all edge types
    - UNION: Composite selector (E.DFG | E.CALL)
    """

    DFG = "dfg"
    CFG = "cfg"
    CALL = "call"
    BINDS = "binds"  # RFC-051: Variable → Template slot
    RENDERS = "renders"  # RFC-051: Function → Template doc
    ESCAPES = "escapes"  # RFC-051: Sanitizer → Slot
    ALL = "all"
    UNION = "union"  # Composite selector


class EdgeTypeSet(StrEnum):
    """
    Edge type combinations for policy configuration.

    Used by PolicyCompiler.default_edges.
    """

    DFG = "dfg"
    CFG = "cfg"
    CALL = "call"
    DFG_CALL = "dfg|call"  # Default for taint analysis
    ALL = "all"


class SelectorType(StrEnum):
    """
    Node selector types

    Used by NodeSelector to specify what kind of nodes to match.
    """

    VAR = "var"
    FUNC = "func"
    CALL = "call"
    BLOCK = "block"
    MODULE = "module"
    CLASS = "class"
    FIELD = "field"
    EXPR = "expr"  # Expression (NEW: 2025-12)
    SOURCE = "source"  # Taint source
    SINK = "sink"  # Taint sink
    ALIAS = "alias"  # Alias of variable (NEW: 2025-12)
    TEMPLATE_SLOT = "template_slot"  # Template slot (RFC-051)
    ANY = "any"  # Wildcard
    UNION = "union"  # OR of selectors
    INTERSECTION = "intersection"  # AND of selectors


class TraversalDirection(StrEnum):
    """
    Traversal direction for path queries

    - FORWARD: Source → Target (default)
    - BACKWARD: Target → Source (reverse)
    """

    FORWARD = "forward"
    BACKWARD = "backward"


class BlockKind(StrEnum):
    """
    Control flow block kinds

    Maps to CFG block types.
    """

    ENTRY = "entry"
    EXIT = "exit"
    NORMAL = "normal"
    BRANCH = "branch"
    LOOP = "loop"


class ConstraintType(StrEnum):
    """
    Path constraint types

    Used by PathQuery constraints.
    """

    WHERE = "where"  # Predicate filter
    WITHIN = "within"  # Scope filter
    EXCLUDING = "excluding"  # Exclusion filter
    CLEANSED_BY = "cleansed_by"  # Sanitizer constraint (NEW: 2025-12)


class ConstraintMode(StrEnum):
    """
    Constraint application modes

    - PRUNE: Apply during traversal (fast)
    - FILTER: Apply after traversal (exhaustive)
    """

    PRUNE = "prune"
    FILTER = "filter"


class SensitivityMode(StrEnum):
    """
    Analysis sensitivity modes

    - MUST: Conservative (only certain aliases)
    - MAY: Aggressive (includes possible aliases)
    """

    MUST = "must"
    MAY = "may"


class ContextStrategy(StrEnum):
    """
    Context-sensitivity strategies

    - SUMMARY: Function summary (fast)
    - CLONING: Context cloning (precise)
    """

    SUMMARY = "summary"
    CLONING = "cloning"


class TaintMode(StrEnum):
    """
    Taint analysis modes for UnifiedAnalyzer.

    - BASIC: Simple taint propagation (fast)
    - PATH_SENSITIVE: CFG-aware analysis (precise)
    - FIELD_SENSITIVE: Object field tracking
    - FULL: Deprecated - falls back to PATH_SENSITIVE

    Usage:
        analyzer = UnifiedAnalyzer(taint_mode=TaintMode.PATH_SENSITIVE)
    """

    BASIC = "basic"
    PATH_SENSITIVE = "path_sensitive"
    FIELD_SENSITIVE = "field_sensitive"
    FULL = "full"  # Deprecated → PATH_SENSITIVE

    @classmethod
    def from_string(cls, value: str) -> "TaintMode":
        """
        Case-insensitive conversion from string.

        Args:
            value: Mode string (e.g., "basic", "PATH_SENSITIVE")

        Returns:
            TaintMode enum

        Raises:
            ValueError: If invalid mode
        """
        normalized = value.lower().strip()
        for member in cls:
            if member.value == normalized:
                return member
        valid = [m.value for m in cls]
        raise ValueError(f"Invalid TaintMode: '{value}'. Valid: {valid}")


class QueryMode(StrEnum):
    """
    Query execution modes for QueryEngine.execute_flow().

    - REALTIME: <100ms, IDE autocomplete (depth=3, paths=10)
    - PR: <5s, CI/CD checks (depth=10, paths=100)
    - FULL: Minutes, complete analysis (k-CFA, alias)

    Usage:
        result = engine.execute_flow(expr, mode=QueryMode.PR)
    """

    REALTIME = "realtime"
    PR = "pr"
    FULL = "full"


class AnalyzerMode(StrEnum):
    """
    Analyzer Pipeline modes for DI Container.

    - REALTIME: 증분, <500ms (SCCP만)
    - PR: <5s (SCCP + Taint lite)
    - AUDIT: 분 단위 (SCCP + Taint full + Null + Z3)
    - COST: <1s (SCCP + Cost Analysis, RFC-028)

    Usage:
        pipeline = container.create_analyzer_pipeline(ir_doc, mode=AnalyzerMode.PR)
    """

    REALTIME = "realtime"
    PR = "pr"
    AUDIT = "audit"
    COST = "cost"
