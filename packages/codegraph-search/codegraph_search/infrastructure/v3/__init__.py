"""
Semantica Hybrid Multi-Index Retriever v3 (S-HMR-v3)

SOTA code search retriever with:
- Multi-label intent classification
- Weighted RRF (rank-based normalization)
- Consensus-aware fusion
- Graph-aware routing
- LTR-ready feature schema
- Async parallel strategy search (v3.1.3+)
"""

from typing import TYPE_CHECKING

from codegraph_search.infrastructure.v3.config import RetrieverV3Config
from codegraph_search.infrastructure.v3.models import (
    ConsensusStats,
    FeatureVector,
    IntentProbability,
    RankedHit,
)
from codegraph_search.infrastructure.v3.types import (
    FusionStrategy,
    IntentType,
    SearchMode,
    SourceType,
)

if TYPE_CHECKING:
    from codegraph_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator
    from codegraph_search.infrastructure.v3.service import RetrieverV3Service


def __getattr__(name: str):
    """Lazy import for heavy service classes."""
    if name == "RetrieverV3Service":
        from codegraph_search.infrastructure.v3.service import RetrieverV3Service

        return RetrieverV3Service
    if name == "RetrieverV3Orchestrator":
        from codegraph_search.infrastructure.v3.orchestrator import RetrieverV3Orchestrator

        return RetrieverV3Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Service & Orchestrator (heavy - lazy import via TYPE_CHECKING)
    "RetrieverV3Service",
    "RetrieverV3Orchestrator",
    # Config & Models (lightweight)
    "RetrieverV3Config",
    "IntentProbability",
    "RankedHit",
    "ConsensusStats",
    "FeatureVector",
    # Types & Enums (SOTA type safety)
    "SourceType",
    "IntentType",
    "FusionStrategy",
    "SearchMode",
]
