"""
Symbol Graph Adapter for Chunk Builder

Provides backward-compatible interface for ChunkBuilder to use SymbolGraph.
"""

from typing import TYPE_CHECKING

from ..symbol_graph.models import SymbolKind

if TYPE_CHECKING:
    from ..symbol_graph.models import Symbol, SymbolGraph


class ChunkSymbolAdapter:
    """
    Adapter for ChunkBuilder to use SymbolGraph.

    Provides simple get_symbol() interface that returns Symbol by ID.
    """

    def __init__(self, symbol_graph: "SymbolGraph"):
        """
        Initialize adapter.

        Args:
            symbol_graph: SymbolGraph to adapt
        """
        self.symbol_graph = symbol_graph

    def get_symbol(self, symbol_id: str) -> "Symbol | None":
        """
        Get symbol by ID.

        Args:
            symbol_id: Symbol identifier

        Returns:
            Symbol if found, None otherwise
        """
        return self.symbol_graph.get_symbol(symbol_id)


def map_symbol_kind_to_chunk_kind(symbol_kind: SymbolKind) -> str:
    """
    Map SymbolKind to Chunk kind.

    Args:
        symbol_kind: SymbolKind from SymbolGraph

    Returns:
        Chunk kind string
    """
    # Direct mapping for most kinds
    mapping = {
        SymbolKind.FILE: "file",
        SymbolKind.MODULE: "module",
        SymbolKind.CLASS: "class",
        SymbolKind.FUNCTION: "function",
        SymbolKind.METHOD: "function",  # Methods are functions in chunk hierarchy
        SymbolKind.VARIABLE: "variable",
        SymbolKind.FIELD: "field",
        # External symbols (not chunked)
        SymbolKind.EXTERNAL_MODULE: "module",
        SymbolKind.EXTERNAL_FUNCTION: "function",
        SymbolKind.EXTERNAL_TYPE: "class",
    }

    return mapping.get(symbol_kind, "class")  # Default to "class"
