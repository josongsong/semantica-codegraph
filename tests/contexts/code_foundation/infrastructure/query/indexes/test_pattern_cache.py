"""
Pattern Cache Unit Tests - L11급

Tests LRU cache for pattern matching optimization.

Test Categories:
- Base: Basic cache hit/miss
- Corner: Empty cache, single entry
- Edge: LRU eviction, capacity limits
- Extreme: 1000+ patterns, concurrent access

SOTA Quality:
- No fakes, no stubs
- Thread safety validated
- All edge cases covered
"""

import threading

import pytest

from codegraph_engine.code_foundation.infrastructure.query.indexes.pattern_cache import (
    PatternCache,
    get_global_pattern_cache,
)


class TestPatternCacheBase:
    """Base functionality tests"""

    def test_cache_initialization(self):
        """Cache should initialize with correct capacity"""
        cache = PatternCache(max_size=100)
        stats = cache.get_stats()

        assert stats["capacity"] == 100
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cache_miss_then_hit(self):
        """First call = miss, second call = hit"""
        cache = PatternCache(max_size=10)
        cache.clear()

        names = {"var_1", "var_2", "test_1"}

        # First call: cache miss
        result1 = cache.match_pattern_fnmatch("var_*", names)
        assert result1 == {"var_1", "var_2"}

        stats1 = cache.get_stats()
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0

        # Second call: cache hit
        result2 = cache.match_pattern_fnmatch("var_*", names)
        assert result2 == result1

        stats2 = cache.get_stats()
        assert stats2["misses"] == 1
        assert stats2["hits"] == 1

    def test_match_pattern_with_ids(self):
        """match_pattern_with_ids should cache full result"""
        cache = PatternCache(max_size=10)
        cache.clear()

        name_to_ids = {
            "var_1": ["id1", "id2"],
            "var_2": ["id3"],
            "test_1": ["id4"],
        }

        # First call: cache miss
        result1 = cache.match_pattern_with_ids("var_*", name_to_ids, lambda n: n.startswith("var_"))
        assert set(result1) == {"id1", "id2", "id3"}

        # Second call: cache hit
        result2 = cache.match_pattern_with_ids("var_*", name_to_ids, lambda n: n.startswith("var_"))
        assert result1 == result2

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1


class TestPatternCacheCorner:
    """Corner case tests"""

    def test_empty_candidates(self):
        """Empty candidates should return empty result"""
        cache = PatternCache(max_size=10)
        result = cache.match_pattern_fnmatch("var_*", set())
        assert result == set()

    def test_no_matches(self):
        """Pattern with no matches should return empty"""
        cache = PatternCache(max_size=10)
        names = {"foo", "bar", "baz"}
        result = cache.match_pattern_fnmatch("var_*", names)
        assert result == set()

    def test_all_match(self):
        """Pattern that matches all should return all"""
        cache = PatternCache(max_size=10)
        names = {"var_1", "var_2", "var_3"}
        result = cache.match_pattern_fnmatch("var_*", names)
        assert result == names


class TestPatternCacheEdge:
    """Edge case tests"""

    def test_lru_eviction_when_full(self):
        """Cache should evict LRU entry when full"""
        cache = PatternCache(max_size=3)
        cache.clear()

        # Fill cache with 3 patterns
        cache.match_pattern_fnmatch("pattern1", {"a", "b"})
        cache.match_pattern_fnmatch("pattern2", {"c", "d"})
        cache.match_pattern_fnmatch("pattern3", {"e", "f"})

        stats = cache.get_stats()
        assert stats["size"] == 3

        # Add 4th pattern: should evict pattern1 (oldest)
        cache.match_pattern_fnmatch("pattern4", {"g", "h"})

        stats = cache.get_stats()
        assert stats["size"] == 3  # Still at capacity

        # pattern1 should be evicted, so accessing it = cache miss
        initial_misses = stats["misses"]
        cache.match_pattern_fnmatch("pattern1", {"a", "b"})

        stats = cache.get_stats()
        assert stats["misses"] == initial_misses + 1, "pattern1 should be evicted"

    def test_lru_move_to_end_on_access(self):
        """Accessing entry should move it to end (prevent eviction)"""
        cache = PatternCache(max_size=3)
        cache.clear()

        # Fill cache
        cache.match_pattern_fnmatch("pattern1", {"a"})
        cache.match_pattern_fnmatch("pattern2", {"b"})
        cache.match_pattern_fnmatch("pattern3", {"c"})

        # Access pattern1 (moves to end)
        cache.match_pattern_fnmatch("pattern1", {"a"})

        # Add new pattern: should evict pattern2 (now oldest)
        cache.match_pattern_fnmatch("pattern4", {"d"})

        # pattern1 should still be cached (was moved to end)
        stats_before = cache.get_stats()
        cache.match_pattern_fnmatch("pattern1", {"a"})
        stats_after = cache.get_stats()

        assert stats_after["hits"] == stats_before["hits"] + 1, "pattern1 should be cached"

    def test_different_candidate_sets_are_different_keys(self):
        """Same pattern with different candidates = different cache entries"""
        cache = PatternCache(max_size=10)
        cache.clear()

        # Same pattern, different candidates
        result1 = cache.match_pattern_fnmatch("var_*", {"var_1", "var_2"})
        result2 = cache.match_pattern_fnmatch("var_*", {"var_3", "var_4"})

        # Should be 2 cache misses (different keys)
        stats = cache.get_stats()
        assert stats["misses"] == 2
        assert stats["hits"] == 0

        # Results should be different
        assert result1 == {"var_1", "var_2"}
        assert result2 == {"var_3", "var_4"}


