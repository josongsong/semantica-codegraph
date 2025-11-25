"""
Symbol Index (Kuzu Graph)

Graph-based symbol navigation using Kuzu embedded database.

Features:
    - Symbol search by name/FQN
    - Go-to-definition
    - Find references (callers/callees)
    - Call graph queries
"""

from .adapter_kuzu import KuzuSymbolIndex, create_kuzu_symbol_index

__all__ = [
    "KuzuSymbolIndex",
    "create_kuzu_symbol_index",
]
