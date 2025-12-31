"""
SOTA Vector Similarity and Memory Scoring

NumPy-optimized implementations for:
- Cosine similarity (10x faster than pure Python)
- Memory scoring (3-axis: Similarity + Recency + Importance)
- Batch operations for efficiency
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from codegraph_runtime.session_memory.domain.models import Episode, MemoryScore

if TYPE_CHECKING:
    from codegraph_runtime.session_memory.infrastructure.config import RetrievalConfig


class VectorSimilarity:
    """
    NumPy-optimized vector similarity operations.

    SOTA: 10x faster than pure Python loop-based implementation.
    """

    @staticmethod
    def cosine_similarity(
        vec1: list[float] | NDArray[np.floating[Any]],
        vec2: list[float] | NDArray[np.floating[Any]],
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Uses NumPy for optimized computation.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity in range [0, 1] (normalized from [-1, 1])
        """
        if not len(vec1) or not len(vec2) or len(vec1) != len(vec2):
            return 0.0

        a = np.asarray(vec1, dtype=np.float64)
        b = np.asarray(vec2, dtype=np.float64)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = float(np.dot(a, b) / (norm_a * norm_b))

        # Normalize from [-1, 1] to [0, 1]
        return (similarity + 1.0) / 2.0

    @staticmethod
    def cosine_similarity_batch(
        query: list[float] | NDArray[np.floating[Any]],
        vectors: list[list[float]] | NDArray[np.floating[Any]],
    ) -> list[float]:
        """
        Calculate cosine similarity between query and multiple vectors.

        Optimized batch operation using matrix multiplication.

        Args:
            query: Query vector
            vectors: List of vectors to compare against

        Returns:
            List of similarity scores
        """
        if not len(query) or not len(vectors):
            return []

        q = np.asarray(query, dtype=np.float64)
        v = np.asarray(vectors, dtype=np.float64)

        # Normalize query
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return [0.0] * len(vectors)
        q_normalized = q / q_norm

        # Normalize vectors (row-wise)
        v_norms = np.linalg.norm(v, axis=1, keepdims=True)
        v_norms[v_norms == 0] = 1.0  # Avoid division by zero
        v_normalized = v / v_norms

        # Dot product with all vectors at once
        similarities = np.dot(v_normalized, q_normalized)

        # Normalize to [0, 1]
        return ((similarities + 1.0) / 2.0).tolist()

    @staticmethod
    def euclidean_distance(
        vec1: list[float] | NDArray[np.floating[Any]],
        vec2: list[float] | NDArray[np.floating[Any]],
    ) -> float:
        """Calculate Euclidean distance between two vectors."""
        if not len(vec1) or not len(vec2) or len(vec1) != len(vec2):
            return float("inf")

        a = np.asarray(vec1, dtype=np.float64)
        b = np.asarray(vec2, dtype=np.float64)

        return float(np.linalg.norm(a - b))

    @staticmethod
    def find_top_k_similar(
        query: list[float],
        vectors: list[list[float]],
        ids: list[str],
        k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[tuple[str, float]]:
        """
        Find top-k most similar vectors to query.

        Args:
            query: Query vector
            vectors: List of candidate vectors
            ids: IDs corresponding to vectors
            k: Number of results to return
            min_similarity: Minimum similarity threshold

        Returns:
            List of (id, similarity) tuples, sorted by similarity descending
        """
        if not vectors or not ids or len(vectors) != len(ids):
            return []

        similarities = VectorSimilarity.cosine_similarity_batch(query, vectors)

        # Pair with IDs and filter by threshold
        results = [(id_, sim) for id_, sim in zip(ids, similarities, strict=False) if sim >= min_similarity]

        # Sort by similarity descending and take top-k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]


class MemoryScoringEngine:
    """
    SOTA Memory Scoring Engine (3-axis).

    Implements Generative Agents style scoring:
    - Similarity: Semantic relevance (embedding-based)
    - Recency: Time decay (exponential)
    - Importance: Intrinsic value (success, retrievals, complexity)
    """

    def __init__(
        self,
        weight_similarity: float = 0.5,
        weight_recency: float = 0.3,
        weight_importance: float = 0.2,
        recency_decay_days: float = 30.0,
    ) -> None:
        """
        Initialize scoring engine.

        Args:
            weight_similarity: Weight for semantic similarity
            weight_recency: Weight for recency score
            weight_importance: Weight for importance score
            recency_decay_days: Half-life for recency decay
        """
        self.w_similarity = weight_similarity
        self.w_recency = weight_recency
        self.w_importance = weight_importance
        self.decay_days = recency_decay_days

    @classmethod
    def from_config(cls, config: RetrievalConfig) -> MemoryScoringEngine:
        """Create from config object."""
        return cls(
            weight_similarity=config.weight_similarity,
            weight_recency=config.weight_recency,
            weight_importance=config.weight_importance,
            recency_decay_days=config.recency_decay_days,
        )

    def score_episode(
        self,
        episode: Episode,
        query_embedding: list[float] | None = None,
        current_time: datetime | None = None,
    ) -> MemoryScore:
        """
        Calculate composite score for an episode.

        Args:
            episode: Episode to score
            query_embedding: Query embedding for similarity
            current_time: Current time for recency calculation

        Returns:
            MemoryScore with all components
        """
        current_time = current_time or datetime.now()

        # 1. Similarity score
        similarity = self._calculate_similarity(episode, query_embedding)

        # 2. Recency score
        recency = self._calculate_recency(episode.created_at, current_time)

        # 3. Importance score
        importance = self._calculate_importance(episode)

        return MemoryScore(
            similarity=similarity,
            recency=recency,
            importance=importance,
            w_similarity=self.w_similarity,
            w_recency=self.w_recency,
            w_importance=self.w_importance,
        )

    def _calculate_similarity(
        self,
        episode: Episode,
        query_embedding: list[float] | None,
    ) -> float:
        """Calculate semantic similarity score."""
        if query_embedding is None or not episode.task_description_embedding:
            return 0.5  # Neutral if no embedding

        return VectorSimilarity.cosine_similarity(
            query_embedding,
            episode.task_description_embedding,
        )

    def _calculate_recency(
        self,
        created_at: datetime,
        current_time: datetime,
    ) -> float:
        """Calculate recency score with exponential decay."""
        age_days = (current_time - created_at).total_seconds() / 86400.0

        # Exponential decay: e^(-age/decay)
        decay = math.exp(-age_days / self.decay_days)

        return max(0.0, min(1.0, decay))

    def _calculate_importance(self, episode: Episode) -> float:
        """
        Calculate importance score from episode attributes.

        Factors:
        - Outcome status (40%): success > partial > failure
        - Retrieval count (30%): frequently accessed = important
        - Usefulness (20%): user feedback
        - Complexity (10%): longer tasks = more valuable
        """
        importance = 0.0

        # 1. Outcome status (0.4)
        status = episode.outcome_status.value
        if status == "success":
            importance += 0.4
        elif status == "partial":
            importance += 0.2

        # 2. Retrieval count (0.3) - normalized to 10 max
        retrieval_score = min(1.0, episode.retrieval_count / 10.0)
        importance += 0.3 * retrieval_score

        # 3. Usefulness (0.2)
        importance += 0.2 * episode.usefulness_score

        # 4. Complexity (0.1) - normalized to 50 steps max
        complexity_score = min(1.0, episode.steps_count / 50.0)
        importance += 0.1 * complexity_score

        return min(1.0, importance)

    def rank_episodes(
        self,
        episodes: list[Episode],
        query_embedding: list[float] | None = None,
        top_k: int = 5,
    ) -> list[tuple[Episode, MemoryScore]]:
        """
        Rank episodes by composite score.

        Args:
            episodes: Episodes to rank
            query_embedding: Query embedding for similarity
            top_k: Number of results

        Returns:
            List of (Episode, MemoryScore) sorted by composite score
        """
        if not episodes:
            return []

        current_time = datetime.now()

        # Score all episodes
        scored = [(ep, self.score_episode(ep, query_embedding, current_time)) for ep in episodes]

        # Sort by composite score descending
        scored.sort(key=lambda x: x[1].composite_score, reverse=True)

        return scored[:top_k]

    def rank_episodes_batch(
        self,
        episodes: list[Episode],
        query_embedding: list[float] | None = None,
        top_k: int = 5,
    ) -> list[tuple[Episode, MemoryScore]]:
        """
        Batch-optimized ranking using NumPy.

        More efficient for large episode lists.
        """
        if not episodes:
            return []

        n = len(episodes)
        current_time = datetime.now()

        # Batch calculate similarity
        if query_embedding and all(ep.task_description_embedding for ep in episodes):
            embeddings = [ep.task_description_embedding for ep in episodes]
            similarities = VectorSimilarity.cosine_similarity_batch(query_embedding, embeddings)
        else:
            similarities = [0.5] * n

        # Calculate recency and importance for all
        recencies = [self._calculate_recency(ep.created_at, current_time) for ep in episodes]
        importances = [self._calculate_importance(ep) for ep in episodes]

        # Build scores
        scored = []
        for i, ep in enumerate(episodes):
            score = MemoryScore(
                similarity=similarities[i],
                recency=recencies[i],
                importance=importances[i],
                w_similarity=self.w_similarity,
                w_recency=self.w_recency,
                w_importance=self.w_importance,
            )
            scored.append((ep, score))

        # Sort and return top-k
        scored.sort(key=lambda x: x[1].composite_score, reverse=True)
        return scored[:top_k]


class AdaptiveScoringEngine(MemoryScoringEngine):
    """
    Adaptive scoring engine that learns from feedback.

    Automatically adjusts weights based on user feedback
    on retrieval usefulness.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with default weights."""
        super().__init__(**kwargs)
        self._feedback_history: list[dict[str, Any]] = []
        self._min_feedback_for_adaptation = 10

    def record_feedback(
        self,
        episode: Episode,
        helpful: bool,
        score: MemoryScore,
    ) -> None:
        """Record feedback for weight adaptation."""
        self._feedback_history.append(
            {
                "episode_id": episode.id,
                "helpful": helpful,
                "similarity": score.similarity,
                "recency": score.recency,
                "importance": score.importance,
            }
        )

        # Trigger adaptation if enough feedback
        if len(self._feedback_history) >= self._min_feedback_for_adaptation:
            self._adapt_weights()

    def _adapt_weights(self) -> None:
        """Adapt weights based on feedback history."""
        recent = self._feedback_history[-self._min_feedback_for_adaptation :]

        helpful = [f for f in recent if f["helpful"]]
        unhelpful = [f for f in recent if not f["helpful"]]

        if not helpful or not unhelpful:
            return

        # Calculate average scores for helpful vs unhelpful
        def avg(items: list[dict[str, Any]], key: str) -> float:
            return sum(f[key] for f in items) / len(items)

        # Difference in each dimension
        diff_sim = abs(avg(helpful, "similarity") - avg(unhelpful, "similarity"))
        diff_rec = abs(avg(helpful, "recency") - avg(unhelpful, "recency"))
        diff_imp = abs(avg(helpful, "importance") - avg(unhelpful, "importance"))

        total_diff = diff_sim + diff_rec + diff_imp
        if total_diff == 0:
            return

        # Update weights proportionally to discriminative power
        self.w_similarity = diff_sim / total_diff
        self.w_recency = diff_rec / total_diff
        self.w_importance = diff_imp / total_diff
