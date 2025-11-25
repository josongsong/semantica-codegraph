"""
Graph-First Helper Functions for ChunkBuilder

This module contains helper functions for the Graph-First chunk building strategy,
where GraphDocument is the single source of truth for semantic kinds.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..graph.models import GraphNodeKind


def map_graph_kind_to_chunk_kind(graph_kind: "GraphNodeKind") -> str:
    """
    Map GraphNodeKind to Chunk kind string.

    Graph-First Strategy: GraphDocument determines semantic type,
    Chunk layer only performs conversion.

    Args:
        graph_kind: Graph node kind from GraphDocument

    Returns:
        Chunk kind string ("class", "service", "repository", etc.)
    """
    from ..graph.models import GraphNodeKind

    # Extended kinds (Phase 3)
    if graph_kind == GraphNodeKind.SERVICE:
        return "service"
    elif graph_kind == GraphNodeKind.REPOSITORY:
        return "repository"
    elif graph_kind == GraphNodeKind.ROUTE:
        return "route"
    elif graph_kind == GraphNodeKind.CONFIG:
        return "config"
    elif graph_kind == GraphNodeKind.JOB:
        return "job"
    elif graph_kind == GraphNodeKind.MIDDLEWARE:
        return "middleware"

    # Standard kinds
    elif graph_kind == GraphNodeKind.CLASS:
        return "class"
    elif graph_kind in (GraphNodeKind.FUNCTION, GraphNodeKind.METHOD):
        return "function"
    elif graph_kind == GraphNodeKind.FILE:
        return "file"
    elif graph_kind == GraphNodeKind.MODULE:
        return "module"

    # Fallback
    else:
        return "class"  # Safe default for unknown types
