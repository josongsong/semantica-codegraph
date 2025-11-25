"""
Cross-encoder Reranker for Final Top-10

Uses cross-encoder models for final reranking of top candidates.

Cross-encoder vs Bi-encoder:
- Bi-encoder: Encode query and document separately, compute similarity
  - Fast (can pre-compute document embeddings)
  - Lower quality (no cross-attention)
- Cross-encoder: Encode query+document together, predict relevance
  - Slow (must encode each pair)
  - Higher quality (full cross-attention)

Strategy:
- Use bi-encoder for initial retrieval (fast)
- Use cross-encoder only for top-10 final ranking (slow but high quality)

Expected improvement: NDCG@10 +15%, MRR +20%

Latency:
- Bi-encoder: 50ms for top-100
- Cross-encoder: 100ms for top-10
- Total: 150ms (acceptable for high quality)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CrossEncoderScore:
    """Cross-encoder relevance score."""

    score: float  # Relevance score (0-1)
    confidence: float  # Model confidence
    latency_ms: float  # Inference latency


class CrossEncoderReranker:
    """
    Cross-encoder reranker for final top-k.

    Uses models like:
    - ms-marco-MiniLM-L-12-v2
    - cross-encoder/ms-marco-TinyBERT-L-6-v2
    - Custom fine-tuned models

    Only for top-10 to balance quality and latency.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        batch_size: int = 10,
        max_length: int = 512,
    ):
        """
        Initialize cross-encoder reranker.

        Args:
            model_name: Model name or path
            device: Device ('cpu', 'cuda', 'mps')
            batch_size: Batch size for inference
            max_length: Max input length (tokens)
        """
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.max_length = max_length

        # Load model (lazy loading)
        self.model = None
        self._load_model()

    def _load_model(self) -> None:
        """Load cross-encoder model."""
        try:
            from sentence_transformers import CrossEncoder

            logger.info(
                f"Loading cross-encoder model: {self.model_name} on {self.device}"
            )

            self.model = CrossEncoder(
                self.model_name,
                max_length=self.max_length,
                device=self.device,
            )

            logger.info(f"Cross-encoder model loaded: {self.model_name}")

        except ImportError:
            logger.warning(
                "sentence-transformers not available, using fallback heuristic"
            )
            self.model = None
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model: {e}")
            self.model = None

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Rerank candidates using cross-encoder.

        Args:
            query: User query
            candidates: Candidate chunks
            top_k: Number of candidates to rerank (should be small, e.g., 10-20)

        Returns:
            Reranked candidates
        """
        if not candidates:
            return []

        if len(candidates) > top_k:
            logger.warning(
                f"Cross-encoder called with {len(candidates)} candidates, "
                f"but designed for top-{top_k}. Consider using lighter reranker first."
            )

        start_time = time.time()

        # Limit to top_k to avoid excessive latency
        candidates_to_rerank = candidates[:top_k]

        logger.info(
            f"Cross-encoder reranking {len(candidates_to_rerank)} candidates"
        )

        if self.model is None:
            # Fallback: use existing scores
            logger.warning("Cross-encoder not available, using fallback")
            return candidates_to_rerank

        # Prepare input pairs
        pairs = []
        for candidate in candidates_to_rerank:
            content = candidate.get("content", "")
            # Truncate content if too long
            content = content[:2000]  # Rough char limit
            pairs.append([query, content])

        # Batch inference
        try:
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )

            # scores is numpy array of floats
            scores = scores.tolist()

        except Exception as e:
            logger.error(f"Cross-encoder prediction failed: {e}")
            # Fallback to original scores
            scores = [c.get("score", 0.0) for c in candidates_to_rerank]

        # Add cross-encoder scores to candidates
        for i, candidate in enumerate(candidates_to_rerank):
            cross_score = scores[i]

            # Normalize to [0, 1] (cross-encoder outputs can vary)
            # MS-MARCO models output [-10, 10], normalize
            cross_score_normalized = self._normalize_score(cross_score)

            candidate["cross_encoder_score"] = cross_score_normalized

            # Blend with original score (80% cross-encoder, 20% original)
            original_score = candidate.get("score", 0.0)
            candidate["final_score"] = (
                0.8 * cross_score_normalized + 0.2 * original_score
            )

        # Sort by final score
        reranked = sorted(
            candidates_to_rerank,
            key=lambda c: c["final_score"],
            reverse=True,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"Cross-encoder reranking complete: {elapsed_ms:.0f}ms")

        return reranked

    def _normalize_score(self, score: float) -> float:
        """
        Normalize cross-encoder score to [0, 1].

        Different models have different output ranges:
        - MS-MARCO models: typically [-10, 10]
        - Custom models: may vary

        Args:
            score: Raw score

        Returns:
            Normalized score [0, 1]
        """
        # Sigmoid normalization (works for most ranges)
        normalized = 1.0 / (1.0 + np.exp(-score))
        return float(normalized)

    def predict_batch(
        self, query_document_pairs: list[tuple[str, str]]
    ) -> list[float]:
        """
        Predict scores for query-document pairs (batch).

        Args:
            query_document_pairs: List of (query, document) tuples

        Returns:
            List of relevance scores
        """
        if self.model is None:
            return [0.5] * len(query_document_pairs)

        try:
            scores = self.model.predict(
                query_document_pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
            return [self._normalize_score(s) for s in scores.tolist()]
        except Exception as e:
            logger.error(f"Batch prediction failed: {e}")
            return [0.5] * len(query_document_pairs)


class CachedCrossEncoderReranker:
    """
    Cached cross-encoder with query-document pair caching.

    Cross-encoder is expensive, so cache (query, doc) → score mappings.
    """

    def __init__(
        self,
        reranker: CrossEncoderReranker,
        cache_size: int = 10000,
        ttl_hours: int = 24,
    ):
        """
        Initialize cached cross-encoder.

        Args:
            reranker: Base cross-encoder reranker
            cache_size: Max cache entries
            ttl_hours: Cache TTL in hours
        """
        self.reranker = reranker
        self.cache_size = cache_size
        self.ttl_hours = ttl_hours

        # In-memory cache
        from collections import OrderedDict

        self.cache: OrderedDict[str, tuple[float, float]] = OrderedDict()
        # key: hash(query, content), value: (score, timestamp)

        self.hits = 0
        self.misses = 0

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Rerank with caching.

        Args:
            query: User query
            candidates: Candidate chunks
            top_k: Number to rerank

        Returns:
            Reranked candidates
        """
        candidates_to_rerank = candidates[:top_k]

        # Check cache
        cached_scores = []
        uncached_candidates = []

        for candidate in candidates_to_rerank:
            content = candidate.get("content", "")[:2000]
            cache_key = self._get_cache_key(query, content)

            if cache_key in self.cache:
                score, timestamp = self.cache[cache_key]

                # Check TTL
                import time

                age_hours = (time.time() - timestamp) / 3600
                if age_hours < self.ttl_hours:
                    candidate["cross_encoder_score"] = score
                    cached_scores.append(candidate)
                    self.hits += 1
                    continue

            # Cache miss
            uncached_candidates.append(candidate)
            self.misses += 1

        # Score uncached candidates
        if uncached_candidates:
            scored_uncached = await self.reranker.rerank(
                query, uncached_candidates, top_k=len(uncached_candidates)
            )

            # Add to cache
            import time

            for candidate in scored_uncached:
                content = candidate.get("content", "")[:2000]
                cache_key = self._get_cache_key(query, content)
                score = candidate["cross_encoder_score"]
                self.cache[cache_key] = (score, time.time())

                # LRU eviction
                if len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)

            cached_scores.extend(scored_uncached)

        # Compute final scores
        for candidate in cached_scores:
            cross_score = candidate["cross_encoder_score"]
            original_score = candidate.get("score", 0.0)
            candidate["final_score"] = 0.8 * cross_score + 0.2 * original_score

        # Sort by final score
        reranked = sorted(
            cached_scores, key=lambda c: c["final_score"], reverse=True
        )

        cache_hit_rate = (
            self.hits / (self.hits + self.misses)
            if (self.hits + self.misses) > 0
            else 0.0
        )
        logger.info(
            f"Cross-encoder cache: {self.hits} hits, {self.misses} misses "
            f"(hit rate: {cache_hit_rate:.1%})"
        )

        return reranked

    def _get_cache_key(self, query: str, content: str) -> str:
        """Get cache key for (query, content) pair."""
        import hashlib

        combined = f"{query}|{content}"
        return hashlib.md5(combined.encode()).hexdigest()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        hit_rate = (
            self.hits / (self.hits + self.misses)
            if (self.hits + self.misses) > 0
            else 0.0
        )
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "cache_size": len(self.cache),
            "max_cache_size": self.cache_size,
        }


