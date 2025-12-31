"""
Canonical Kind Definitions (RFC-031)

Single source of truth for Node/Edge kinds across IR and Graph layers.
Provides KindMeta for policy-driven transformation.

Author: Semantica Team
Version: 1.0.0
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


# ============================================================
# Canonical Node Kind
# ============================================================


class NodeKind(str, Enum):
    """
    Canonical NodeKind - unified enum for IR and Graph layers.

    Categories:
    - STRUCTURAL: Basic code structure (IR/Graph 공통)
    - CONTROL: Control flow (IR 전용, Graph에서 SKIP)
    - SEMANTIC: Type/Signature (Graph 전용)
    - EXTERNAL: External references (Graph 전용)
    - FRAMEWORK: Framework entities (Graph 전용)
    """

    # === Structural (IR/Graph 공통) ===
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    INTERFACE = "Interface"
    FUNCTION = "Function"
    METHOD = "Method"
    VARIABLE = "Variable"
    FIELD = "Field"
    IMPORT = "Import"

    # === IR 전용 (AST 구조) ===
    ENUM = "Enum"
    TYPE_ALIAS = "TypeAlias"
    LAMBDA = "Lambda"
    METHOD_REFERENCE = "MethodReference"
    TYPE_PARAMETER = "TypeParameter"
    PROPERTY = "Property"
    CONSTANT = "Constant"
    EXPORT = "Export"
    EXPRESSION = "Expression"  # RFC-031: Call sites, binary ops, etc.

    # === IR 전용 (Control Flow) ===
    BLOCK = "Block"
    CONDITION = "Condition"
    LOOP = "Loop"
    TRY_CATCH = "TryCatch"

    # === Graph 전용 (Semantic) ===
    TYPE = "Type"
    SIGNATURE = "Signature"
    CFG_BLOCK = "CfgBlock"

    # === Graph 전용 (External) ===
    EXTERNAL_MODULE = "ExternalModule"
    EXTERNAL_FUNCTION = "ExternalFunction"
    EXTERNAL_TYPE = "ExternalType"

    # === Graph 전용 (Framework) ===
    ROUTE = "Route"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    CONFIG = "Config"
    JOB = "Job"
    MIDDLEWARE = "Middleware"
    SUMMARY = "Summary"
    DOCUMENT = "Document"

    # === Template IR (RFC-051) ===
    TEMPLATE_DOC = "TemplateDoc"
    """Template document (JSX, Vue SFC, Jinja, etc.)"""

    TEMPLATE_ELEMENT = "TemplateElement"
    """Template HTML/Component element"""

    TEMPLATE_SLOT = "TemplateSlot"
    """Template dynamic value insertion point (XSS analysis target)"""

    TEMPLATE_DIRECTIVE = "TemplateDirective"
    """Template directive (v-if, v-for, ng-for, etc.)"""


# ============================================================
# Canonical Edge Kind
# ============================================================


class EdgeKind(str, Enum):
    """
    Canonical EdgeKind - unified enum for IR and Graph layers.

    Categories:
    - STRUCTURAL: Containment, definition
    - CALL_USAGE: Calls, reads, writes
    - TYPE_REF: Type references, inheritance
    - CONTROL_FLOW: CFG edges
    - FRAMEWORK: Route/service relationships
    """

    # === Structural ===
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"

    # === Call/Usage ===
    CALLS = "CALLS"
    READS = "READS"
    WRITES = "WRITES"
    REFERENCES = "REFERENCES"

    # === Type/Inheritance ===
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    REFERENCES_TYPE = "REFERENCES_TYPE"
    REFERENCES_SYMBOL = "REFERENCES_SYMBOL"

    # === Decorator/Instance ===
    DECORATES = "DECORATES"
    INSTANTIATES = "INSTANTIATES"
    OVERRIDES = "OVERRIDES"

    # === Resource ===
    USES = "USES"
    READS_RESOURCE = "READS_RESOURCE"
    WRITES_RESOURCE = "WRITES_RESOURCE"

    # === Exception/Control ===
    THROWS = "THROWS"
    ROUTE_TO = "ROUTE_TO"
    USES_REPO = "USES_REPO"

    # === Closure/Capture ===
    CAPTURES = "CAPTURES"
    ACCESSES = "ACCESSES"
    SHADOWS = "SHADOWS"

    # === Control Flow (CFG) ===
    CFG_NEXT = "CFG_NEXT"
    CFG_BRANCH = "CFG_BRANCH"
    CFG_LOOP = "CFG_LOOP"
    CFG_HANDLER = "CFG_HANDLER"

    # === Framework ===
    ROUTE_HANDLER = "ROUTE_HANDLER"
    HANDLES_REQUEST = "HANDLES_REQUEST"
    USES_REPOSITORY = "USES_REPOSITORY"
    MIDDLEWARE_NEXT = "MIDDLEWARE_NEXT"

    # === Documentation ===
    DOCUMENTS = "DOCUMENTS"
    REFERENCES_CODE = "REFERENCES_CODE"
    DOCUMENTED_IN = "DOCUMENTED_IN"

    # === Template Binding (RFC-051) ===
    RENDERS = "RENDERS"
    """Function/Component → TemplateDoc (rendering relationship)"""

    BINDS = "BINDS"
    """Variable/Expression → TemplateSlot (data binding)"""

    ESCAPES = "ESCAPES"
    """Sanitizer → TemplateSlot (escape/sanitization applied)"""

    CONTAINS_SLOT = "CONTAINS_SLOT"
    """TemplateElement → TemplateSlot (containment)"""

    TEMPLATE_CHILD = "TEMPLATE_CHILD"
    """TemplateElement → TemplateElement (parent-child relationship)"""


# ============================================================
# Kind Metadata
# ============================================================


@dataclass(frozen=True)
class KindMeta:
    """
    Kind metadata for policy-driven transformation.

    Attributes:
        layer: Where this kind is used ("IR", "GRAPH", "BOTH")
        family: Semantic category
        languages: Supported languages (empty = all)
        graph_policy: IR→Graph transformation policy
        graph_target: Target kind when policy is "CONVERT"
    """

    layer: Literal["IR", "GRAPH", "BOTH"]
    family: Literal["STRUCTURAL", "SEMANTIC", "EXTERNAL", "FRAMEWORK", "CONTROL"]
    languages: frozenset[str]
    graph_policy: Literal["KEEP", "CONVERT", "SKIP"]
    graph_target: NodeKind | None = None


# ============================================================
# Kind Meta Registry (fail-fast on missing)
# ============================================================

NODE_KIND_META: dict[NodeKind, KindMeta] = {
    # === Structural (BOTH, KEEP) ===
    NodeKind.FILE: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.MODULE: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.CLASS: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.INTERFACE: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.FUNCTION: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.METHOD: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.VARIABLE: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.FIELD: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    NodeKind.IMPORT: KindMeta("BOTH", "STRUCTURAL", frozenset(), "KEEP"),
    # === IR 전용 (CONVERT or SKIP) ===
    NodeKind.ENUM: KindMeta("IR", "STRUCTURAL", frozenset(), "CONVERT", NodeKind.CLASS),
    NodeKind.TYPE_ALIAS: KindMeta("IR", "STRUCTURAL", frozenset(), "CONVERT", NodeKind.TYPE),
    NodeKind.LAMBDA: KindMeta(
        "IR", "STRUCTURAL", frozenset({"python", "java", "typescript"}), "CONVERT", NodeKind.FUNCTION
    ),
    NodeKind.METHOD_REFERENCE: KindMeta("IR", "STRUCTURAL", frozenset({"java"}), "SKIP"),
    NodeKind.TYPE_PARAMETER: KindMeta("IR", "STRUCTURAL", frozenset({"java", "typescript"}), "SKIP"),
    NodeKind.PROPERTY: KindMeta("IR", "STRUCTURAL", frozenset(), "CONVERT", NodeKind.FIELD),
    NodeKind.CONSTANT: KindMeta("IR", "STRUCTURAL", frozenset(), "CONVERT", NodeKind.VARIABLE),
    NodeKind.EXPORT: KindMeta("IR", "STRUCTURAL", frozenset({"typescript", "javascript"}), "SKIP"),
    NodeKind.EXPRESSION: KindMeta("IR", "STRUCTURAL", frozenset(), "SKIP"),  # Call sites, binary ops
    # === IR Control Flow (SKIP) ===
    NodeKind.BLOCK: KindMeta("IR", "CONTROL", frozenset(), "SKIP"),
    NodeKind.CONDITION: KindMeta("IR", "CONTROL", frozenset(), "SKIP"),
    NodeKind.LOOP: KindMeta("IR", "CONTROL", frozenset(), "SKIP"),
    NodeKind.TRY_CATCH: KindMeta("IR", "CONTROL", frozenset(), "SKIP"),
    # === Graph Semantic (GRAPH, KEEP) ===
    NodeKind.TYPE: KindMeta("GRAPH", "SEMANTIC", frozenset(), "KEEP"),
    NodeKind.SIGNATURE: KindMeta("GRAPH", "SEMANTIC", frozenset(), "KEEP"),
    NodeKind.CFG_BLOCK: KindMeta("GRAPH", "SEMANTIC", frozenset(), "KEEP"),
    # === Graph External (GRAPH, KEEP) ===
    NodeKind.EXTERNAL_MODULE: KindMeta("GRAPH", "EXTERNAL", frozenset(), "KEEP"),
    NodeKind.EXTERNAL_FUNCTION: KindMeta("GRAPH", "EXTERNAL", frozenset(), "KEEP"),
    NodeKind.EXTERNAL_TYPE: KindMeta("GRAPH", "EXTERNAL", frozenset(), "KEEP"),
    # === Graph Framework (GRAPH, KEEP) ===
    NodeKind.ROUTE: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.SERVICE: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.REPOSITORY: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.CONFIG: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.JOB: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.MIDDLEWARE: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.SUMMARY: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    NodeKind.DOCUMENT: KindMeta("GRAPH", "FRAMEWORK", frozenset(), "KEEP"),
    # === Template IR (RFC-051) ===
    NodeKind.TEMPLATE_DOC: KindMeta("IR", "STRUCTURAL", frozenset(), "SKIP"),
    NodeKind.TEMPLATE_ELEMENT: KindMeta("IR", "STRUCTURAL", frozenset(), "SKIP"),
    NodeKind.TEMPLATE_SLOT: KindMeta("IR", "STRUCTURAL", frozenset(), "SKIP"),
    NodeKind.TEMPLATE_DIRECTIVE: KindMeta("IR", "STRUCTURAL", frozenset(), "SKIP"),
}


def get_node_meta(kind: NodeKind) -> KindMeta:
    """
    Get metadata for a NodeKind.

    Raises:
        KeyError: If kind is not registered (fail-fast)
    """
    try:
        return NODE_KIND_META[kind]
    except KeyError as e:
        raise KeyError(f"NODE_KIND_META missing for {kind}. Add to registry.") from e


def to_graph_node_kind(ir_kind: NodeKind) -> NodeKind | None:
    """
    Apply IR→Graph transformation policy.

    Returns:
        None: SKIP (not included in graph)
        Same kind: KEEP (use as-is)
        Different kind: CONVERT (transform to target)
    """
    meta = get_node_meta(ir_kind)
    if meta.graph_policy == "SKIP":
        return None
    if meta.graph_policy == "CONVERT":
        return meta.graph_target
    return ir_kind


def is_ir_kind(kind: NodeKind) -> bool:
    """Check if kind is used in IR layer"""
    meta = get_node_meta(kind)
    return meta.layer in ("IR", "BOTH")


def is_graph_kind(kind: NodeKind) -> bool:
    """Check if kind is used in Graph layer"""
    meta = get_node_meta(kind)
    return meta.layer in ("GRAPH", "BOTH")


# ============================================================
# Edge Kind Metadata (simplified - no complex transformation)
# ============================================================


@dataclass(frozen=True)
class EdgeKindMeta:
    """Edge kind metadata"""

    layer: Literal["IR", "GRAPH", "BOTH"]
    family: Literal["STRUCTURAL", "CALL_USAGE", "TYPE_REF", "CONTROL_FLOW", "FRAMEWORK", "DOCUMENTATION"]


EDGE_KIND_META: dict[EdgeKind, EdgeKindMeta] = {
    # Structural
    EdgeKind.CONTAINS: EdgeKindMeta("BOTH", "STRUCTURAL"),
    EdgeKind.DEFINES: EdgeKindMeta("IR", "STRUCTURAL"),
    # Call/Usage
    EdgeKind.CALLS: EdgeKindMeta("BOTH", "CALL_USAGE"),
    EdgeKind.READS: EdgeKindMeta("BOTH", "CALL_USAGE"),
    EdgeKind.WRITES: EdgeKindMeta("BOTH", "CALL_USAGE"),
    EdgeKind.REFERENCES: EdgeKindMeta("IR", "CALL_USAGE"),
    # Type/Inheritance
    EdgeKind.IMPORTS: EdgeKindMeta("BOTH", "TYPE_REF"),
    EdgeKind.INHERITS: EdgeKindMeta("BOTH", "TYPE_REF"),
    EdgeKind.IMPLEMENTS: EdgeKindMeta("BOTH", "TYPE_REF"),
    EdgeKind.REFERENCES_TYPE: EdgeKindMeta("GRAPH", "TYPE_REF"),
    EdgeKind.REFERENCES_SYMBOL: EdgeKindMeta("GRAPH", "TYPE_REF"),
    # Decorator/Instance
    EdgeKind.DECORATES: EdgeKindMeta("BOTH", "CALL_USAGE"),
    EdgeKind.INSTANTIATES: EdgeKindMeta("BOTH", "CALL_USAGE"),
    EdgeKind.OVERRIDES: EdgeKindMeta("BOTH", "TYPE_REF"),
    # Resource
    EdgeKind.USES: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.READS_RESOURCE: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.WRITES_RESOURCE: EdgeKindMeta("IR", "CALL_USAGE"),
    # Exception
    EdgeKind.THROWS: EdgeKindMeta("IR", "CONTROL_FLOW"),
    EdgeKind.ROUTE_TO: EdgeKindMeta("IR", "CONTROL_FLOW"),
    EdgeKind.USES_REPO: EdgeKindMeta("IR", "CALL_USAGE"),
    # Closure
    EdgeKind.CAPTURES: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.ACCESSES: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.SHADOWS: EdgeKindMeta("IR", "CALL_USAGE"),
    # Control Flow
    EdgeKind.CFG_NEXT: EdgeKindMeta("GRAPH", "CONTROL_FLOW"),
    EdgeKind.CFG_BRANCH: EdgeKindMeta("GRAPH", "CONTROL_FLOW"),
    EdgeKind.CFG_LOOP: EdgeKindMeta("GRAPH", "CONTROL_FLOW"),
    EdgeKind.CFG_HANDLER: EdgeKindMeta("GRAPH", "CONTROL_FLOW"),
    # Framework
    EdgeKind.ROUTE_HANDLER: EdgeKindMeta("GRAPH", "FRAMEWORK"),
    EdgeKind.HANDLES_REQUEST: EdgeKindMeta("GRAPH", "FRAMEWORK"),
    EdgeKind.USES_REPOSITORY: EdgeKindMeta("GRAPH", "FRAMEWORK"),
    EdgeKind.MIDDLEWARE_NEXT: EdgeKindMeta("GRAPH", "FRAMEWORK"),
    # Documentation
    EdgeKind.DOCUMENTS: EdgeKindMeta("GRAPH", "DOCUMENTATION"),
    EdgeKind.REFERENCES_CODE: EdgeKindMeta("GRAPH", "DOCUMENTATION"),
    EdgeKind.DOCUMENTED_IN: EdgeKindMeta("GRAPH", "DOCUMENTATION"),
    # Template Binding (RFC-051)
    EdgeKind.RENDERS: EdgeKindMeta("IR", "STRUCTURAL"),
    EdgeKind.BINDS: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.ESCAPES: EdgeKindMeta("IR", "CALL_USAGE"),
    EdgeKind.CONTAINS_SLOT: EdgeKindMeta("IR", "STRUCTURAL"),
    EdgeKind.TEMPLATE_CHILD: EdgeKindMeta("IR", "STRUCTURAL"),
}


def get_edge_meta(kind: EdgeKind) -> EdgeKindMeta:
    """
    Get metadata for an EdgeKind.

    Raises:
        KeyError: If kind is not registered (fail-fast)
    """
    try:
        return EDGE_KIND_META[kind]
    except KeyError as e:
        raise KeyError(f"EDGE_KIND_META missing for {kind}. Add to registry.") from e
