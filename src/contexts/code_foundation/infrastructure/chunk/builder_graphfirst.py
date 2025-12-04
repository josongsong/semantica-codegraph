"""
Graph-First Helper Functions for ChunkBuilder

This module contains helper functions for the Graph-First chunk building strategy,
where GraphDocument is the single source of truth for semantic kinds.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import GraphNodeKind


# Lazy-initialized mapping dict (avoids import at module load time)
_GRAPH_KIND_TO_CHUNK_KIND: dict["GraphNodeKind", str] | None = None


def _get_mapping() -> dict["GraphNodeKind", str]:
    """Get or initialize the GraphNodeKind to chunk kind mapping."""
    global _GRAPH_KIND_TO_CHUNK_KIND
    if _GRAPH_KIND_TO_CHUNK_KIND is None:
        from src.contexts.code_foundation.infrastructure.graph.models import GraphNodeKind

        _GRAPH_KIND_TO_CHUNK_KIND = {
            # Extended kinds (Phase 3)
            GraphNodeKind.SERVICE: "service",
            GraphNodeKind.REPOSITORY: "repository",
            GraphNodeKind.ROUTE: "route",
            GraphNodeKind.CONFIG: "config",
            GraphNodeKind.JOB: "job",
            GraphNodeKind.MIDDLEWARE: "middleware",
            # Standard kinds
            GraphNodeKind.CLASS: "class",
            GraphNodeKind.FUNCTION: "function",
            GraphNodeKind.METHOD: "function",
            GraphNodeKind.FILE: "file",
            GraphNodeKind.MODULE: "module",
        }
    return _GRAPH_KIND_TO_CHUNK_KIND


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
    return _get_mapping().get(graph_kind, "class")  # "class" as safe default
