"""
Tree-sitter utility functions

Shared utilities for tree-sitter AST parsing across language generators.
"""

from typing import Any


def get_node_text(node: Any, source_bytes: bytes | None = None, encoding: str = "utf-8") -> str:
    """
    Extract text content from a tree-sitter node

    Args:
        node: Tree-sitter AST node
        source_bytes: Optional source code bytes (for generators)
        encoding: Character encoding (default: utf-8)

    Returns:
        Text content as string

    Examples:
        # From generator (has source_bytes):
        text = get_node_text(node, self._source_bytes, self._source.encoding)

        # From parser (direct node.text):
        text = get_node_text(node)
    """
    if not node:
        return ""

    # If source_bytes provided, extract from byte range
    if source_bytes is not None:
        try:
            return source_bytes[node.start_byte : node.end_byte].decode(encoding)
        except (AttributeError, UnicodeDecodeError):
            pass

    # Fallback: Use node.text attribute
    if hasattr(node, "text"):
        text_bytes = node.text
        if isinstance(text_bytes, bytes):
            try:
                return text_bytes.decode(encoding)
            except UnicodeDecodeError:
                return text_bytes.decode(encoding, errors="replace")
        return str(text_bytes)

    # Last resort: str() conversion
    return str(node)


def safe_child_by_field(node: Any, field_name: str) -> Any | None:
    """
    Safely get child node by field name with null check

    Args:
        node: Parent tree-sitter node
        field_name: Field name to query

    Returns:
        Child node or None

    Examples:
        name_node = safe_child_by_field(node, 'name')
        if name_node:
            name = get_node_text(name_node)
    """
    if not node:
        return None

    if not hasattr(node, "child_by_field_name"):
        return None

    return node.child_by_field_name(field_name)
