"""
Hybrid Search Module (Phase 2 SOTA)

Advanced search techniques including Late Interaction and Cross-encoder Reranking.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.hybrid.reranker import CrossEncoderPort, RerankedChunk

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.hybrid.cross_encoder_reranker import CrossEncoderReranker
    from src.contexts.retrieval_search.infrastructure.hybrid.late_interaction import (
        EmbeddingModelPort,
        LateInteractionSearch,
        ScoredChunk,
    )


def __getattr__(name: str):
    """Lazy import for ML model classes."""
    if name == "CrossEncoderReranker":
        from src.contexts.retrieval_search.infrastructure.hybrid.cross_encoder_reranker import CrossEncoderReranker

        return CrossEncoderReranker
    if name == "LateInteractionSearch":
        from src.contexts.retrieval_search.infrastructure.hybrid.late_interaction import LateInteractionSearch

        return LateInteractionSearch
    if name == "ScoredChunk":
        from src.contexts.retrieval_search.infrastructure.hybrid.late_interaction import ScoredChunk

        return ScoredChunk
    if name == "EmbeddingModelPort":
        from src.contexts.retrieval_search.infrastructure.hybrid.late_interaction import EmbeddingModelPort

        return EmbeddingModelPort
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Late Interaction (ML models - lazy import)
    "LateInteractionSearch",
    "ScoredChunk",
    "EmbeddingModelPort",
    # Reranking (ML models - lazy import)
    "CrossEncoderReranker",
    "RerankedChunk",
    "CrossEncoderPort",
]
