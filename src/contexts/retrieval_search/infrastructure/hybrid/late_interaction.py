"""
Late Interaction Search (ColBERT-style)

Fine-grained token-level matching between query and documents.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from src.common.observability import get_logger

logger = get_logger(__name__)


class EmbeddingModelPort(Protocol):
    """Protocol for embedding models that support token-level embeddings."""

    def encode_query(self, text: str) -> np.ndarray:
        """
        Encode query into token embeddings.

        Args:
            text: Query text

        Returns:
            Array of shape (num_query_tokens, embedding_dim)
        """
        ...

    def encode_document(self, text: str) -> np.ndarray:
        """
        Encode document into token embeddings.

        Args:
            text: Document text

        Returns:
            Array of shape (num_doc_tokens, embedding_dim)
        """
        ...


@dataclass
class ScoredChunk:
    """Chunk with late interaction score."""

    chunk_id: str
    content: str
    score: float
    max_sims: list[float]  # Individual MaxSim scores per query token
    metadata: dict


class SimpleEmbeddingModel:
    """
    Simple embedding model for development/testing.

    DEPRECATED: Phase 3 Day 26-28
    Use BGEEmbeddingModel instead for production.
    """

    def __init__(self, embedding_dim: int = 128):
        """
        Initialize simple embedding model.

        Args:
            embedding_dim: Embedding dimension
        """
        self.embedding_dim = embedding_dim
        logger.warning(
            "simple_embedding_model_deprecated",
            message="SimpleEmbeddingModel uses random embeddings. Use BGEEmbeddingModel for production.",
        )

    def encode_query(self, text: str) -> np.ndarray:
        """Encode query (random embeddings - for testing only)."""
        tokens = text.lower().split()
        embeddings = []
        for token in tokens:
            np.random.seed(hash(token) % (2**32))
            emb = np.random.randn(self.embedding_dim)
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            embeddings.append(emb)
        if not embeddings:
            embeddings = [np.zeros(self.embedding_dim)]
        return np.array(embeddings)

    def encode_document(self, text: str) -> np.ndarray:
        """Encode document (random embeddings - for testing only)."""
        tokens = text.lower().split()[:100]
        embeddings = []
        for token in tokens:
            np.random.seed(hash(token) % (2**32))
            emb = np.random.randn(self.embedding_dim)
            emb = emb / (np.linalg.norm(emb) + 1e-8)
            embeddings.append(emb)
        if not embeddings:
            embeddings = [np.zeros(self.embedding_dim)]
        return np.array(embeddings)


class LateInteractionSearch:
    """
    Late Interaction Search using ColBERT-style MaxSim.

    Query token과 document token 간 fine-grained matching을 수행합니다.

    Pipeline (from 실행안):
    Query
      ↓
    Fast Retrieval (1000 candidates) - BM25/ANN
      ↓
    Fusion (Top 100)
      ↓
    Late Interaction (Top 50) ← Phase 2
      ↓
    Cross-encoder Reranking (Top 20) ← Phase 2
      ↓
    Context Builder
    """

    def __init__(self, embedding_model: EmbeddingModelPort | None = None):
        """
        Initialize late interaction search.

        Args:
            embedding_model: Embedding model for token-level embeddings
                            Default: SimpleEmbeddingModel (deprecated, use BGEEmbeddingModel)
        """
        if embedding_model is None:
            # Phase 3: Default to SimpleEmbeddingModel for backward compatibility
            # Production should provide BGEEmbeddingModel
            logger.warning(
                "using_simple_embedding_model",
                message="Using SimpleEmbeddingModel (random). Provide BGEEmbeddingModel for production.",
            )
            embedding_model = SimpleEmbeddingModel()

        self.embedding_model = embedding_model

    def search(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 50,
    ) -> list[ScoredChunk]:
        """
        Re-rank candidates using late interaction.

        Args:
            query: User query
            candidates: List of candidate chunks (dicts with 'chunk_id', 'content')
            top_k: Number of top results to return

        Returns:
            List of ScoredChunk sorted by late interaction score
        """
        if not candidates:
            return []

        # Encode query into token embeddings
        query_embeddings = self.embedding_model.encode_query(query)
        # Shape: (num_query_tokens, embedding_dim)

        logger.debug(f"Late interaction: query → {query_embeddings.shape[0]} tokens (dim={query_embeddings.shape[1]})")

        # Score each candidate
        scored_chunks = []

        for candidate in candidates:
            chunk_id = candidate.get("chunk_id", "")
            content = candidate.get("content", "")

            if not content:
                continue

            # Encode document into token embeddings
            # In production, these would be pre-computed and cached
            doc_embeddings = self.embedding_model.encode_document(content)
            # Shape: (num_doc_tokens, embedding_dim)

            # Compute MaxSim score
            score, max_sims = self._compute_maxsim(query_embeddings, doc_embeddings)

            scored_chunk = ScoredChunk(
                chunk_id=chunk_id,
                content=content,
                score=score,
                max_sims=max_sims,
                metadata=candidate.get("metadata", {}),
            )

            scored_chunks.append(scored_chunk)

        # Sort by score (descending)
        scored_chunks.sort(key=lambda x: x.score, reverse=True)

        # Return top K
        result = scored_chunks[:top_k]

        logger.info(
            f"Late interaction: {len(candidates)} → {len(result)} chunks "
            f"(avg score: {np.mean([c.score for c in result]):.3f})"
        )

        return result

    def _compute_maxsim(self, query_embeddings: np.ndarray, doc_embeddings: np.ndarray) -> tuple[float, list[float]]:
        """
        Compute MaxSim score (ColBERT-style).

        For each query token, find the maximum similarity with any document token,
        then sum all maximum similarities.

        Args:
            query_embeddings: Query token embeddings (num_query_tokens, dim)
            doc_embeddings: Document token embeddings (num_doc_tokens, dim)

        Returns:
            Tuple of (total_score, max_sims_per_query_token)
        """
        # Compute pairwise cosine similarities
        # Shape: (num_query_tokens, num_doc_tokens)
        similarities = np.dot(query_embeddings, doc_embeddings.T)

        # For each query token, find max similarity with any doc token
        max_sims = np.max(similarities, axis=1)  # Shape: (num_query_tokens,)

        # Sum all max similarities
        total_score = float(np.sum(max_sims))

        return total_score, max_sims.tolist()

    def get_cache_key(self, chunk_id: str) -> str:
        """
        Get cache key for pre-computed document embeddings.

        In production, document embeddings would be cached to avoid
        re-encoding during retrieval.

        Args:
            chunk_id: Chunk identifier

        Returns:
            Cache key for embeddings
        """
        return f"late_interaction:embeddings:{chunk_id}"
