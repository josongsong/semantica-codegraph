"""
RFC-039 P0.5: Tests for Priority-based Memory Cache
"""

import time
import threading

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.cache.priority_cache import (
    CacheEntry,
    PriorityCacheStats,
    PriorityMemoryCache,
)


class TestCacheEntry:
    """CacheEntry tests."""

    def test_initial_values(self):
        """Entry starts with access_count=1."""
        entry = CacheEntry(value="test", size_bytes=100)
        assert entry.access_count == 1
        assert entry.size_bytes == 100

    def test_touch_increments_access_count(self):
        """touch() increments access_count."""
        entry = CacheEntry(value="test", size_bytes=100)
        entry.touch()
        entry.touch()
        assert entry.access_count == 3

    def test_touch_updates_last_access_time(self):
        """touch() updates last_access_time."""
        entry = CacheEntry(value="test", size_bytes=100)
        original_time = entry.last_access_time
        time.sleep(0.01)
        entry.touch()
        assert entry.last_access_time > original_time

    def test_priority_score_positive(self):
        """Priority score is always positive."""
        entry = CacheEntry(value="test", size_bytes=100)
        score = entry.priority_score(time.time())
        assert score > 0

    def test_priority_higher_for_frequent_access(self):
        """More accessed entries have higher priority."""
        entry1 = CacheEntry(value="test1", size_bytes=100)
        entry2 = CacheEntry(value="test2", size_bytes=100)

        # Access entry1 more
        for _ in range(10):
            entry1.touch()

        current_time = time.time()
        assert entry1.priority_score(current_time) > entry2.priority_score(current_time)

    def test_priority_lower_for_larger_items(self):
        """Larger items have lower priority."""
        small_entry = CacheEntry(value="small", size_bytes=100)
        large_entry = CacheEntry(value="large", size_bytes=10000)

        current_time = time.time()
        assert small_entry.priority_score(current_time) > large_entry.priority_score(current_time)

    def test_priority_decays_over_time(self):
        """Priority decays for stale entries."""
        entry = CacheEntry(value="test", size_bytes=100)
        entry.last_access_time = time.time() - 1000  # 1000 seconds ago

        current_time = time.time()
        old_score = entry.priority_score(current_time)

        # Fresh entry should have higher priority
        fresh_entry = CacheEntry(value="fresh", size_bytes=100)
        fresh_score = fresh_entry.priority_score(current_time)

        assert fresh_score > old_score


class TestPriorityMemoryCache:
    """PriorityMemoryCache tests."""

    def test_basic_get_set(self):
        """Basic get/set operations work."""
        cache = PriorityMemoryCache(max_size=10)

        cache.set("key1", {"data": "value1"})
        result = cache.get("key1")

        assert result == {"data": "value1"}

    def test_cache_miss(self):
        """Missing key returns None."""
        cache = PriorityMemoryCache()
        assert cache.get("nonexistent") is None

    def test_stats_tracking(self):
        """Stats track hits and misses."""
        cache = PriorityMemoryCache()

        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss

        stats = cache.stats()
        assert stats.hits == 1
        assert stats.misses == 1

    def test_size_limit_eviction(self):
        """Evicts entries when size limit exceeded."""
        # Small cache: max 2 entries
        cache = PriorityMemoryCache(max_size=2, max_bytes=1024 * 1024)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict one

        # Only 2 entries should remain
        stats = cache.stats()
        assert stats.evictions >= 1

    def test_priority_eviction_keeps_frequent(self):
        """Priority eviction keeps frequently accessed entries."""
        cache = PriorityMemoryCache(max_size=2, max_bytes=1024 * 1024)

        # Add key1 and access it many times
        cache.set("key1", "value1")
        for _ in range(10):
            cache.get("key1")

        # Add key2 (less accessed)
        cache.set("key2", "value2")

        # Add key3 (should evict key2, not key1)
        cache.set("key3", "value3")

        # key1 should still exist (high priority)
        assert cache.get("key1") == "value1"

    def test_bytes_limit_eviction(self):
        """Evicts entries when bytes limit exceeded."""
        # Very small byte limit
        cache = PriorityMemoryCache(max_size=100, max_bytes=2000)

        # Add entries until bytes exceeded
        for i in range(10):
            cache.set(f"key{i}", {"data": "x" * 100})

        # Should have evicted some
        stats = cache.stats()
        assert stats.evictions > 0
        assert stats.current_bytes <= 2000

    def test_delete(self):
        """Delete removes entry."""
        cache = PriorityMemoryCache()

        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self):
        """Delete nonexistent returns False."""
        cache = PriorityMemoryCache()
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        """Clear removes all entries and resets stats."""
        cache = PriorityMemoryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.get("key1")

        # Check stats before clear
        stats_before = cache.stats()
        assert stats_before.hits == 1

        cache.clear()

        # Stats should be reset
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0

        # Entries should be gone (these add misses)
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_max_size_zero(self):
        """max_size=0 is no-op cache."""
        cache = PriorityMemoryCache(max_size=0)

        cache.set("key1", "value1")
        assert cache.get("key1") is None

    def test_thread_safety(self):
        """Cache is thread-safe."""
        cache = PriorityMemoryCache(max_size=100)
        errors = []

        def worker(worker_id: int):
            try:
                for i in range(50):
                    cache.set(f"key{worker_id}_{i}", f"value{i}")
                    cache.get(f"key{worker_id}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_update_existing_entry(self):
        """Updating existing entry preserves access count."""
        cache = PriorityMemoryCache()

        cache.set("key1", "value1")
        cache.get("key1")  # Access count = 2
        cache.get("key1")  # Access count = 3

        cache.set("key1", "new_value")  # Update, access count = 4

        # Access count should be preserved/incremented
        priorities = cache.get_entry_priorities()
        assert len(priorities) == 1
        key, priority, access_count, size = priorities[0]
        assert access_count >= 4

    def test_get_entry_priorities(self):
        """get_entry_priorities returns correct info."""
        cache = PriorityMemoryCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        priorities = cache.get_entry_priorities()
        assert len(priorities) == 2

        for key, priority, access_count, size in priorities:
            assert key in ("key1", "key2")
            assert priority > 0
            assert access_count >= 1
            assert size > 0


class TestPriorityCacheStats:
    """PriorityCacheStats tests."""

    def test_inherits_base(self):
        """Inherits from BaseCacheStats."""
        from codegraph_engine.code_foundation.infrastructure.ir.cache.core import BaseCacheStats

        assert issubclass(PriorityCacheStats, BaseCacheStats)

    def test_to_dict_includes_priority_fields(self):
        """to_dict includes priority-specific fields."""
        stats = PriorityCacheStats(
            hits=10,
            misses=5,
            evictions=3,
            priority_evictions=2,
            current_bytes=1000,
        )
        d = stats.to_dict()
        assert d["priority_evictions"] == 2
        assert d["current_bytes"] == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
