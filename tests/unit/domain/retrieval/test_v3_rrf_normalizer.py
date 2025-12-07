"""
Tests for RRF Normalizer V3.
"""

import pytest
from src.retriever.v3.config import RRFConfig, WeightProfile
from src.retriever.v3.models import RankedHit
from src.retriever.v3.rrf_normalizer import RRFNormalizer


class TestRRFNormalizer:
    """Test RRF normalizer."""

    @pytest.fixture
    def config(self):
        """Create RRF config."""
        return RRFConfig(k_vec=70, k_lex=70, k_sym=50, k_graph=50)

    @pytest.fixture
    def normalizer(self, config):
        """Create normalizer instance."""
        return RRFNormalizer(config)

    @pytest.fixture
    def sample_hits(self):
        """Create sample ranked hits."""
        return {
            "vector": [
                RankedHit(chunk_id="chunk1", strategy="vector", rank=0, raw_score=0.9),
                RankedHit(chunk_id="chunk2", strategy="vector", rank=1, raw_score=0.8),
                RankedHit(chunk_id="chunk3", strategy="vector", rank=2, raw_score=0.7),
            ],
            "lexical": [
                RankedHit(chunk_id="chunk1", strategy="lexical", rank=1, raw_score=15.0),
                RankedHit(chunk_id="chunk4", strategy="lexical", rank=0, raw_score=20.0),
            ],
            "symbol": [
                RankedHit(chunk_id="chunk1", strategy="symbol", rank=0, raw_score=1.0),
            ],
        }

    def test_rrf_calculation(self, normalizer, sample_hits):
        """Test basic RRF score calculation."""
        rrf_scores = normalizer.calculate_rrf_scores(sample_hits)

        # chunk1 appears in all 3 strategies
        assert "chunk1" in rrf_scores
        assert "vector" in rrf_scores["chunk1"]
        assert "lexical" in rrf_scores["chunk1"]
        assert "symbol" in rrf_scores["chunk1"]

        # RRF formula: 1 / (k + rank)
        # chunk1 in vector: rank=0, k=70 → 1/70
        expected_vec = 1.0 / (70 + 0)
        assert abs(rrf_scores["chunk1"]["vector"] - expected_vec) < 0.001

        # chunk1 in symbol: rank=0, k=50 → 1/50
        expected_sym = 1.0 / (50 + 0)
        assert abs(rrf_scores["chunk1"]["symbol"] - expected_sym) < 0.001

    def test_weighted_scores(self, normalizer, sample_hits):
        """Test weighted score calculation."""
        rrf_scores = normalizer.calculate_rrf_scores(sample_hits)

        # Uniform weights
        weights = WeightProfile(vec=0.25, lex=0.25, sym=0.25, graph=0.25)
        weighted_scores = normalizer.calculate_weighted_scores(rrf_scores, weights)

        # chunk1 should have highest score (appears in 3 strategies)
        assert "chunk1" in weighted_scores
        chunk1_score = weighted_scores["chunk1"]

        # Should be sum of weighted RRF scores
        expected = (
            0.25 * rrf_scores["chunk1"]["vector"]
            + 0.25 * rrf_scores["chunk1"]["lexical"]
            + 0.25 * rrf_scores["chunk1"]["symbol"]
        )
        assert abs(chunk1_score - expected) < 0.001

    def test_normalize_and_weight(self, normalizer, sample_hits):
        """Test complete normalization pipeline."""
        weights = WeightProfile(vec=0.4, lex=0.3, sym=0.2, graph=0.1)

        weighted_scores, rrf_scores = normalizer.normalize_and_weight(sample_hits, weights)

        # Should return both weighted scores and RRF scores
        assert len(weighted_scores) > 0
        assert len(rrf_scores) > 0

        # chunk1 should have high score
        assert "chunk1" in weighted_scores
        assert weighted_scores["chunk1"] > 0

    def test_high_rank_penalty(self, normalizer):
        """Test that higher ranks get lower RRF scores."""
        hits = {
            "vector": [
                RankedHit(chunk_id="top", strategy="vector", rank=0),
                RankedHit(chunk_id="middle", strategy="vector", rank=10),
                RankedHit(chunk_id="bottom", strategy="vector", rank=100),
            ]
        }

        rrf_scores = normalizer.calculate_rrf_scores(hits)

        # Lower rank → higher RRF score
        assert rrf_scores["top"]["vector"] > rrf_scores["middle"]["vector"]
        assert rrf_scores["middle"]["vector"] > rrf_scores["bottom"]["vector"]

    def test_strategy_specific_k(self, normalizer):
        """Test that different strategies use different k values."""
        hits = {
            "symbol": [RankedHit(chunk_id="chunk1", strategy="symbol", rank=0)],
            "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=0)],
        }

        rrf_scores = normalizer.calculate_rrf_scores(hits)

        # Symbol uses k=50, vector uses k=70
        # Same rank (0) should give different RRF scores
        symbol_rrf = rrf_scores["chunk1"]["symbol"]  # 1/50
        vector_rrf = rrf_scores["chunk1"]["vector"]  # 1/70

        assert symbol_rrf > vector_rrf

    def test_empty_hits(self, normalizer):
        """Test handling of empty hits."""
        hits = {}
        rrf_scores = normalizer.calculate_rrf_scores(hits)

        assert len(rrf_scores) == 0

    def test_single_strategy(self, normalizer):
        """Test with single strategy."""
        hits = {
            "vector": [
                RankedHit(chunk_id="chunk1", strategy="vector", rank=0),
                RankedHit(chunk_id="chunk2", strategy="vector", rank=1),
            ]
        }

        weights = WeightProfile(vec=1.0, lex=0.0, sym=0.0, graph=0.0)
        weighted_scores, _ = normalizer.normalize_and_weight(hits, weights)

        # Both chunks should have scores
        assert "chunk1" in weighted_scores
        assert "chunk2" in weighted_scores

        # chunk1 should score higher (better rank)
        assert weighted_scores["chunk1"] > weighted_scores["chunk2"]
