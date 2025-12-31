"""
Budget Manager Tests (SOTA L11)

Test Coverage:
- BudgetConfig: Token limits, weights
- RelevanceScore: Score calculation, to_dict
- Edge: Zero budget, max budget, weight boundaries
"""

import pytest

from codegraph_engine.reasoning_engine.infrastructure.slicer.budget_manager import (
    BudgetConfig,
    RelevanceScore,
)


class TestBudgetConfig:
    """BudgetConfig tests"""

    def test_default_config(self):
        """Default configuration values"""
        config = BudgetConfig()
        assert config.max_tokens == 8000
        assert config.min_tokens == 500
        assert config.summarization_threshold == 200

    def test_default_weights(self):
        """Default relevance weights"""
        config = BudgetConfig()
        assert config.distance_weight == 0.5
        assert config.effect_weight == 0.3
        assert config.recency_weight == 0.1
        assert config.hotspot_weight == 0.1

    def test_weights_sum_to_one(self):
        """Default weights sum to 1.0"""
        config = BudgetConfig()
        total = config.distance_weight + config.effect_weight + config.recency_weight + config.hotspot_weight
        assert total == pytest.approx(1.0)

    def test_custom_config(self):
        """Custom configuration"""
        config = BudgetConfig(
            max_tokens=16000,
            min_tokens=1000,
            summarization_threshold=100,
        )
        assert config.max_tokens == 16000
        assert config.min_tokens == 1000

    def test_custom_weights(self):
        """Custom relevance weights"""
        config = BudgetConfig(
            distance_weight=0.7,
            effect_weight=0.2,
            recency_weight=0.05,
            hotspot_weight=0.05,
        )
        total = config.distance_weight + config.effect_weight + config.recency_weight + config.hotspot_weight
        assert total == pytest.approx(1.0)


class TestRelevanceScore:
    """RelevanceScore tests"""

    def test_create_score(self):
        """Create relevance score"""
        score = RelevanceScore(
            node_id="func1",
            score=0.85,
            distance_score=0.9,
            effect_score=0.7,
        )
        assert score.node_id == "func1"
        assert score.score == 0.85
        assert score.distance_score == 0.9

    def test_default_values(self):
        """Default score values"""
        score = RelevanceScore(node_id="node", score=0.5)
        assert score.distance_score == 0.0
        assert score.effect_score == 0.0
        assert score.recency_score == 0.0
        assert score.hotspot_score == 0.0
        assert score.reason == "distance"

    def test_to_dict(self):
        """Convert to dictionary"""
        score = RelevanceScore(
            node_id="func1",
            score=0.8,
            distance_score=0.9,
            effect_score=0.7,
            recency_score=0.5,
            hotspot_score=0.3,
            reason="effect",
        )
        d = score.to_dict()

        assert d["node_id"] == "func1"
        assert d["score"] == 0.8
        assert d["distance"] == 0.9
        assert d["effect"] == 0.7
        assert d["recency"] == 0.5
        assert d["hotspot"] == 0.3
        assert d["reason"] == "effect"

    def test_all_reason_types(self):
        """All reason types"""
        for reason in ["distance", "effect", "recency", "hotspot"]:
            score = RelevanceScore(node_id="n", score=0.5, reason=reason)
            assert score.reason == reason


class TestEdgeCases:
    """Edge case tests"""

    def test_zero_max_tokens(self):
        """Zero max tokens"""
        config = BudgetConfig(max_tokens=0)
        assert config.max_tokens == 0

    def test_very_large_max_tokens(self):
        """Very large max tokens"""
        config = BudgetConfig(max_tokens=1_000_000)
        assert config.max_tokens == 1_000_000

    def test_min_greater_than_max(self):
        """Min tokens greater than max (edge case)"""
        config = BudgetConfig(max_tokens=100, min_tokens=1000)
        # Model doesn't validate, just stores
        assert config.min_tokens > config.max_tokens

    def test_zero_score(self):
        """Zero relevance score"""
        score = RelevanceScore(node_id="low", score=0.0)
        assert score.score == 0.0

    def test_max_score(self):
        """Maximum relevance score"""
        score = RelevanceScore(node_id="high", score=1.0)
        assert score.score == 1.0

    def test_negative_score(self):
        """Negative score (edge case)"""
        score = RelevanceScore(node_id="neg", score=-0.5)
        assert score.score == -0.5


class TestCornerCases:
    """Corner case tests"""

    def test_all_weights_zero(self):
        """All weights zero"""
        config = BudgetConfig(
            distance_weight=0.0,
            effect_weight=0.0,
            recency_weight=0.0,
            hotspot_weight=0.0,
        )
        total = config.distance_weight + config.effect_weight + config.recency_weight + config.hotspot_weight
        assert total == 0.0

    def test_single_dominant_weight(self):
        """Single dominant weight"""
        config = BudgetConfig(
            distance_weight=1.0,
            effect_weight=0.0,
            recency_weight=0.0,
            hotspot_weight=0.0,
        )
        assert config.distance_weight == 1.0

    def test_unicode_node_id(self):
        """Unicode in node_id"""
        score = RelevanceScore(node_id="함수_테스트", score=0.5)
        assert "함수" in score.node_id

    def test_long_node_id(self):
        """Very long node_id"""
        long_id = "module.submodule." + "class." * 50 + "method"
        score = RelevanceScore(node_id=long_id, score=0.5)
        assert len(score.node_id) > 200

    def test_score_precision(self):
        """Score precision"""
        score = RelevanceScore(node_id="precise", score=0.123456789)
        assert score.score == pytest.approx(0.123456789)

    def test_to_dict_roundtrip(self):
        """to_dict contains all fields"""
        score = RelevanceScore(
            node_id="test",
            score=0.5,
            distance_score=0.6,
            effect_score=0.7,
            recency_score=0.8,
            hotspot_score=0.9,
            reason="hotspot",
        )
        d = score.to_dict()
        assert len(d) == 7  # All fields present
