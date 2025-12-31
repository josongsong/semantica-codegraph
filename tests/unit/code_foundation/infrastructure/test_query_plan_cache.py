"""
QueryPlan Cache Unit Tests (SOTA)

RFC-052: MCP Service Layer Architecture
Tests for QueryPlanCache LRU implementation.

Test Coverage:
- Cache hit/miss
- LRU eviction
- TTL expiration
- Snapshot invalidation
- Statistics
"""

import time

import pytest

from codegraph_engine.code_foundation.domain.query.query_plan import (
    Budget,
    dataflow_plan,
    slice_plan,
)
from codegraph_engine.code_foundation.infrastructure.query.query_plan_cache import (
    QueryPlanCache,
)


class TestQueryPlanCacheBasics:
    """Basic cache operations"""

    def test_cache_miss_initially(self):
        """Initial cache state is empty (miss)"""
        cache = QueryPlanCache()
        plan = slice_plan("main")

        result = cache.get("snap_001", plan)

        assert result is None

    def test_cache_put_and_get(self):
        """Put and get cache entry"""
        cache = QueryPlanCache()
        plan = slice_plan("main")

        # Put
        cache.put("snap_001", plan, {"result": "data"}, evidence_id="ev_001")

        # Get
        cached = cache.get("snap_001", plan)

        assert cached is not None
        assert cached.result == {"result": "data"}
        assert cached.evidence_id == "ev_001"
        assert cached.hit_count == 1

    def test_cache_hit_increments_count(self):
        """Cache hit increments hit_count"""
        cache = QueryPlanCache()
        plan = slice_plan("main")

        cache.put("snap_001", plan, "data")

        # Hit multiple times
        for _ in range(5):
            cached = cache.get("snap_001", plan)
            assert cached is not None

        # Check hit count
        cached = cache.get("snap_001", plan)
        assert cached.hit_count == 6  # 5 + 1

    def test_cache_different_snapshots(self):
        """Different snapshots have separate cache entries"""
        cache = QueryPlanCache()
        plan = slice_plan("main")

        cache.put("snap_001", plan, "data1")
        cache.put("snap_002", plan, "data2")

        # Both should be cached separately
        cached1 = cache.get("snap_001", plan)
        cached2 = cache.get("snap_002", plan)

        assert cached1.result == "data1"
        assert cached2.result == "data2"

    def test_cache_different_plans(self):
        """Different plans have separate cache entries"""
        cache = QueryPlanCache()

        plan1 = slice_plan("func1")
        plan2 = slice_plan("func2")

        cache.put("snap_001", plan1, "result1")
        cache.put("snap_001", plan2, "result2")

        # Both should be cached
        assert cache.get("snap_001", plan1).result == "result1"
        assert cache.get("snap_001", plan2).result == "result2"

    def test_cache_different_budgets(self):
        """Different budgets create separate cache entries"""
        cache = QueryPlanCache()

        plan_light = slice_plan("main", budget=Budget.light())
        plan_heavy = slice_plan("main", budget=Budget.heavy())

        cache.put("snap_001", plan_light, "light_result")
        cache.put("snap_001", plan_heavy, "heavy_result")

        # Different cache entries
        assert cache.get("snap_001", plan_light).result == "light_result"
        assert cache.get("snap_001", plan_heavy).result == "heavy_result"


class TestQueryPlanCacheLRU:
    """LRU eviction tests"""

    def test_lru_eviction(self):
        """LRU eviction when cache is full"""
        cache = QueryPlanCache(max_size=3)

        plans = [slice_plan(f"func{i}") for i in range(4)]

        # Fill cache (3 entries)
        for i in range(3):
            cache.put("snap_001", plans[i], f"data{i}")

        # Add 4th entry → LRU eviction (plans[0] evicted)
        cache.put("snap_001", plans[3], "data3")

        # plans[0] should be evicted
        assert cache.get("snap_001", plans[0]) is None

        # plans[1], plans[2], plans[3] should remain
        assert cache.get("snap_001", plans[1]) is not None
        assert cache.get("snap_001", plans[2]) is not None
        assert cache.get("snap_001", plans[3]) is not None

    def test_lru_access_updates_order(self):
        """Accessing entry moves it to end (LRU)"""
        cache = QueryPlanCache(max_size=3)

        plans = [slice_plan(f"func{i}") for i in range(4)]

        # Fill cache
        for i in range(3):
            cache.put("snap_001", plans[i], f"data{i}")

        # Access plans[0] (moves to end)
        cache.get("snap_001", plans[0])

        # Add 4th entry → plans[1] evicted (not plans[0])
        cache.put("snap_001", plans[3], "data3")

        # plans[0] should remain
        assert cache.get("snap_001", plans[0]) is not None

        # plans[1] should be evicted
        assert cache.get("snap_001", plans[1]) is None


class TestQueryPlanCacheTTL:
    """TTL expiration tests"""

    def test_ttl_expiration(self):
        """Cache entry expires after TTL"""
        cache = QueryPlanCache(ttl_seconds=1)  # 1 second TTL
        plan = slice_plan("main")

        cache.put("snap_001", plan, "data")

        # Should be cached
        assert cache.get("snap_001", plan) is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert cache.get("snap_001", plan) is None


class TestQueryPlanCacheInvalidation:
    """Cache invalidation tests"""

    def test_invalidate_by_snapshot(self):
        """Invalidate all entries for a snapshot"""
        cache = QueryPlanCache()

        # Add entries for multiple snapshots
        plan1 = slice_plan("func1")
        plan2 = slice_plan("func2")

        cache.put("snap_001", plan1, "data1")
        cache.put("snap_001", plan2, "data2")
        cache.put("snap_002", plan1, "data3")

        # Invalidate snap_001
        invalidated = cache.invalidate_snapshot("snap_001")

        assert invalidated == 2

        # snap_001 entries should be gone
        assert cache.get("snap_001", plan1) is None
        assert cache.get("snap_001", plan2) is None

        # snap_002 should remain
        assert cache.get("snap_002", plan1) is not None

    def test_clear_cache(self):
        """Clear all cache entries"""
        cache = QueryPlanCache()

        # Add entries
        for i in range(5):
            plan = slice_plan(f"func{i}")
            cache.put("snap_001", plan, f"data{i}")

        # Clear
        cache.clear()

        # All should be gone
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestQueryPlanCacheStatistics:
    """Cache statistics tests"""

    def test_hit_rate_calculation(self):
        """Hit rate is calculated correctly"""
        cache = QueryPlanCache()
        plan = slice_plan("main")

        cache.put("snap_001", plan, "data")

        # 3 hits
        for _ in range(3):
            cache.get("snap_001", plan)

        # 2 misses
        other_plan = slice_plan("other")
        cache.get("snap_001", other_plan)
        cache.get("snap_002", plan)

        stats = cache.get_stats()

        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.6  # 3/(3+2)

    def test_stats_includes_size(self):
        """Stats include cache size"""
        cache = QueryPlanCache(max_size=10)

        # Add 5 entries
        for i in range(5):
            plan = slice_plan(f"func{i}")
            cache.put("snap_001", plan, f"data{i}")

        stats = cache.get_stats()

        assert stats["size"] == 5
        assert stats["max_size"] == 10
