"""
Cross-encoder Reranking

High-quality reranking using cross-encoder models for final precision.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class CrossEncoderPort(Protocol):
    """Protocol for cross-encoder models."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """
        Predict relevance scores for query-document pairs.

        Args:
            pairs: List of (query, document) tuples

        Returns:
            List of relevance scores (higher = more relevant)
        """
        ...


@dataclass
class RerankedChunk:
    """Chunk with reranking score."""

    chunk_id: str
    content: str
    score: float
    reranking_score: float
    metadata: dict


class SimpleCrossEncoder:
    """
    Simple cross-encoder for development/testing.

    In production, this would be replaced with actual cross-encoder model
    (e.g., cross-encoder/ms-marco-MiniLM-L-6-v2).
    """

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """
        Predict relevance scores (simplified).

        Args:
            pairs: List of (query, document) tuples

        Returns:
            List of relevance scores
        """
        scores = []

        for query, doc in pairs:
            # Simple scoring based on token overlap
            query_tokens = set(query.lower().split())
            doc_tokens = set(doc.lower().split())

            # Jaccard similarity
            intersection = len(query_tokens & doc_tokens)
            union = len(query_tokens | doc_tokens)

            if union == 0:
                score = 0.0
            else:
                score = intersection / union

            # Add some variance based on length
            length_factor = min(len(doc) / 1000, 1.0)  # Prefer moderate length
            score = score * (0.7 + 0.3 * length_factor)

            scores.append(score)

        return scores


class CrossEncoderReranker:
    """
    Cross-encoder reranker for final precision.

    Pipeline (from 실행안):
    Fast Retrieval (1000 candidates)
      ↓
    Fusion (Top 100)
      ↓
    Late Interaction (Top 50) ← Phase 2
      ↓
    Cross-encoder Reranking (Top 20) ← Phase 2
      ↓
    Context Builder
    """

    def __init__(
        self,
        cross_encoder: CrossEncoderPort | None = None,
        use_late_interaction: bool = True,
    ):
        """
        Initialize cross-encoder reranker.

        Args:
            cross_encoder: Cross-encoder model
            use_late_interaction: Whether to use late interaction before reranking
        """
        self.cross_encoder = cross_encoder or SimpleCrossEncoder()
        self.use_late_interaction = use_late_interaction

        if use_late_interaction:
            from .late_interaction import LateInteractionSearch

            self.late_interaction = LateInteractionSearch()
        else:
            self.late_interaction = None

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 20,
        late_interaction_k: int = 50,
    ) -> list[RerankedChunk]:
        """
        Rerank candidates using multi-stage pipeline.

        Args:
            query: User query
            candidates: List of candidate chunks (top 100 from fusion)
            top_k: Final number of results (default: 20)
            late_interaction_k: Number of candidates for late interaction (default: 50)

        Returns:
            List of RerankedChunk sorted by reranking score
        """
        if not candidates:
            return []

        # Stage 1: Late Interaction (Top 100 → Top 50)
        if self.use_late_interaction and self.late_interaction:
            logger.debug(f"Stage 1: Late interaction ({len(candidates)} → {late_interaction_k})")

            late_results = self.late_interaction.search(query, candidates, top_k=late_interaction_k)

            # Convert back to dict format for next stage
            candidates_for_ce = [
                {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "score": chunk.score,  # Late interaction score
                    "metadata": chunk.metadata,
                }
                for chunk in late_results
            ]
        else:
            candidates_for_ce = candidates[:late_interaction_k]

        # Stage 2: Cross-encoder (Top 50 → Top 20)
        logger.debug(f"Stage 2: Cross-encoder ({len(candidates_for_ce)} → {top_k})")

        # Prepare query-document pairs
        pairs = [(query, candidate.get("content", "")) for candidate in candidates_for_ce]

        # Predict relevance scores
        ce_scores = self.cross_encoder.predict(pairs)

        # Create reranked chunks
        reranked = []
        for candidate, ce_score in zip(candidates_for_ce, ce_scores):
            chunk = RerankedChunk(
                chunk_id=candidate.get("chunk_id", ""),
                content=candidate.get("content", ""),
                score=candidate.get("score", 0.0),  # Original/Late interaction score
                reranking_score=ce_score,
                metadata=candidate.get("metadata", {}),
            )
            reranked.append(chunk)

        # Sort by cross-encoder score
        reranked.sort(key=lambda x: x.reranking_score, reverse=True)

        # Return top K
        result = reranked[:top_k]

        logger.info(
            f"Reranking complete: {len(candidates)} → {len(result)} chunks "
            f"(avg CE score: {np.mean([c.reranking_score for c in result]):.3f})"
        )

        return result

    def rerank_simple(self, query: str, candidates: list[dict], top_k: int = 20) -> list[dict]:
        """
        Simple reranking without late interaction (for backward compatibility).

        Args:
            query: User query
            candidates: List of candidate chunks
            top_k: Number of top results

        Returns:
            List of reranked chunks as dicts
        """
        reranked_chunks = self.rerank(
            query=query,
            candidates=candidates,
            top_k=top_k,
            late_interaction_k=min(len(candidates), 50),
        )

        # Convert back to dict format
        return [
            {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "score": chunk.reranking_score,
                "original_score": chunk.score,
                "metadata": chunk.metadata,
            }
            for chunk in reranked_chunks
        ]
