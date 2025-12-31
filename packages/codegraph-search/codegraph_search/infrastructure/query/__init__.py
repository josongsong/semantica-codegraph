"""
Query Decomposition & Multi-hop Module (Phase 3 SOTA)

Advanced query processing for complex multi-step searches.
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.query.models import (
    DecomposedQuery,
    MultiHopResult,
    QueryStep,
    QueryType,
    StepResult,
)

if TYPE_CHECKING:
    from codegraph_search.infrastructure.query.decomposer import QueryDecomposer
    from codegraph_search.infrastructure.query.hyde import HyDEGenerator, HyDEQueryProcessor
    from codegraph_search.infrastructure.query.multi_hop import MultiHopRetriever
    from codegraph_search.infrastructure.query.multi_query import (
        MultiQueryGenerator,
        MultiQueryRetriever,
    )


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "QueryDecomposer":
        from codegraph_search.infrastructure.query.decomposer import QueryDecomposer

        return QueryDecomposer
    if name == "MultiHopRetriever":
        from codegraph_search.infrastructure.query.multi_hop import MultiHopRetriever

        return MultiHopRetriever
    if name == "HyDEGenerator":
        from codegraph_search.infrastructure.query.hyde import HyDEGenerator

        return HyDEGenerator
    if name == "HyDEQueryProcessor":
        from codegraph_search.infrastructure.query.hyde import HyDEQueryProcessor

        return HyDEQueryProcessor
    if name == "MultiQueryGenerator":
        from codegraph_search.infrastructure.query.multi_query import MultiQueryGenerator

        return MultiQueryGenerator
    if name == "MultiQueryRetriever":
        from codegraph_search.infrastructure.query.multi_query import MultiQueryRetriever

        return MultiQueryRetriever
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
    # HyDE (SOTA 2024)
    "HyDEGenerator",
    "HyDEQueryProcessor",
    # RAG-Fusion (SOTA 2024)
    "MultiQueryGenerator",
    "MultiQueryRetriever",
]
