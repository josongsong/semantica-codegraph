"""
Query Decomposition & Multi-hop Module (Phase 3 SOTA)

Advanced query processing for complex multi-step searches.
"""

from .decomposer import QueryDecomposer
from .models import DecomposedQuery, MultiHopResult, QueryStep, QueryType, StepResult
from .multi_hop import MultiHopRetriever

__all__ = [
    # Models
    "QueryType",
    "QueryStep",
    "DecomposedQuery",
    "StepResult",
    "MultiHopResult",
    # Decomposer
    "QueryDecomposer",
    # Multi-hop
    "MultiHopRetriever",
]
