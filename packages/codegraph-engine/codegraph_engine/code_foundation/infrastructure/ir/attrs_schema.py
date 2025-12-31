"""
RFC-031: Node.attrs Schema Registry

Defines the canonical keys and namespaces for Node.attrs dict.
All attrs access should use these constants for type safety and discoverability.

Namespacing:
- No prefix: Common/shared keys (e.g., "is_async", "decorators")
- "lang_*": Language-specific keys (e.g., "lang_java_annotations")
- "fw_*": Framework-specific keys (e.g., "fw_react_hooks")
- "_*": Internal/transient keys (e.g., "_uncommitted")

Usage:
    from codegraph_engine.code_foundation.infrastructure.ir.attrs_schema import AttrKey

    node.attrs[AttrKey.IS_ASYNC] = True
    node.attrs[AttrKey.PARAMETERS] = [...]
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypedDict


# ============================================================
# Common Attrs Keys (no prefix)
# ============================================================


class AttrKey(str, Enum):
    """
    Canonical attrs keys.

    Use these constants instead of string literals for:
    - IDE autocomplete
    - Refactoring safety
    - Discoverability via grep/search
    """

    # Function/Method signature
    IS_ASYNC = "is_async"
    PARAMETERS = "parameters"  # List of param dicts
    RETURN_TYPE = "return_type"
    GENERIC_PARAMS = "generic_params"
    DECORATORS = "decorators"  # Python decorators
    ANNOTATIONS = "annotations"  # Java annotations
    THROWS = "throws"  # Java throws clause

    # Type info
    TYPE_INFO = "type_info"  # Full type dict from analyzers
    TYPE_PARAMETERS = "type_parameters"  # Java/TS generics
    RETURN_NULLABLE = "return_nullable"
    RETURN_NONNULL = "return_nonnull"

    # LSP enrichment (RFC-031)
    LSP_TYPE = "lsp_type"  # LSP-resolved type string
    LSP_DOCS = "lsp_docs"  # LSP documentation string
    LSP_ENHANCED = "lsp_enhanced"  # Whether LSP enrichment was applied
    LSP_IS_BUILTIN = "lsp_is_builtin"  # Whether type is builtin

    # Type source tracking
    TYPE_SOURCE = "type_source"  # "ir" | "literal" | "yaml" | "lsp" | "annotation" | "inferred"
    INFERRED_TYPE_SOURCE = "inferred_type_source"  # Source of inferred type
    LOCAL_RETURN_TYPE = "local_return_type"  # Local flow inferred return type
    LOCAL_RETURN_TYPE_SOURCE = "local_return_type_source"  # Source of local return type

    # Body analysis
    BODY_STATEMENTS = "body_statements"  # Statement list for heap analysis
    BODY_SPAN = "body_span"  # Span of function body

    # Framework detection
    USES_HOOKS = "uses_hooks"  # React hooks detected

    # Internal/transient (underscore prefix)
    _UNCOMMITTED = "_uncommitted"  # Local overlay marker
    _GIT_COMMIT = "_git_commit"  # Snapshot commit hash

    # Language-specific (lang_ prefix)
    LANG_JAVA_TYPE_PARAMS = "lang_java_type_params"
    LANG_TS_GENERIC_PARAMS = "lang_ts_generic_params"

    # Framework-specific (fw_ prefix)
    FW_REACT_HOOKS = "fw_react_hooks"
    FW_FLASK_ROUTE = "fw_flask_route"
    FW_DJANGO_VIEW = "fw_django_view"
    FW_SPRING_MAPPING = "fw_spring_mapping"


# ============================================================
# TypedDict Schemas for structured attrs values
# ============================================================


class ParameterInfo(TypedDict, total=False):
    """Parameter info in attrs['parameters']"""

    name: str
    type: str | None
    default: str | None
    is_variadic: bool
    is_keyword: bool


class TypeInfo(TypedDict, total=False):
    """Type info in attrs['type_info']"""

    parameters: list[ParameterInfo]
    return_type: str | None
    type_params: list[str]
    is_async: bool
    is_generator: bool


class BodyStatement(TypedDict, total=False):
    """Body statement in attrs['body_statements']"""

    kind: Literal["assign", "call", "return", "if", "for", "while", "try", "with"]
    line: int
    target: str | None  # For assignments
    source: str | None  # For calls/assignments


# ============================================================
# Attrs Access Helpers
# ============================================================


def get_attr(attrs: dict[str, Any], key: AttrKey, default: Any = None) -> Any:
    """Type-safe attrs access with AttrKey enum."""
    return attrs.get(key.value, default)


def set_attr(attrs: dict[str, Any], key: AttrKey, value: Any) -> None:
    """Type-safe attrs setting with AttrKey enum."""
    attrs[key.value] = value


def has_attr(attrs: dict[str, Any], key: AttrKey) -> bool:
    """Check if attrs has the given key."""
    return key.value in attrs


@dataclass(frozen=True)
class AttrKeyMeta:
    """Metadata about an attrs key"""

    key: AttrKey
    value_type: type
    description: str
    node_kinds: frozenset[str]  # Which NodeKinds use this attr
    required: bool = False


# ============================================================
# Attrs Key Registry
# ============================================================

ATTR_KEY_META: dict[AttrKey, AttrKeyMeta] = {
    AttrKey.IS_ASYNC: AttrKeyMeta(
        key=AttrKey.IS_ASYNC,
        value_type=bool,
        description="Whether function/method is async",
        node_kinds=frozenset({"Function", "Method", "Lambda"}),
    ),
    AttrKey.PARAMETERS: AttrKeyMeta(
        key=AttrKey.PARAMETERS,
        value_type=list,
        description="List of ParameterInfo dicts",
        node_kinds=frozenset({"Function", "Method", "Lambda", "Constructor"}),
    ),
    AttrKey.RETURN_TYPE: AttrKeyMeta(
        key=AttrKey.RETURN_TYPE,
        value_type=str,
        description="Return type annotation string",
        node_kinds=frozenset({"Function", "Method", "Lambda"}),
    ),
    AttrKey.DECORATORS: AttrKeyMeta(
        key=AttrKey.DECORATORS,
        value_type=list,
        description="List of Python decorator names",
        node_kinds=frozenset({"Function", "Method", "Class"}),
    ),
    AttrKey.ANNOTATIONS: AttrKeyMeta(
        key=AttrKey.ANNOTATIONS,
        value_type=list,
        description="List of Java annotation names",
        node_kinds=frozenset({"Function", "Method", "Class", "Field"}),
    ),
    AttrKey.BODY_STATEMENTS: AttrKeyMeta(
        key=AttrKey.BODY_STATEMENTS,
        value_type=list,
        description="List of BodyStatement dicts for heap analysis",
        node_kinds=frozenset({"Function", "Method", "Lambda", "Constructor"}),
    ),
    AttrKey.TYPE_INFO: AttrKeyMeta(
        key=AttrKey.TYPE_INFO,
        value_type=dict,
        description="Full TypeInfo dict from type analyzers",
        node_kinds=frozenset({"Function", "Method", "Lambda", "Constructor"}),
    ),
    AttrKey.USES_HOOKS: AttrKeyMeta(
        key=AttrKey.USES_HOOKS,
        value_type=bool,
        description="Whether React hooks are used",
        node_kinds=frozenset({"Function", "Method"}),
    ),
    AttrKey.LSP_TYPE: AttrKeyMeta(
        key=AttrKey.LSP_TYPE,
        value_type=str,
        description="LSP-resolved type string",
        node_kinds=frozenset({"Function", "Method", "Variable", "Parameter", "Class"}),
    ),
    AttrKey.LSP_DOCS: AttrKeyMeta(
        key=AttrKey.LSP_DOCS,
        value_type=str,
        description="LSP documentation string",
        node_kinds=frozenset({"Function", "Method", "Variable", "Parameter", "Class"}),
    ),
    AttrKey.LSP_ENHANCED: AttrKeyMeta(
        key=AttrKey.LSP_ENHANCED,
        value_type=bool,
        description="Whether LSP enrichment was applied",
        node_kinds=frozenset({"Function", "Method", "Variable", "Parameter", "Class"}),
    ),
    AttrKey.TYPE_SOURCE: AttrKeyMeta(
        key=AttrKey.TYPE_SOURCE,
        value_type=str,
        description="Source of type information (ir/literal/yaml/lsp/annotation/inferred)",
        node_kinds=frozenset({"Function", "Method", "Variable", "Parameter"}),
    ),
}


def validate_attrs(attrs: dict[str, Any], node_kind: str) -> list[str]:
    """
    Validate attrs dict against schema.

    Returns list of warning messages for unknown/mistyped keys.
    Does not raise - just warns for flexibility.
    """
    warnings = []

    for key, value in attrs.items():
        # Check if key is known
        try:
            attr_key = AttrKey(key)
        except ValueError:
            # Unknown key - warn if not prefixed correctly
            if not (key.startswith("lang_") or key.startswith("fw_") or key.startswith("_")):
                warnings.append(f"Unknown attrs key '{key}' without namespace prefix")
            continue

        # Check metadata if available
        if attr_key in ATTR_KEY_META:
            meta = ATTR_KEY_META[attr_key]

            # Check value type
            if not isinstance(value, meta.value_type):
                warnings.append(
                    f"Attrs key '{key}' has type {type(value).__name__}, expected {meta.value_type.__name__}"
                )

            # Check node kind compatibility
            if node_kind not in meta.node_kinds:
                warnings.append(f"Attrs key '{key}' not expected on NodeKind.{node_kind}")

    return warnings
