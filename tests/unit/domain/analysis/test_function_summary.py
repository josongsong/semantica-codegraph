"""
Unit tests for FunctionSummaryCache and TaintAnalyzerWithCache

Tests:
1. Cache hit/miss behavior
2. LRU eviction
3. Cache statistics
4. Integration with analyzer
"""

import pytest
from datetime import datetime
from src.contexts.code_foundation.infrastructure.analyzers.function_summary import (
    FunctionTaintSummary,
    FunctionSummaryCache,
    TaintAnalyzerWithCache,
    create_cached_analyzer,
)


class TestFunctionTaintSummary:
    """Test FunctionTaintSummary dataclass"""

    def test_basic_creation(self):
        """Test creating a basic summary"""
        summary = FunctionTaintSummary(
            function_id="test.py:10:func:(str)->str",
            tainted_params={0},
            tainted_return=True,
        )

        assert summary.function_id == "test.py:10:func:(str)->str"
        assert summary.tainted_params == {0}
        assert summary.tainted_return is True
        assert summary.sanitizes is False

    def test_is_tainted_call_propagates(self):
        """Test taint propagation check"""
        summary = FunctionTaintSummary(
            function_id="func1",
            tainted_params={0, 2},  # Params 0 and 2 propagate taint
            tainted_return=True,
        )

        # Tainted arg 0 → tainted return
        assert summary.is_tainted_call({0}) is True

        # Tainted arg 2 → tainted return
        assert summary.is_tainted_call({2}) is True

        # Tainted arg 1 (not in tainted_params) → clean return
        assert summary.is_tainted_call({1}) is False

        # No tainted args → clean return
        assert summary.is_tainted_call(set()) is False

    def test_is_tainted_call_sanitizer(self):
        """Test sanitizer doesn't propagate taint"""
        summary = FunctionTaintSummary(
            function_id="escape_html",
            tainted_params={0},
            tainted_return=False,
            sanitizes=True,
        )

        # Sanitizer always returns clean
        assert summary.is_tainted_call({0}) is False
        assert summary.is_tainted_call({1}) is False


