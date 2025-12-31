"""
Code Foundation Bounded Context

코드 분석의 기초: AST, IR, Graph, Chunk, Query DSL

Note: Uses lazy imports to avoid circular import issues.
"""

from typing import TYPE_CHECKING


# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name in ("ASTDocument", "Chunk", "IRDocument", "Language", "Reference", "Symbol"):
        from .domain import (
            ASTDocument,
            Chunk,
            IRDocument,
            Language,
            Reference,
            Symbol,
        )

        return locals()[name]

    if name in ("E", "Q"):
        from .domain.query import E, Q

        return locals()[name]

    if name in ("GraphDocument", "GraphEdge", "GraphNode"):
        from .infrastructure.graph.models import GraphDocument, GraphEdge, GraphNode

        return locals()[name]

    if name == "QueryEngine":
        from .infrastructure.query import QueryEngine

        return QueryEngine

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # IR & Graph
    "ASTDocument",
    "Chunk",
    "GraphDocument",
    "GraphEdge",
    "GraphNode",
    "IRDocument",
    "Language",
    "Reference",
    "Symbol",
    # Query DSL
    "Q",
    "E",
    "QueryEngine",
]