class HybridFinalReranker:
    """
    Hybrid final reranker combining multiple strategies.

    Pipeline:
    1. Learned reranker (top-50 → top-20)
    2. LLM reranker (top-20 → top-15, optional)
    3. Cross-encoder (top-15 → top-10, final)

    This cascading approach balances quality and latency.
    """

    def __init__(
        self,
        learned_reranker: Any | None = None,
        llm_reranker: Any | None = None,
        cross_encoder: CrossEncoderReranker | None = None,
    ):
        """
        Initialize hybrid final reranker.

        Args:
            learned_reranker: Learned lightweight reranker
            llm_reranker: LLM reranker (optional)
            cross_encoder: Cross-encoder reranker
        """
        self.learned_reranker = learned_reranker
        self.llm_reranker = llm_reranker
        self.cross_encoder = cross_encoder

    async def rerank(
        self, query: str, candidates: list[dict[str, Any]], top_k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Multi-stage reranking pipeline.

        Args:
            query: User query
            candidates: Candidate chunks
            top_k: Final number of results

        Returns:
            Reranked candidates
        """
        current_candidates = candidates

        # Stage 1: Learned reranker (fast, top-50 → top-20)
        if self.learned_reranker and len(current_candidates) > 20:
            logger.info("Stage 1: Learned reranker")
            current_candidates = self.learned_reranker.rerank(
                query, current_candidates, top_k=20
            )

        # Stage 2: LLM reranker (optional, top-20 → top-15)
        if self.llm_reranker and len(current_candidates) > 15:
            logger.info("Stage 2: LLM reranker")
            current_candidates = await self.llm_reranker.rerank(
                query, current_candidates
            )
            current_candidates = current_candidates[:15]

        # Stage 3: Cross-encoder (final, top-15 → top-10)
        if self.cross_encoder:
            logger.info("Stage 3: Cross-encoder reranker (final)")
            final_candidates = await self.cross_encoder.rerank(
                query, current_candidates, top_k=top_k
            )
        else:
            final_candidates = current_candidates[:top_k]

        logger.info(
            f"Hybrid final reranking: {len(candidates)} → {len(final_candidates)} chunks"
        )

        return final_candidates


# Example usage
def example_usage():
    """Example usage of cross-encoder reranker."""

    # Initialize cross-encoder
    reranker = CrossEncoderReranker(
        model_name="cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu"
    )

    # Mock candidates
    candidates = [
        {
            "chunk_id": "A",
            "content": "User authentication with JWT tokens",
            "score": 0.8,
        },
        {
            "chunk_id": "B",
            "content": "Database connection pooling",
            "score": 0.75,
        },
        {
            "chunk_id": "C",
            "content": "User login and session management",
            "score": 0.7,
        },
    ]

    # Rerank
    query = "how to authenticate users"
    reranked = asyncio.run(reranker.rerank(query, candidates, top_k=3))

    print("Reranked results:")
    for i, chunk in enumerate(reranked):
        print(
            f"  {i+1}. {chunk['chunk_id']}: "
            f"cross_encoder={chunk.get('cross_encoder_score', 0):.3f}, "
            f"final={chunk.get('final_score', 0):.3f}"
        )
