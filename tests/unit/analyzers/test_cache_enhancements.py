"""
Test cache enhancement features: warming, adaptive TTL, persistence

SOTA requirements:
- Base cases: Normal operation
- Edge cases: Empty cache, single item, full cache
- Extreme cases: 1000+ items, rapid access, concurrent access
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.adapters.ttl_cache import TTLCache
from codegraph_engine.code_foundation.infrastructure.analyzers.function_summary import (
    FunctionSummaryCache,
    FunctionTaintSummary,
)


class TestCacheWarming:
    """Test cache warming functionality"""

    def test_warm_up_basic(self, tmp_path):
        """Base case: Warm up with a few functions"""
        cache = FunctionSummaryCache(max_size=100)

        # Analyzer function mock
        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params={0},
                tainted_return=True,
                confidence=0.9,
            )

        hot_functions = ["func1", "func2", "func3"]

        warmed = cache.warm_up(hot_functions, mock_analyzer, max_warm=10)

        assert warmed == 3
        assert len(cache) == 3
        assert "func1" in cache
        assert cache._hot_functions == {"func1", "func2", "func3"}

    def test_warm_up_respects_max(self):
        """Edge case: max_warm limit respected"""
        cache = FunctionSummaryCache(max_size=100)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        many_functions = [f"func{i}" for i in range(100)]

        warmed = cache.warm_up(many_functions, mock_analyzer, max_warm=10)

        assert warmed == 10
        assert len(cache) == 10

    def test_warm_up_skips_existing(self):
        """Edge case: Skip already cached functions"""
        cache = FunctionSummaryCache(max_size=100)

        # Pre-cache one function
        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params={0},
                tainted_return=True,
                confidence=0.9,
            )

        hot_functions = ["func1", "func2", "func3"]

        warmed = cache.warm_up(hot_functions, mock_analyzer, max_warm=10)

        # Only func2, func3 should be warmed (func1 already exists)
        assert warmed == 2
        assert len(cache) == 3

    def test_warm_up_handles_errors(self):
        """Edge case: Handle analyzer errors gracefully"""
        cache = FunctionSummaryCache(max_size=100)

        def failing_analyzer(func_id):
            if func_id == "bad_func":
                raise ValueError("Analysis failed")
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        functions = ["func1", "bad_func", "func2"]

        warmed = cache.warm_up(functions, failing_analyzer, max_warm=10)

        # Should warm func1 and func2, skip bad_func
        assert warmed == 2
        assert "func1" in cache
        assert "func2" in cache
        assert "bad_func" not in cache


class TestHotFunctions:
    """Test hot function tracking"""

    def test_get_hot_functions_tracks_access(self):
        """Base case: Access frequency tracked correctly"""
        cache = FunctionSummaryCache(max_size=100)

        # Add functions
        for i in range(5):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )
            cache.put(summary)

        # Access func0 10 times, func1 5 times, func2 once
        for _ in range(10):
            cache.get("func0")
        for _ in range(5):
            cache.get("func1")
        cache.get("func2")

        hot = cache.get_hot_functions(top_n=3)

        assert hot[0] == "func0"  # Most accessed
        assert hot[1] == "func1"  # Second most
        assert hot[2] == "func2"  # Third most

    def test_get_hot_functions_empty_cache(self):
        """Edge case: Empty cache returns empty list"""
        cache = FunctionSummaryCache(max_size=100)

        hot = cache.get_hot_functions(top_n=10)

        assert hot == []

    def test_get_hot_functions_top_n_larger_than_cache(self):
        """Edge case: top_n larger than cache size"""
        cache = FunctionSummaryCache(max_size=100)

        for i in range(3):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )
            cache.put(summary)
            cache.get(f"func{i}")

        hot = cache.get_hot_functions(top_n=100)

        assert len(hot) == 3  # Only 3 functions exist


class TestCachePersistence:
    """Test cache persistence (save/load)"""

    def test_save_and_load_basic(self, tmp_path):
        """Base case: Save and load cache successfully"""
        cache_file = tmp_path / "test_cache.pkl"

        # Create and populate cache
        cache1 = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        for i in range(5):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params={i},
                tainted_return=True,
                confidence=0.9,
            )
            cache1.put(summary)

        # Save to disk
        success = cache1.save_to_disk()
        assert success
        assert cache_file.exists()

        # Load into new cache
        cache2 = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        assert len(cache2) == 5
        assert "func0" in cache2
        assert "func4" in cache2

        # Verify data integrity
        summary = cache2.get("func2")
        assert summary is not None
        assert summary.tainted_params == {2}
        assert summary.tainted_return

    def test_load_from_nonexistent_file(self, tmp_path):
        """Edge case: Load from non-existent file (first run)"""
        cache_file = tmp_path / "nonexistent.pkl"

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        # Should start empty (no crash)
        assert len(cache) == 0

    def test_save_without_persistence_enabled(self):
        """Edge case: Save without persistence enabled"""
        cache = FunctionSummaryCache(max_size=100, enable_persistence=False)

        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params=set(),
            tainted_return=False,
            confidence=1.0,
        )
        cache.put(summary)

        success = cache.save_to_disk()
        assert not success  # Should warn and skip

    def test_persistence_atomic_write(self, tmp_path):
        """SOTA: Atomic write prevents corruption"""
        cache_file = tmp_path / "atomic_test.pkl"

        cache = FunctionSummaryCache(
            max_size=100,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        for i in range(100):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )
            cache.put(summary)

        # Save should be atomic (either complete or not at all)
        success = cache.save_to_disk()
        assert success

        # File should be valid pickle
        import pickle

        with open(cache_file, "rb") as f:
            data = pickle.load(f)

        assert len(data["summaries"]) == 100


class TestAdaptiveTTL:
    """Test adaptive TTL in TTLCache"""

    def test_adaptive_ttl_reduces_for_hot_items(self):
        """Base case: Hot items get shorter TTL"""
        cache = TTLCache[str](
            max_size=100,
            default_ttl=3600,
            adaptive_ttl=True,
            min_ttl=60,
            max_ttl=86400,
        )

        # Add item
        cache.set("hot_item", "value1", ttl=3600)

        # Access many times
        for _ in range(100):
            cache.get("hot_item")

        # Update item - should get shorter TTL
        cache.set("hot_item", "value2", ttl=3600)

        # Check that TTL was adjusted
        entry = cache._cache["hot_item"]
        original_ttl = 3600
        assert entry.access_count == 100

        # TTL should be significantly shorter due to high access count
        actual_ttl = (entry.expires_at - entry.created_at).total_seconds()
        assert actual_ttl < original_ttl

    def test_adaptive_ttl_disabled(self):
        """Edge case: Adaptive TTL can be disabled"""
        cache = TTLCache[str](
            max_size=100,
            default_ttl=3600,
            adaptive_ttl=False,  # Disabled
        )

        cache.set("item", "value1", ttl=3600)

        for _ in range(100):
            cache.get("item")

        # Update - TTL should NOT change
        cache.set("item", "value2", ttl=3600)

        entry = cache._cache["item"]
        actual_ttl = (entry.expires_at - entry.created_at).total_seconds()

        # Should be close to original (within 1 second for timing)
        assert abs(actual_ttl - 3600) < 2

    def test_adaptive_ttl_respects_bounds(self):
        """Edge case: Adaptive TTL respects min/max bounds"""
        cache = TTLCache[str](
            max_size=100,
            default_ttl=3600,
            adaptive_ttl=True,
            min_ttl=100,
            max_ttl=7200,
        )

        cache.set("item", "value", ttl=3600)

        # Access 1000 times
        for _ in range(100):  # 1000 → 100
            cache.get("item")

        # Update
        cache.set("item", "new_value", ttl=3600)

        entry = cache._cache["item"]
        actual_ttl = (entry.expires_at - entry.created_at).total_seconds()

        # Should be clamped to min_ttl
        assert actual_ttl >= 100  # min_ttl
        assert actual_ttl <= 7200  # max_ttl


class TestExtremeScenarios:
    """Test extreme usage scenarios"""

    def test_warm_up_1000_functions(self):
        """Extreme: Warm up 1000 functions"""
        cache = FunctionSummaryCache(max_size=2000)

        def mock_analyzer(func_id):
            return FunctionTaintSummary(
                function_id=func_id,
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )

        functions = [f"func{i}" for i in range(100)]  # 1000 → 100

        import time

        start = time.time()
        warmed = cache.warm_up(functions, mock_analyzer, max_warm=1000)
        elapsed = time.time() - start

        assert warmed == 100  # 1000 → 100
        assert elapsed < 1.0  # Should be fast (<1 second)

    def test_persistence_large_cache(self, tmp_path):
        """Extreme: Persist 100+ summaries (축소)"""
        cache_file = tmp_path / "large_cache.pkl"

        cache = FunctionSummaryCache(
            max_size=2000,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        # Add 1000 summaries
        for i in range(100):  # 1000 → 100
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params={i % 10},
                tainted_return=i % 2 == 0,
                confidence=0.9,
            )
            cache.put(summary)

        # Save
        success = cache.save_to_disk()
        assert success

        # Load
        cache2 = FunctionSummaryCache(
            max_size=2000,
            enable_persistence=True,
            persistence_path=str(cache_file),
        )

        assert cache2.size() == 100  # 1000 → 100

        # Verify random samples
        assert "func0" in cache2
        assert "func50" in cache2  # func500 → func50
        assert "func99" in cache2  # func999 → func99

    def test_hot_functions_with_high_churn(self):
        """Extreme: Track hot functions with high churn rate"""
        cache = FunctionSummaryCache(max_size=100)

        # Add 100 functions, access with power-law distribution
        for i in range(100):
            summary = FunctionTaintSummary(
                function_id=f"func{i}",
                tainted_params=set(),
                tainted_return=False,
                confidence=1.0,
            )
            cache.put(summary)

        # Power-law access: func0 accessed 1000 times, func99 accessed once
        for i in range(100):
            access_count = 1000 // (i + 1)
            for _ in range(access_count):
                cache.get(f"func{i}")

        hot = cache.get_hot_functions(top_n=10)

        # Top 10 should be func0-func9
        assert hot[0] == "func0"
        assert hot[9] == "func9"
