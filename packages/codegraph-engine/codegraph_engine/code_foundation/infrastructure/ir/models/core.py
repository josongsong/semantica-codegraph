"""
IR Core Models - Structural Layer

Node, Edge, Span - language-agnostic code structure.

NOTE (RFC-031): NodeKind/EdgeKind are now defined in kinds.py for unification.
This file re-exports them for backward compatibility.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# RFC-031: Import canonical kinds from unified module
from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import (
    EdgeKind,
    NodeKind,
)

# ============================================================
# Enums (IR-specific, not in kinds.py)
# ============================================================


class InterproceduralEdgeKind(str, Enum):
    """Inter-procedural data flow edge types"""

    ARG_TO_PARAM = "arg_to_param"
    RETURN_TO_CALLSITE = "return_to_callsite"
    COLLECTION_STORE = "collection_store"
    COLLECTION_LOAD = "collection_load"


class ScopeKind(str, Enum):
    """Scope types for AST traversal"""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    LAMBDA = "lambda"
    COMPREHENSION = "comprehension"


class VariableKind(str, Enum):
    """Variable kinds in data flow analysis"""

    PARAMETER = "parameter"
    LOCAL = "local"
    CAPTURED = "captured"
    FIELD = "field"
    GLOBAL = "global"


class FindingSeverity(str, Enum):
    """Severity levels for security findings"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# NOTE: NodeKind and EdgeKind are imported from kinds.py (RFC-031)
# They are re-exported via __all__ for backward compatibility


# ============================================================
# Common Structures
# ============================================================


@dataclass(frozen=True, slots=True)
class Span:
    """
    Source code location (immutable).

    SOTA Enhancement: frozen=True for memory interning.
    - Hashable (required for WeakValueDictionary)
    - Immutable (safe for concurrent access)
    - Memory efficient (__slots__)
    """

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def overlaps(self, other: "Span") -> bool:
        """Check if this span overlaps with another"""
        return not (self.end_line < other.start_line or other.end_line < self.start_line)

    def contains_line(self, line: int) -> bool:
        """Check if span contains the given line"""
        return self.start_line <= line <= self.end_line


@dataclass(slots=True)
class ControlFlowSummary:
    """Control flow summary (without full CFG)"""

    cyclomatic_complexity: int = 1
    has_loop: bool = False
    has_try: bool = False
    branch_count: int = 0


# ============================================================
# Core Entities
# ============================================================


@dataclass(slots=True)
class Node:
    """
    IR Node - language-agnostic code structure/symbol representation.

    All relationships (parent/children, calls, references) are expressed
    in Edge layer, not in Node.
    """

    # [Required] Identity
    id: str  # logical_id (human-readable, e.g., "method:semantica:src/...")
    kind: NodeKind
    fqn: str  # Fully Qualified Name

    # [Required] Location
    file_path: str  # Relative to repo root
    span: Span
    language: str  # python, typescript, javascript, go, java, ...

    # [Optional] Identity (tracking)
    stable_id: str | None = None  # Hash-based stable ID for file movement tracking
    content_hash: str | None = None  # sha256 of node's code text

    # [Optional] Structure
    name: str | None = None  # Symbol name (null for File/Block)
    module_path: str | None = None  # For import/name resolution
    parent_id: str | None = None  # Convenience anchor (also in CONTAINS Edge)
    body_span: Span | None = None  # Body only (excluding signature)

    # [Optional] Metadata
    docstring: str | None = None  # For LLM summary/search
    role: str | None = None  # controller, service, repo, dto, entity, util, test, ...
    is_test_file: bool | None = None

    # [Optional] Type/Signature references
    signature_id: str | None = None  # For Function/Method/Lambda
    declared_type_id: str | None = None  # For Variable/Field

    # [Optional] Control flow
    control_flow_summary: ControlFlowSummary | None = None

    # [Optional] Ordering (RFC-RUST-ENGINE Phase 1)
    # Tie-breaker for deterministic total ordering
    # Ensures same input → same ordering → same hash
    local_seq: int = 0

    # [Optional] Language-specific extensions
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    """
    IR Edge - first-class relationship entity.

    All relationships are stored here, not in Node.
    """

    # [Required] Identity
    id: str  # e.g., "edge:call:plan→_search_vector@1"
    kind: EdgeKind
    source_id: str  # Caller, Referrer, Owner, etc.
    target_id: str  # Callee, Referenced, Imported, etc.

    # [Optional] Location
    span: Span | None = None  # Where this relationship appears in code

    # [Optional] Ordering (RFC-RUST-ENGINE Phase 1)
    # Tie-breaker for deterministic total ordering
    local_seq: int = 0

    # [Optional] Metadata
    attrs: dict[str, Any] = field(default_factory=dict)
