"""
IR Core Models - Structural Layer

Node, Edge, Span - language-agnostic code structure.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ============================================================
# Enums
# ============================================================


class NodeKind(str, Enum):
    """Node types (language-agnostic)"""

    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    INTERFACE = "Interface"
    FUNCTION = "Function"
    METHOD = "Method"
    LAMBDA = "Lambda"
    VARIABLE = "Variable"  # Local variable, parameter
    FIELD = "Field"  # Class/interface member
    IMPORT = "Import"
    EXPORT = "Export"
    BLOCK = "Block"
    CONDITION = "Condition"
    LOOP = "Loop"
    TRY_CATCH = "TryCatch"


class EdgeKind(str, Enum):
    """Edge types (relationship)"""

    # Structure/Definition
    CONTAINS = "CONTAINS"  # File→Class, Class→Method, etc.
    DEFINES = "DEFINES"  # Scope→Symbol

    # Call/Usage
    CALLS = "CALLS"  # Function/method call
    READS = "READS"  # Value read (variable/field/property)
    WRITES = "WRITES"  # Value write (assignment/modification)

    # Type/Reference (non-data-flow)
    REFERENCES = "REFERENCES"  # Type/class/interface/symbol reference

    # Type/Inheritance/Implementation
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"

    # Structure/Pattern
    DECORATES = "DECORATES"
    INSTANTIATES = "INSTANTIATES"
    OVERRIDES = "OVERRIDES"

    # Resource/State
    USES = "USES"
    READS_RESOURCE = "READS_RESOURCE"
    WRITES_RESOURCE = "WRITES_RESOURCE"

    # Exception/Control
    THROWS = "THROWS"
    ROUTE_TO = "ROUTE_TO"
    USES_REPO = "USES_REPO"


# ============================================================
# Common Structures
# ============================================================


@dataclass
class Span:
    """Source code location"""

    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def overlaps(self, other: "Span") -> bool:
        """Check if this span overlaps with another"""
        return not (
            self.end_line < other.start_line or other.end_line < self.start_line
        )

    def contains_line(self, line: int) -> bool:
        """Check if span contains the given line"""
        return self.start_line <= line <= self.end_line


@dataclass
class ControlFlowSummary:
    """Control flow summary (without full CFG)"""

    cyclomatic_complexity: int = 1
    has_loop: bool = False
    has_try: bool = False
    branch_count: int = 0


# ============================================================
# Core Entities
# ============================================================


@dataclass
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
    stable_id: Optional[str] = None  # Hash-based stable ID for file movement tracking
    content_hash: Optional[str] = None  # sha256 of node's code text

    # [Optional] Structure
    name: Optional[str] = None  # Symbol name (null for File/Block)
    module_path: Optional[str] = None  # For import/name resolution
    parent_id: Optional[str] = None  # Convenience anchor (also in CONTAINS Edge)
    body_span: Optional[Span] = None  # Body only (excluding signature)

    # [Optional] Metadata
    docstring: Optional[str] = None  # For LLM summary/search
    role: Optional[str] = None  # controller, service, repo, dto, entity, util, test, ...
    is_test_file: Optional[bool] = None

    # [Optional] Type/Signature references
    signature_id: Optional[str] = None  # For Function/Method/Lambda
    declared_type_id: Optional[str] = None  # For Variable/Field

    # [Optional] Control flow
    control_flow_summary: Optional[ControlFlowSummary] = None

    # [Optional] Language-specific extensions
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
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
    span: Optional[Span] = None  # Where this relationship appears in code

    # [Optional] Metadata
    attrs: dict[str, Any] = field(default_factory=dict)
