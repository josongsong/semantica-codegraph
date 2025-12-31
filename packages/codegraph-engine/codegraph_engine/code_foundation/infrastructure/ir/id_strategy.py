"""
IR Node ID Generation Strategy

Implements dual ID system:
- logical_id: Human-readable (primary key) - LEGACY
- stable_id: Hash-based for file movement tracking

RFC-031 additions:
- CanonicalIdentity: Structured identity for lossless ID generation
- generate_node_id_v2: Stable hash ID (24 hex)
- generate_edge_id_v2: Stable hash ID (20 hex)
"""

import hashlib
from dataclasses import dataclass

from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind, Span


# ============================================================
# RFC-031: Canonical Identity & Stable Hash ID
# ============================================================

# Hash lengths (RFC-031: increased for collision safety)
NODE_HASH_HEX = 24  # 96 bits
EDGE_HASH_HEX = 20  # 80 bits


@dataclass(frozen=True)
class CanonicalIdentity:
    """
    Canonical identity for nodes - lossless structure.

    Used for:
    - Stable hash ID generation
    - Reverse lookup (ID → identity)
    - Collision detection
    """

    repo_id: str
    kind: str  # NodeKind.value
    file_path: str
    fqn: str
    language: str

    def to_key(self, salt: str = "") -> str:
        """Generate hash key string"""
        return f"{self.repo_id}|{self.kind}|{self.file_path}|{self.fqn}|{self.language}|{salt}"


def _hash_hex(key: str, n_hex: int) -> str:
    """Generate hex hash of specified length"""
    return hashlib.sha256(key.encode()).hexdigest()[:n_hex]


def generate_node_id_v2(identity: CanonicalIdentity, salt: str = "") -> str:
    """
    RFC-031: Generate stable hash node ID.

    Format: node:{repo}:{kind}:{hash}

    Args:
        identity: Canonical identity
        salt: Optional salt for collision resolution

    Returns:
        Stable hash ID (24 hex = 96 bits)

    Note:
        Reverse lookup is done via Node's canonical fields, not ID parsing.
    """
    digest = _hash_hex(identity.to_key(salt), NODE_HASH_HEX)
    return f"node:{identity.repo_id}:{identity.kind.lower()}:{digest}"


def generate_edge_id_v2(
    kind: str,
    source_id: str,
    target_id: str,
    occurrence: int = 0,
    salt: str = "",
) -> str:
    """
    RFC-031: Generate stable hash edge ID.

    Format: edge:{kind}:{hash}

    Args:
        kind: EdgeKind value
        source_id: Source node ID
        target_id: Target node ID
        occurrence: Occurrence index (for multiple edges)
        salt: Optional salt for collision resolution

    Returns:
        Stable hash ID (20 hex = 80 bits)
    """
    key = f"{kind}|{source_id}|{target_id}|{occurrence}|{salt}"
    digest = _hash_hex(key, EDGE_HASH_HEX)
    return f"edge:{kind.lower()}:{digest}"


# ============================================================
# Legacy ID Generation (DEPRECATED - Use generate_node_id_v2)
# ============================================================


def generate_logical_id(
    repo_id: str,
    kind: NodeKind,
    file_path: str,
    fqn: str,
) -> str:
    """
    DEPRECATED: Use generate_node_id_v2() instead.

    Legacy human-readable logical ID generation.
    Kept for backward compatibility during migration.

    Format: {kind}:{repo_id}:{file_path}:{fqn_suffix}

    Migration:
        identity = CanonicalIdentity(repo_id, kind.value, file_path, fqn, language)
        new_id = generate_node_id_v2(identity)
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
    stable_key = f"{repo_id}:{kind.value}:{fqn}:{span.start_line}-{span.end_line}:{content_hash}"

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
    DEPRECATED: Use generate_edge_id_v2() instead.

    Legacy edge ID generation with human-readable format.
    Kept for backward compatibility during migration.

    Format: "edge:{kind}:{source_suffix}→{target_suffix}@{occurrence}"

    Migration:
        new_id = generate_edge_id_v2(kind, source_id, target_id, occurrence)
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
        f"{name}:params={','.join(param_types)}:return={return_type or 'None'}:async={is_async}:static={is_static}"
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
