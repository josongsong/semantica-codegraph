"""
Hybrid Search Module (Phase 2 SOTA)

Advanced search techniques including Late Interaction and Cross-encoder Reranking.
"""

from .late_interaction import EmbeddingModelPort, LateInteractionSearch, ScoredChunk
from .reranker import CrossEncoderPort, CrossEncoderReranker, RerankedChunk

__all__ = [
    # Late Interaction
    "LateInteractionSearch",
    "ScoredChunk",
    "EmbeddingModelPort",
    # Reranking
    "CrossEncoderReranker",
    "RerankedChunk",
    "CrossEncoderPort",
]
