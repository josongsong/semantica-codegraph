"""
Query Decomposition & Multi-hop Module (Phase 3 SOTA)

Advanced query processing for complex multi-step searches.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.query.models import (
    DecomposedQuery,
    MultiHopResult,
    QueryStep,
    QueryType,
    StepResult,
)

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.query.decomposer import QueryDecomposer
    from src.contexts.retrieval_search.infrastructure.query.multi_hop import MultiHopRetriever


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "QueryDecomposer":
        from src.contexts.retrieval_search.infrastructure.query.decomposer import QueryDecomposer

        return QueryDecomposer
    if name == "MultiHopRetriever":
        from src.contexts.retrieval_search.infrastructure.query.multi_hop import MultiHopRetriever

        return MultiHopRetriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "QueryType",
    "QueryStep",
    "DecomposedQuery",
    "StepResult",
    "MultiHopResult",
    # Decomposer (heavy - lazy import via TYPE_CHECKING)
    "QueryDecomposer",
    # Multi-hop (heavy - lazy import via TYPE_CHECKING)
    "MultiHopRetriever",
]
