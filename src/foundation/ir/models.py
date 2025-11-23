"""
IR v4.1 Data Models

Core data structures for Intermediate Representation of code.
Based on IR v4.1 specification with the following key decisions:
- logical_id as primary key (human-readable)
- stable_id for file movement tracking
- content_hash for "same code" detection
- Type resolution level: LOCAL + MODULE first
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


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


class TypeFlavor(str, Enum):
    """Type classification"""

    PRIMITIVE = "primitive"  # int, str, bool, etc.
    BUILTIN = "builtin"  # list, dict, set, etc.
    USER = "user"  # User-defined classes/types
    EXTERNAL = "external"  # Third-party library types
    TYPEVAR = "typevar"  # Generic type variables
    GENERIC = "generic"  # Generic types


class TypeResolutionLevel(str, Enum):
    """Type resolution level (progressive)"""

    RAW = "raw"  # Raw string only
    BUILTIN = "builtin"  # Built-in types resolved
    LOCAL = "local"  # Same file definitions
    MODULE = "module"  # Same package imports
    PROJECT = "project"  # Entire project
    EXTERNAL = "external"  # External dependencies


class Visibility(str, Enum):
    """Access control (language-specific mapping)"""

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"


class CFGBlockKind(str, Enum):
    """Control Flow Graph block types"""

    ENTRY = "Entry"
    EXIT = "Exit"
    BLOCK = "Block"
    CONDITION = "Condition"
    LOOP_HEADER = "LoopHeader"
    TRY = "Try"
    CATCH = "Catch"
    FINALLY = "Finally"


class CFGEdgeKind(str, Enum):
    """Control Flow Graph edge types"""

    NORMAL = "NORMAL"
    TRUE_BRANCH = "TRUE_BRANCH"
    FALSE_BRANCH = "FALSE_BRANCH"
    EXCEPTION = "EXCEPTION"
    LOOP_BACK = "LOOP_BACK"


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


@dataclass
class TypeEntity:
    """
    Type system representation (separate from Node).

    Type resolution is progressive:
    - Phase 1: raw_only
    - Phase 2: builtin + local + module
    - Phase 3: project
    - Phase 4: external
    """

    # [Required] Identity
    id: str  # e.g., "type:RetrievalPlan", "type:List[Candidate]"
    raw: str  # As it appears in code

    # [Required] Classification
    flavor: TypeFlavor
    is_nullable: bool
    resolution_level: TypeResolutionLevel

    # [Optional] Resolution
    resolved_target: Optional[str] = None  # Node.id (Class/Interface/TypeAlias)

    # [Optional] Generics
    generic_param_ids: list[str] = field(default_factory=list)  # TypeEntity.id list


@dataclass
class SignatureEntity:
    """
    Function/Method signature (separate entity for interface change detection).
    """

    # [Required] Identity
    id: str  # e.g., "sig:HybridRetriever.plan(Query,int)->RetrievalPlan"
    owner_node_id: str  # Node.id (Function/Method/Lambda)
    name: str
    raw: str  # Signature string

    # [Required] Parameters/Return
    parameter_type_ids: list[str] = field(default_factory=list)  # TypeEntity.id list
    return_type_id: Optional[str] = None  # TypeEntity.id

    # [Required] Modifiers
    is_async: bool = False
    is_static: bool = False

    # [Optional] Metadata
    visibility: Optional[Visibility] = None
    throws_type_ids: list[str] = field(default_factory=list)  # TypeEntity.id list
    signature_hash: Optional[str] = None  # For interface change detection


# ============================================================
# Control Flow Graph (CFG)
# ============================================================


@dataclass
class ControlFlowBlock:
    """CFG Basic Block"""

    # [Required] Identity
    id: str  # e.g., "cfg:plan:block:1"
    kind: CFGBlockKind
    function_node_id: str  # Node.id (Function/Method)

    # [Optional] Location
    span: Optional[Span] = None

    # [Optional] Data Flow (for DFG)
    defined_variable_ids: list[str] = field(default_factory=list)  # Node.id (Variable/Field)
    used_variable_ids: list[str] = field(default_factory=list)  # Node.id


@dataclass
class ControlFlowEdge:
    """CFG Edge between blocks"""

    source_block_id: str
    target_block_id: str
    kind: CFGEdgeKind


@dataclass
class ControlFlowGraph:
    """Control Flow Graph for a single function/method"""

    # [Required] Identity
    id: str  # e.g., "cfg:HybridRetriever.plan"
    function_node_id: str  # Node.id (Function/Method)

    # [Required] Structure
    entry_block_id: str
    exit_block_id: str
    blocks: list[ControlFlowBlock] = field(default_factory=list)
    edges: list[ControlFlowEdge] = field(default_factory=list)


# ============================================================
# IR Document (Container)
# ============================================================


@dataclass
class IRDocument:
    """
    Complete IR snapshot for a repository at a specific point in time.

    This is the top-level container that gets serialized to JSON/DB.
    """

    # [Required] Identity
    repo_id: str  # e.g., "semantica-codegraph"
    snapshot_id: str  # e.g., "commit:abc123", "workspace:user@session"
    schema_version: str  # e.g., "4.1.0"

    # [Required] Core layers
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    # [Optional] Advanced layers
    types: list[TypeEntity] = field(default_factory=list)
    signatures: list[SignatureEntity] = field(default_factory=list)
    control_flow_graphs: list[ControlFlowGraph] = field(default_factory=list)

    # [Optional] Metadata
    meta: dict[str, Any] = field(default_factory=dict)


# ============================================================
# File IR Bundle (for IRStore caching)
# ============================================================


@dataclass
class FileIRBundle:
    """
    File-level IR bundle for efficient caching in IRStore.

    This is the unit of Hot/Cold management, not individual nodes.
    """

    repo_id: str
    snapshot_id: str
    file_path: str

    # All IR entities for this file
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    types: list[TypeEntity] = field(default_factory=list)
    signatures: list[SignatureEntity] = field(default_factory=list)
    control_flow_graphs: list[ControlFlowGraph] = field(default_factory=list)

    # Cache metadata
    last_accessed: Optional[float] = None  # Unix timestamp
    access_count: int = 0
    hotness_score: float = 0.0
