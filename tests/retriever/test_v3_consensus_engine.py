"""
Tests for Consensus Engine V3.
"""

import pytest

from src.retriever.v3.config import ConsensusConfig
from src.retriever.v3.consensus_engine import ConsensusEngine
from src.retriever.v3.models import RankedHit


class TestConsensusEngine:
    """Test consensus engine."""

    @pytest.fixture
    def config(self):
        """Create consensus config."""
        return ConsensusConfig(beta=0.3, max_factor=1.5, quality_q0=10.0)

    @pytest.fixture
    def engine(self, config):
        """Create consensus engine instance."""
        return ConsensusEngine(config)

    @pytest.fixture
    def sample_hits(self):
        """Create sample hits with various consensus levels."""
        return {
            "vector": [
                RankedHit(chunk_id="high_consensus", strategy="vector", rank=0),
                RankedHit(chunk_id="medium_consensus", strategy="vector", rank=5),
                RankedHit(chunk_id="low_consensus", strategy="vector", rank=10),
            ],
            "lexical": [
                RankedHit(chunk_id="high_consensus", strategy="lexical", rank=1),
                RankedHit(chunk_id="medium_consensus", strategy="lexical", rank=8),
            ],
            "symbol": [
                RankedHit(chunk_id="high_consensus", strategy="symbol", rank=0),
            ],
        }

    def test_consensus_stats_calculation(self, engine, sample_hits):
        """Test consensus statistics calculation."""
        stats = engine.calculate_consensus_stats("high_consensus", sample_hits)

        # high_consensus appears in 3 strategies
        assert stats.num_strategies == 3
        assert stats.best_rank == 0  # Best rank is 0 (vector)
        assert stats.avg_rank == (0 + 1 + 0) / 3  # Average of ranks

        # Quality factor should be high (low avg rank)
        assert stats.quality_factor > 0.5

        # Consensus factor should be > 1 (boost)
        assert stats.consensus_factor > 1.0
        assert stats.consensus_factor <= 1.5  # Capped at max_factor

    def test_consensus_boost_formula(self, engine):
        """Test consensus boost formula."""
        hits = {
            "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=0)],
            "lexical": [RankedHit(chunk_id="chunk1", strategy="lexical", rank=0)],
            "symbol": [RankedHit(chunk_id="chunk1", strategy="symbol", rank=0)],
            "graph": [RankedHit(chunk_id="chunk1", strategy="graph", rank=0)],
        }

        stats = engine.calculate_consensus_stats("chunk1", hits)

        # 4 strategies, all rank 0
        # consensus_raw = 1 + 0.3 * (sqrt(4) - 1) = 1 + 0.3 * 1 = 1.3
        # quality_factor = 1 / (1 + 0/10) = 1.0
        # consensus_factor = 1.3 * (0.5 + 0.5 * 1.0) = 1.3

        assert stats.num_strategies == 4
        assert abs(stats.consensus_factor - 1.3) < 0.01

    def test_consensus_cap(self, engine):
        """Test consensus factor capping."""
        # Create many strategies to exceed max_factor
        hits = {
            f"strategy_{i}": [RankedHit(chunk_id="chunk1", strategy=f"strategy_{i}", rank=0)]
            for i in range(20)
        }

        stats = engine.calculate_consensus_stats("chunk1", hits)

        # Should be capped at max_factor (1.5)
        assert stats.consensus_factor <= 1.5

    def test_quality_factor_impact(self, engine):
        """Test that poor rank quality reduces consensus boost."""
        # Good ranks
        good_hits = {
            "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=0)],
            "lexical": [RankedHit(chunk_id="chunk1", strategy="lexical", rank=1)],
        }

        # Poor ranks
        poor_hits = {
            "vector": [RankedHit(chunk_id="chunk2", strategy="vector", rank=50)],
            "lexical": [RankedHit(chunk_id="chunk2", strategy="lexical", rank=60)],
        }

        good_stats = engine.calculate_consensus_stats("chunk1", good_hits)
        poor_stats = engine.calculate_consensus_stats("chunk2", poor_hits)

        # Good ranks should have higher consensus factor
        assert good_stats.consensus_factor > poor_stats.consensus_factor

    def test_apply_consensus_boost(self, engine, sample_hits):
        """Test applying consensus boost to base scores."""
        base_scores = {
            "high_consensus": 0.5,
            "medium_consensus": 0.5,
            "low_consensus": 0.5,
        }

        boosted_scores, stats_map = engine.apply_consensus_boost(base_scores, sample_hits)

        # high_consensus should get highest boost (3 strategies)
        assert boosted_scores["high_consensus"] > base_scores["high_consensus"]

        # Verify stats are returned
        assert "high_consensus" in stats_map
        assert stats_map["high_consensus"].num_strategies == 3

    def test_get_chunks_by_consensus(self, engine):
        """Test filtering chunks by consensus threshold."""
        stats_map = {
            "chunk1": engine.calculate_consensus_stats(
                "chunk1",
                {
                    "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=0)],
                    "lexical": [RankedHit(chunk_id="chunk1", strategy="lexical", rank=0)],
                    "symbol": [RankedHit(chunk_id="chunk1", strategy="symbol", rank=0)],
                },
            ),
            "chunk2": engine.calculate_consensus_stats(
                "chunk2",
                {
                    "vector": [RankedHit(chunk_id="chunk2", strategy="vector", rank=0)],
                },
            ),
        }

        # Filter for chunks in at least 2 strategies
        high_consensus = engine.get_chunks_by_consensus(stats_map, min_strategies=2)

        assert "chunk1" in high_consensus
        assert "chunk2" not in high_consensus

    def test_explain_consensus(self, engine, sample_hits):
        """Test consensus explanation generation."""
        stats = engine.calculate_consensus_stats("high_consensus", sample_hits)

        explanation = engine.explain_consensus(stats)

        # Should contain key information
        assert "3 strategies" in explanation
        assert "best rank" in explanation.lower()
        assert "avg rank" in explanation.lower()

    def test_single_strategy_no_boost(self, engine):
        """Test that single strategy gets minimal boost."""
        hits = {
            "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=0)],
        }

        stats = engine.calculate_consensus_stats("chunk1", hits)

        # consensus_raw = 1 + 0.3 * (sqrt(1) - 1) = 1 + 0 = 1.0
        # Should be close to 1.0 (no boost)
        assert stats.consensus_factor <= 1.1

    def test_best_rank_tracking(self, engine):
        """Test that best rank is correctly tracked."""
        hits = {
            "vector": [RankedHit(chunk_id="chunk1", strategy="vector", rank=10)],
            "lexical": [RankedHit(chunk_id="chunk1", strategy="lexical", rank=2)],
            "symbol": [RankedHit(chunk_id="chunk1", strategy="symbol", rank=5)],
        }

        stats = engine.calculate_consensus_stats("chunk1", hits)

        # Best rank should be 2 (from lexical)
        assert stats.best_rank == 2
