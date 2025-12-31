"""
RFC-031 Phase B: ID Generation Helper for Java Generator

Provides backward-compatible wrapper for Hash ID generation.
"""

from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    CanonicalIdentity,
    generate_node_id_v2,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind


def generate_java_node_id(
    repo_id: str,
    kind: NodeKind,
    file_path: str,
    fqn: str,
) -> str:
    """
    Generate Java node ID using RFC-031 Hash ID.

    Args:
        repo_id: Repository ID
        kind: NodeKind enum
        file_path: File path
        fqn: Fully qualified name

    Returns:
        Hash ID (node:repo:kind:hash)
    """
    identity = CanonicalIdentity(
        repo_id=repo_id,
        kind=kind.value,
        file_path=file_path,
        fqn=fqn,
        language="java",
    )
    return generate_node_id_v2(identity)
