"""
Graph Construction Layer

Unified graph representation for code analysis.
Converts Structural IR + Semantic IR into GraphDocument.
"""

from .builder import GraphBuilder
from .models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphIndex,
    GraphNode,
    GraphNodeKind,
)

__all__ = [
    # Builder
    "GraphBuilder",
    # Models
    "GraphNode",
    "GraphNodeKind",
    "GraphEdge",
    "GraphEdgeKind",
    "GraphIndex",
    "GraphDocument",
]
