"""
Tree-sitter Compatibility Layer (L11 SOTA급)

Optional Dependency의 Fallback 로직을 명확히 처리:
- tree-sitter 있으면: 실제 TSNode 사용
- tree-sitter 없으면: 명시적 NotImplementedError

Fake/Stub 금지 원칙 준수:
- return True 같은 fake 대신 명시적 에러 발생
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode
else:
    TSNode = Any

# Runtime import
try:
    from tree_sitter import Node as _TSNode

    TREE_SITTER_AVAILABLE = True
    TSNodeRuntime = _TSNode
except ImportError:
    TREE_SITTER_AVAILABLE = False
    TSNodeRuntime = None


def require_tree_sitter() -> None:
    """
    tree-sitter 필수 체크 (L11 SOTA급)

    Fake/Stub 금지: 없으면 명시적 에러

    Raises:
        NotImplementedError: tree-sitter not installed
    """
    if not TREE_SITTER_AVAILABLE:
        raise NotImplementedError("tree-sitter is required for this operation. Install with: pip install tree-sitter")


def safe_node_type(node: Any) -> str:
    """
    안전한 node.type 접근 (방어적 코딩)

    Args:
        node: TSNode 또는 Any

    Returns:
        node.type 또는 빈 문자열

    Notes:
        TYPE_CHECKING=TSNode이지만 runtime=None인 경우 방어
    """
    if node is None:
        return ""

    if hasattr(node, "type"):
        return node.type

    # Fallback: tree-sitter 없는 상황
    return ""


__all__ = [
    "TSNode",
    "TSNodeRuntime",
    "TREE_SITTER_AVAILABLE",
    "require_tree_sitter",
    "safe_node_type",
]
