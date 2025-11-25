"""
Semantica Hybrid Multi-Index Retriever v3 (S-HMR-v3)

SOTA code search retriever with:
- Multi-label intent classification
- Weighted RRF (rank-based normalization)
- Consensus-aware fusion
- Graph-aware routing
- LTR-ready feature schema
"""

from .config import RetrieverV3Config
from .models import ConsensusStats, FeatureVector, IntentProbability, RankedHit
from .service import RetrieverV3Service

__all__ = [
    "RetrieverV3Service",
    "RetrieverV3Config",
    "IntentProbability",
    "RankedHit",
    "ConsensusStats",
    "FeatureVector",
]
