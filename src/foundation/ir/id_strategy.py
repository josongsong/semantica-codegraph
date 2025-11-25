"""
IR Node ID Generation Strategy

Implements dual ID system:
- logical_id: Human-readable (primary key)
- stable_id: Hash-based for file movement tracking
- content_hash: For "same code" detection
"""

import hashlib

from .models import NodeKind, Span


def generate_logical_id(
    repo_id: str,
    kind: NodeKind,
    file_path: str,
    fqn: str,
) -> str:
    """
    Generate human-readable logical ID.

    Format: {kind}:{repo_id}:{file_path}:{fqn_suffix}

    Examples:
    - "method:semantica:src/retriever/plan.py:HybridRetriever.plan"
    - "class:semantica:src/retriever/plan.py:HybridRetriever"
    - "file:semantica:src/retriever/plan.py"
    """
    # For File nodes, use file_path as suffix
    if kind == NodeKind.FILE:
        return f"{kind.value.lower()}:{repo_id}:{file_path}"

    # Extract suffix from FQN (last part after module path)
    # e.g., "semantica.retriever.plan.HybridRetriever.plan" -> "HybridRetriever.plan"
    fqn_suffix = fqn.split(".")[-2:] if "." in fqn else [fqn]
    suffix = ".".join(fqn_suffix)

    return f"{kind.value.lower()}:{repo_id}:{file_path}:{suffix}"


def generate_stable_id(
    repo_id: str,
    kind: NodeKind,
    fqn: str,
    span: Span,
    content_hash: str,
) -> str:
    """
    Generate hash-based stable ID for file movement tracking.

    This ID remains stable even when file is moved, as long as:
    - FQN stays the same (or similar)
    - Span is similar
    - Content is the same

    Format: "stable:{hash}"
    """
    # Construct a stable key
    # Note: file_path is intentionally excluded for stability across file moves
    stable_key = f"{repo_id}:{kind.value}:{fqn}:" f"{span.start_line}-{span.end_line}:" f"{content_hash}"

    # Hash to 16 chars for brevity
    hash_digest = hashlib.sha256(stable_key.encode()).hexdigest()[:16]

    return f"stable:{hash_digest}"


def generate_content_hash(code_text: str) -> str:
    """
    Generate SHA256 hash of node's code text.

    Used for:
    - Detecting "same code" across snapshots
    - Stable ID generation
    - Change detection in incremental indexing
    """
    # Normalize whitespace (optional, can be strict)
    normalized = code_text.strip()

    hash_digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"sha256:{hash_digest}"


def generate_edge_id(
    kind: str,
    source_id: str,
    target_id: str,
    occurrence: int = 0,
) -> str:
    """
    Generate edge ID.

    Format: "edge:{kind}:{source_suffix}→{target_suffix}@{occurrence}"

    Examples:
    - "edge:call:plan→_search_vector@0"
    - "edge:contains:HybridRetriever→plan@0"
    """
    # Extract short names for readability
    source_suffix = source_id.split(":")[-1] if ":" in source_id else source_id
    target_suffix = target_id.split(":")[-1] if ":" in target_id else target_id

    return f"edge:{kind.lower()}:{source_suffix}→{target_suffix}@{occurrence}"


def generate_type_id(raw_type: str, repo_id: str) -> str:
    """
    Generate type entity ID.

    Format: "type:{repo_id}:{normalized_type}"

    Examples:
    - "type:semantica:RetrievalPlan"
    - "type:semantica:List[Candidate]"
    - "type:builtin:int"
    """
    # Normalize type string (remove extra spaces)
    normalized = raw_type.replace(" ", "")

    # For built-in types, use "builtin" as repo
    if is_builtin_type(raw_type):
        return f"type:builtin:{normalized}"

    return f"type:{repo_id}:{normalized}"


def generate_signature_id(
    owner_node_id: str,
    name: str,
    param_types: list[str],
    return_type: str | None,
) -> str:
    """
    Generate signature entity ID.

    Format: "sig:{owner_suffix}:{name}({params})->{return}"

    Examples:
    - "sig:HybridRetriever:plan(Query,int)->RetrievalPlan"
    - "sig:build_default_plan(str)->Plan"
    """
    owner_suffix = owner_node_id.split(":")[-1] if ":" in owner_node_id else owner_node_id

    # Simplify param types (just the type name)
    param_str = ",".join(_simplify_type(t) for t in param_types)

    # Simplify return type
    return_str = _simplify_type(return_type) if return_type else "None"

    return f"sig:{owner_suffix}:{name}({param_str})->{return_str}"


def generate_signature_hash(
    name: str,
    param_types: list[str],
    return_type: str | None,
    is_async: bool,
    is_static: bool,
) -> str:
    """
    Generate signature hash for interface change detection.

    This hash changes only when the function signature changes,
    not when implementation changes.
    """
    sig_key = (
        f"{name}:"
        f"params={','.join(param_types)}:"
        f"return={return_type or 'None'}:"
        f"async={is_async}:"
        f"static={is_static}"
    )

    hash_digest = hashlib.sha256(sig_key.encode()).hexdigest()[:16]
    return f"sighash:{hash_digest}"


def generate_cfg_block_id(function_node_id: str, block_index: int) -> str:
    """
    Generate CFG block ID.

    Format: "cfg:{function_suffix}:block:{index}"
    """
    function_suffix = function_node_id.split(":")[-1] if ":" in function_node_id else function_node_id
    return f"cfg:{function_suffix}:block:{block_index}"


def generate_cfg_id(function_node_id: str) -> str:
    """
    Generate CFG ID.

    Format: "cfg:{function_suffix}"
    """
    function_suffix = function_node_id.split(":")[-1] if ":" in function_node_id else function_node_id
    return f"cfg:{function_suffix}"


# ============================================================
# Helpers
# ============================================================


def is_builtin_type(type_str: str) -> bool:
    """Check if type is a built-in type"""
    builtin_types = {
        # Python
        "int",
        "str",
        "float",
        "bool",
        "bytes",
        "list",
        "dict",
        "set",
        "tuple",
        "None",
        "Any",
        # JavaScript/TypeScript
        "number",
        "string",
        "boolean",
        "object",
        "array",
        "void",
        "null",
        "undefined",
        "any",
        # Go
        "int64",
        "int32",
        "float64",
        "interface{}",
        # Java
        "Integer",
        "String",
        "Boolean",
        "Double",
        "Long",
    }

    # Extract base type (before brackets)
    base_type = type_str.split("[")[0].strip()
    return base_type.lower() in {t.lower() for t in builtin_types}


def _simplify_type(type_str: str) -> str:
    """Simplify type string for signature ID"""
    if not type_str:
        return ""

    # Remove module paths, keep only the last part
    # e.g., "semantica.core.types.Query" -> "Query"
    parts = type_str.replace(" ", "").split(".")
    return parts[-1]
