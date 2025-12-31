"""
Tests for Pass@k Selector (TRAE-style)
"""

import pytest

from apps.orchestrator.orchestrator.domain.reasoning.passk_selector import PassKSelector


class MockStrategy:
    """Mock strategy for testing"""

    def __init__(self, strategy_id: str, score: float, code: str):
        self.strategy_id = strategy_id
        self.score = score
        self.code = code


@pytest.mark.asyncio
class TestPassKSelector:
    """Test Pass@k Selection"""

    async def test_first_success(self):
        """Test first strategy succeeds"""
        selector = PassKSelector(k=5)

        strategies = [
            MockStrategy("s1", 0.9, "valid code"),
            MockStrategy("s2", 0.8, "valid code"),
            MockStrategy("s3", 0.7, "valid code"),
        ]

        # All succeed
        def apply_fn(code):
            return True, ""

        result = await selector.select(strategies, apply_fn)

        assert result.selected_strategy_id == "s1"  # First one
        assert result.selected_rank == 1
        assert result.total_attempts == 1
        assert not result.fallback_used

    async def test_second_success(self):
        """Test second strategy succeeds (first fails)"""
        selector = PassKSelector(k=5)

        strategies = [
            MockStrategy("s1", 0.9, "invalid"),
            MockStrategy("s2", 0.8, "valid"),
            MockStrategy("s3", 0.7, "valid"),
        ]

        attempt_count = [0]

        def apply_fn(code):
            attempt_count[0] += 1
            # First fails, second succeeds
            return code == "valid", "error" if code != "valid" else ""

        result = await selector.select(strategies, apply_fn)

        assert result.selected_strategy_id == "s2"  # Second one
        assert result.selected_rank == 2
        assert result.total_attempts == 2
        assert not result.fallback_used

    async def test_all_fail_fallback(self):
        """Test all strategies fail, use fallback"""
        selector = PassKSelector(k=3)

        strategies = [
            MockStrategy("s1", 0.9, "invalid1"),
            MockStrategy("s2", 0.8, "invalid2"),
            MockStrategy("s3", 0.7, "invalid3"),
        ]

        # All fail
        def apply_fn(code):
            return False, "error"

        result = await selector.select(strategies, apply_fn)

        assert result.selected_strategy_id == "s1"  # Fallback to top-1
        assert result.selected_rank is None  # Failed
        assert result.total_attempts == 3
        assert result.fallback_used

    async def test_k_limit(self):
        """Test k parameter limits attempts"""
        selector = PassKSelector(k=2)  # Only try top-2

        strategies = [
            MockStrategy("s1", 0.9, "invalid"),
            MockStrategy("s2", 0.8, "invalid"),
            MockStrategy("s3", 0.7, "valid"),  # Would succeed, but not tried
        ]

        def apply_fn(code):
            return code == "valid", ""

        result = await selector.select(strategies, apply_fn)

        # Only tried top-2, both failed
        assert result.total_attempts == 2
        assert result.fallback_used

    async def test_empty_strategies(self):
        """Test empty strategy list"""
        selector = PassKSelector(k=5)

        def apply_fn(code):
            return True, ""

        # Should handle empty list gracefully
        strategies = []
        result = await selector.select(strategies, apply_fn)

        assert result.selected_strategy_id is None or result.fallback_used