class TestPatternCacheExtreme:
    """Extreme stress tests"""

    def test_1000_unique_patterns(self):
        """Cache should handle 1000+ patterns with LRU eviction"""
        cache = PatternCache(max_size=100)
        cache.clear()

        names = {f"var_{i}" for i in range(100)}

        # Query 1000 unique patterns
        for i in range(1000):
            pattern = f"var_{i}*"
            cache.match_pattern_fnmatch(pattern, names)

        stats = cache.get_stats()

        # Cache should be at capacity (LRU eviction)
        assert stats["size"] <= 100, "Cache exceeded capacity"
        assert stats["misses"] == 1000, "All should be misses (unique patterns)"

        print(f"\n  ✅ 1000 patterns handled, cache size: {stats['size']}")

    def test_concurrent_access_thread_safe(self):
        """Multiple threads accessing cache concurrently"""
        cache = PatternCache(max_size=50)
        cache.clear()

        names = {f"var_{i}" for i in range(100)}
        errors = []

        def worker():
            try:
                for i in range(100):
                    pattern = f"var_{i % 10}*"  # Repeat patterns for cache hits
                    cache.match_pattern_fnmatch(pattern, names)
            except Exception as e:
                errors.append(str(e))

        # Launch 10 threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify: no errors
        assert not errors, f"Thread safety violations: {errors}"

        # Verify: cache stats are consistent
        stats = cache.get_stats()
        assert stats["hits"] + stats["misses"] == 1000, "Total should be 1000"

        print("\n  ✅ 1000 concurrent queries across 10 threads")
        print(f"     Hit rate: {stats['hit_rate_pct']:.1f}%")


class TestGlobalCacheSingleton:
    """Test global cache singleton"""

    def test_global_cache_is_singleton(self):
        """get_global_pattern_cache should return same instance"""
        cache1 = get_global_pattern_cache()
        cache2 = get_global_pattern_cache()

        assert cache1 is cache2, "Should be same instance"

    def test_global_cache_shared_across_indexes(self):
        """Global cache should be shared across all SemanticIndex instances"""
        cache = get_global_pattern_cache()
        cache.clear()

        # First index uses cache
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.query.indexes.node_index import NodeIndex
        from codegraph_engine.code_foundation.infrastructure.query.indexes.semantic_index import SemanticIndex

        ir_doc1 = IRDocument(repo_id="test1", snapshot_id="v1")
        ir_doc1.dfg_snapshot = DfgSnapshot(
            variables=[
                VariableEntity(
                    id="var:1", repo_id="test1", file_path="test.py", function_fqn="func", name="var_1", kind="local"
                )
            ]
        )
        node_index1 = NodeIndex(ir_doc1)
        index1 = SemanticIndex(ir_doc1, node_index1)

        # Query pattern (cache miss)
        index1.find_vars_by_pattern("var_*")

        stats_after_index1 = cache.get_stats()
        misses_after_index1 = stats_after_index1["misses"]

        # Second index should reuse cache
        ir_doc2 = IRDocument(repo_id="test2", snapshot_id="v1")
        ir_doc2.dfg_snapshot = DfgSnapshot(
            variables=[
                VariableEntity(
                    id="var:2", repo_id="test2", file_path="test.py", function_fqn="func", name="var_2", kind="local"
                )
            ]
        )
        node_index2 = NodeIndex(ir_doc2)
        index2 = SemanticIndex(ir_doc2, node_index2)

        # Query same pattern (but different names set)
        # This will be a miss because frozenset(names) is different
        index2.find_vars_by_pattern("var_*")

        stats_after_index2 = cache.get_stats()

        # Should have incremented misses (different name sets = different cache keys)
        assert stats_after_index2["misses"] > misses_after_index1

        print("\n  ✅ Global cache shared across indexes")
        print(f"     Total misses: {stats_after_index2['misses']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
