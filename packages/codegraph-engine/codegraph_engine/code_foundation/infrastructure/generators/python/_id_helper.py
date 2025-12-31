"""
RFC-031 Phase B: ID Generation Helper for Python Generators

Provides backward-compatible wrapper for Hash ID generation.
"""

from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    CanonicalIdentity,
    generate_node_id_v2,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind


def generate_python_node_id(
    repo_id: str,
    kind: NodeKind,
    file_path: str,
    fqn: str,
    language: str = "python",
) -> str:
    """
    Generate Python node ID using RFC-031 Hash ID.

    Wrapper for backward compatibility with existing code.

    Args:
        repo_id: Repository ID
        kind: NodeKind enum
        file_path: File path
        fqn: Fully qualified name
        language: Language (default: "python")

    Returns:
        Hash ID (node:repo:kind:hash)
    """
    identity = CanonicalIdentity(
        repo_id=repo_id,
        kind=kind.value,
        file_path=file_path,
        fqn=fqn,
        language=language,
    )
    return generate_node_id_v2(identity)
