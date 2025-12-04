"""
Cross-encoder Reranking

High-quality reranking using cross-encoder models for final precision.
"""

from dataclasses import dataclass
from typing import Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)


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


# NOTE: CrossEncoderReranker has been moved to cross_encoder_reranker.py
# This file now only contains the Protocol, dataclass, and SimpleCrossEncoder for testing.
# Import CrossEncoderReranker from cross_encoder_reranker.py instead.