class TestFunctionSummaryCache:
    """Test FunctionSummaryCache LRU cache"""

    def test_cache_hit(self):
        """Test cache hit increments hits counter"""
        cache = FunctionSummaryCache(max_size=100)
        summary = FunctionTaintSummary("func1", {0}, True)

        cache.put(summary)

        result = cache.get("func1")
        assert result == summary

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0

    def test_cache_miss(self):
        """Test cache miss"""
        cache = FunctionSummaryCache()

        result = cache.get("nonexistent")
        assert result is None

        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.0

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full"""
        cache = FunctionSummaryCache(max_size=2)

        # Add 2 summaries (fills cache)
        cache.put(FunctionTaintSummary("func1", {0}, True))
        cache.put(FunctionTaintSummary("func2", {1}, False))

        assert len(cache) == 2

        # Add 3rd summary (should evict func1, the oldest)
        cache.put(FunctionTaintSummary("func3", {2}, True))

        assert len(cache) == 2
        assert cache.get("func1") is None  # Evicted
        assert cache.get("func2") is not None  # Still there
        assert cache.get("func3") is not None  # Newly added

        stats = cache.get_stats()
        assert stats["evictions"] == 1

    def test_lru_update_on_access(self):
        """Test that accessing an item moves it to end (most recent)"""
        cache = FunctionSummaryCache(max_size=2)

        cache.put(FunctionTaintSummary("func1", {0}, True))
        cache.put(FunctionTaintSummary("func2", {1}, False))

        # Access func1 (moves it to end)
        cache.get("func1")

        # Add func3 (should evict func2, not func1)
        cache.put(FunctionTaintSummary("func3", {2}, True))

        assert cache.get("func1") is not None  # Still there (recently accessed)
        assert cache.get("func2") is None  # Evicted (oldest)
        assert cache.get("func3") is not None  # New

    def test_invalidate(self):
        """Test cache invalidation"""
        cache = FunctionSummaryCache()
        cache.put(FunctionTaintSummary("func1", {0}, True))

        assert "func1" in cache

        cache.invalidate("func1")

        assert "func1" not in cache
        assert cache.get("func1") is None

    def test_clear(self):
        """Test clearing entire cache"""
        cache = FunctionSummaryCache()
        cache.put(FunctionTaintSummary("func1", {0}, True))
        cache.put(FunctionTaintSummary("func2", {1}, False))

        assert len(cache) == 2

        cache.clear()

        assert len(cache) == 0
        assert cache.get("func1") is None
        assert cache.get("func2") is None

    def test_update_existing(self):
        """Test updating existing summary"""
        cache = FunctionSummaryCache()

        # Initial summary
        cache.put(FunctionTaintSummary("func1", {0}, True))
        assert cache.get("func1").tainted_return is True

        # Update with new summary
        cache.put(FunctionTaintSummary("func1", {0, 1}, False))

        # Should be updated
        summary = cache.get("func1")
        assert summary.tainted_params == {0, 1}
        assert summary.tainted_return is False

        # Cache size should not increase
        assert len(cache) == 1


class TestTaintAnalyzerWithCache:
    """Test TaintAnalyzerWithCache"""

    def test_create_with_default_cache(self):
        """Test creating analyzer with default cache"""
        analyzer = TaintAnalyzerWithCache(base_analyzer=None)

        assert analyzer.cache is not None
        assert isinstance(analyzer.cache, FunctionSummaryCache)

    def test_create_with_custom_cache(self):
        """Test creating analyzer with custom cache"""
        custom_cache = FunctionSummaryCache(max_size=50)
        analyzer = TaintAnalyzerWithCache(None, custom_cache)

        assert analyzer.cache is custom_cache
        assert analyzer.cache._max_size == 50

    def test_get_cache_stats(self):
        """Test getting cache statistics"""
        analyzer = TaintAnalyzerWithCache(None)

        # Add some data
        analyzer.cache.put(FunctionTaintSummary("func1", {0}, True))
        analyzer.cache.get("func1")  # Hit
        analyzer.cache.get("func2")  # Miss

        stats = analyzer.get_cache_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["cache_size"] == 1

    def test_clear_cache(self):
        """Test clearing cache through analyzer"""
        analyzer = TaintAnalyzerWithCache(None)

        analyzer.cache.put(FunctionTaintSummary("func1", {0}, True))
        assert len(analyzer.cache) == 1

        analyzer.clear_cache()
        assert len(analyzer.cache) == 0


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_create_cached_analyzer_default(self):
        """Test creating analyzer with defaults"""
        analyzer = create_cached_analyzer()

        assert isinstance(analyzer, TaintAnalyzerWithCache)
        assert analyzer.cache._max_size == 10000  # Default

    def test_create_cached_analyzer_custom_size(self):
        """Test creating analyzer with custom cache size"""
        analyzer = create_cached_analyzer(max_cache_size=500)

        assert analyzer.cache._max_size == 500


# Performance tests


@pytest.mark.benchmark
class TestPerformance:
    """Performance benchmarks"""

    def test_cache_hit_performance(self, benchmark):
        """Benchmark cache hit performance"""
        cache = FunctionSummaryCache(max_size=1000)

        # Populate cache
        for i in range(1000):
            cache.put(FunctionTaintSummary(f"func{i}", {0}, True))

        # Benchmark: cache hit should be very fast
        result = benchmark(lambda: cache.get("func500"))

        assert result is not None

    def test_cache_miss_performance(self, benchmark):
        """Benchmark cache miss performance"""
        cache = FunctionSummaryCache()

        # Benchmark: cache miss should also be fast (just dict lookup)
        result = benchmark(lambda: cache.get("nonexistent"))

        assert result is None

    def test_lru_eviction_performance(self, benchmark):
        """Benchmark LRU eviction"""
        cache = FunctionSummaryCache(max_size=100)

        # Fill cache
        for i in range(100):
            cache.put(FunctionTaintSummary(f"func{i}", {0}, True))

        # Benchmark: adding item with eviction
        def add_with_eviction():
            cache.put(FunctionTaintSummary("new_func", {0}, True))

        benchmark(add_with_eviction)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
