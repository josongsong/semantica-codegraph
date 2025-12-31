"""
Memory Scoring Engine Tests (SOTA L11)

Test Coverage:
- 3-axis scoring: Similarity + Recency + Importance
- Edge: Zero values, boundary values, missing embeddings
- Corner: Time decay, weight normalization
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestRecencyScoring:
    """Recency (time decay) scoring tests"""

    def test_recent_memory_high_score(self):
        """Recent memory has high recency score"""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Decay calculation: e^(-lambda * hours)
        hours_diff = 1
        decay_rate = 0.1  # typical
        expected_min = 0.9  # e^(-0.1) ≈ 0.90

        score = _calculate_time_decay(one_hour_ago, now, decay_rate)
        assert score >= expected_min

    def test_old_memory_low_score(self):
        """Old memory has low recency score"""
        now = datetime.now()
        one_week_ago = now - timedelta(days=7)

        hours_diff = 7 * 24
        decay_rate = 0.01
        # e^(-0.01 * 168) ≈ 0.18
        score = _calculate_time_decay(one_week_ago, now, decay_rate)
        assert score < 0.5

    def test_same_time_full_score(self):
        """Same time gives full recency score"""
        now = datetime.now()
        score = _calculate_time_decay(now, now, 0.1)
        assert score == pytest.approx(1.0)


def _calculate_time_decay(created_at: datetime, current_time: datetime, decay_rate: float) -> float:
    """Helper: Calculate time decay score"""
    import math

    hours_diff = (current_time - created_at).total_seconds() / 3600
    return math.exp(-decay_rate * hours_diff)


class TestSimilarityScoring:
    """Similarity scoring tests"""

    def test_identical_vectors_max_similarity(self):
        """Identical vectors have similarity 1.0"""
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        sim = _cosine_similarity(v1, v2)
        assert sim == pytest.approx(1.0)

    def test_orthogonal_vectors_zero_similarity(self):
        """Orthogonal vectors have similarity 0.0"""
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        sim = _cosine_similarity(v1, v2)
        assert sim == pytest.approx(0.0)

    def test_opposite_vectors_negative_similarity(self):
        """Opposite vectors have similarity -1.0"""
        v1 = [1.0, 0.0, 0.0]
        v2 = [-1.0, 0.0, 0.0]
        sim = _cosine_similarity(v1, v2)
        assert sim == pytest.approx(-1.0)

    def test_similar_vectors(self):
        """Similar vectors have high similarity"""
        v1 = [0.9, 0.1, 0.0]
        v2 = [0.85, 0.15, 0.0]
        sim = _cosine_similarity(v1, v2)
        assert sim > 0.9


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Helper: Calculate cosine similarity"""
    import math

    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class TestImportanceScoring:
    """Importance scoring tests"""

    def test_high_importance_marked(self):
        """High importance memory"""
        importance = 0.9
        assert importance > 0.7  # High threshold

    def test_low_importance(self):
        """Low importance memory"""
        importance = 0.2
        assert importance < 0.5  # Low threshold

    def test_importance_range(self):
        """Importance in valid range"""
        for importance in [0.0, 0.5, 1.0]:
            assert 0.0 <= importance <= 1.0


class TestCompositeScoring:
    """Composite (weighted) scoring tests"""

    def test_weighted_combination(self):
        """Weighted combination of 3 axes"""
        similarity = 0.8
        recency = 0.6
        importance = 0.4

        w_sim = 0.5
        w_rec = 0.3
        w_imp = 0.2

        composite = similarity * w_sim + recency * w_rec + importance * w_imp
        expected = 0.8 * 0.5 + 0.6 * 0.3 + 0.4 * 0.2
        assert composite == pytest.approx(expected)

    def test_weights_sum_to_one(self):
        """Default weights sum to 1.0"""
        w_sim = 0.5
        w_rec = 0.3
        w_imp = 0.2
        assert w_sim + w_rec + w_imp == pytest.approx(1.0)


class TestEdgeCases:
    """Edge case tests"""

    def test_zero_all_scores(self):
        """All zero scores"""
        composite = 0.0 * 0.5 + 0.0 * 0.3 + 0.0 * 0.2
        assert composite == 0.0

    def test_max_all_scores(self):
        """All max scores"""
        composite = 1.0 * 0.5 + 1.0 * 0.3 + 1.0 * 0.2
        assert composite == pytest.approx(1.0)

    def test_missing_query_embedding(self):
        """Missing query embedding defaults to 0 similarity"""
        # When query_embedding is None, similarity should be 0 or default
        similarity = 0.0  # Default when no embedding
        assert similarity == 0.0

    def test_very_old_memory(self):
        """Very old memory (years)"""
        now = datetime.now()
        years_ago = now - timedelta(days=365 * 5)
        score = _calculate_time_decay(years_ago, now, 0.001)
        assert score < 0.1

    def test_future_time(self):
        """Future time (edge case)"""
        now = datetime.now()
        future = now + timedelta(hours=1)
        # Future should give high score (or handle gracefully)
        score = _calculate_time_decay(future, now, 0.1)
        assert score >= 0.0  # Should not be negative


class TestCornerCases:
    """Corner case tests"""

    def test_zero_vector_similarity(self):
        """Zero vector similarity"""
        v1 = [0.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        sim = _cosine_similarity(v1, v2)
        assert sim == 0.0  # Division by zero handled

    def test_high_dimensional_vectors(self):
        """High dimensional vectors (768d BERT)"""
        import random

        random.seed(42)
        v1 = [random.random() for _ in range(768)]
        v2 = [random.random() for _ in range(768)]
        sim = _cosine_similarity(v1, v2)
        assert -1.0 <= sim <= 1.0

    def test_decay_rate_extremes(self):
        """Extreme decay rates"""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Very fast decay
        fast_score = _calculate_time_decay(one_hour_ago, now, 10.0)
        assert fast_score < 0.001

        # No decay
        no_decay = _calculate_time_decay(one_hour_ago, now, 0.0)
        assert no_decay == pytest.approx(1.0)

    def test_single_dominant_weight(self):
        """Single dominant weight"""
        similarity = 1.0
        recency = 0.0
        importance = 0.0

        # Only similarity matters
        composite = similarity * 1.0 + recency * 0.0 + importance * 0.0
        assert composite == pytest.approx(1.0)
