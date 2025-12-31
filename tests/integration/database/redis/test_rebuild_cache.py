"""
Rebuild Cache Tests
"""

import time

import pytest

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument, GraphNode, GraphNodeKind, Span
from codegraph_engine.reasoning_engine.application.incremental_builder import ImpactAnalysisPlanner
from codegraph_engine.reasoning_engine.infrastructure.cache.rebuild_cache import CacheEntry, RebuildCache


@pytest.fixture
def sample_graph():
    """Sample graph"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    for i in range(1, 4):
        graph.graph_nodes[f"f{i}"] = GraphNode(
            id=f"f{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="s1",
            fqn=f"f{i}",
            name=f"func{i}",
            path="test.py",
            span=Span(start_line=i * 10, start_col=0, end_line=i * 10 + 5, end_col=0),
            attrs={},
        )

    return graph


class TestRebuildCache:
    """Cache 기본 테스트"""

    def test_cache_initialization(self):
        """초기화"""
        cache = RebuildCache(ttl_seconds=300, max_entries=100)

        assert cache.ttl_seconds == 300
        assert cache.max_entries == 100
        assert cache.hits == 0
        assert cache.misses == 0

    def test_cache_miss(self, sample_graph):
        """Cache miss"""
        cache = RebuildCache()

        changes = {"f1": ("old", "new")}
        result = cache.get(sample_graph, changes)

        assert result is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_cache_hit(self, sample_graph):
        """Cache hit"""
        cache = RebuildCache()

        changes = {"f1": ("old", "new")}

        # Store
        cache.set(
            sample_graph,
            changes,
            sample_graph,  # Dummy updated_graph
            {"strategy": "minimal"},
            {"changed_symbols": 1},
        )

        # Retrieve
        result = cache.get(sample_graph, changes)

        assert result is not None
        assert cache.hits == 1
        assert cache.misses == 0
        assert result.rebuild_plan["strategy"] == "minimal"

    def test_cache_key_computation(self, sample_graph):
        """Cache key 일관성"""
        cache = RebuildCache()

        changes1 = {"f1": ("old", "new"), "f2": ("old2", "new2")}
        changes2 = {"f2": ("old2", "new2"), "f1": ("old", "new")}  # Same, different order

        key1 = cache._compute_key(sample_graph, changes1)
        key2 = cache._compute_key(sample_graph, changes2)

        # Should be same (order-independent)
        assert key1 == key2

    def test_cache_expiration(self, sample_graph):
        """TTL expiration"""
        cache = RebuildCache(ttl_seconds=1)  # 1 second

        changes = {"f1": ("old", "new")}

        # Store
        cache.set(sample_graph, changes, sample_graph, {}, {})

        # Immediate hit
        result = cache.get(sample_graph, changes)
        assert result is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        result = cache.get(sample_graph, changes)
        assert result is None
        assert cache.expirations == 1

    def test_cache_lru_eviction(self, sample_graph):
        """LRU eviction"""
        cache = RebuildCache(max_entries=2)

        # Add 3 entries (exceeds max)
        for i in range(1, 4):
            changes = {f"f{i}": ("old", "new")}
            cache.set(sample_graph, changes, sample_graph, {}, {})

        # Should have evicted 1
        assert len(cache._cache) == 2
        assert cache.evictions == 1

        # First entry should be evicted (LRU)
        changes1 = {"f1": ("old", "new")}
        result = cache.get(sample_graph, changes1)
        assert result is None  # Evicted

    def test_cache_invalidation_specific(self, sample_graph):
        """특정 entry invalidation"""
        cache = RebuildCache()

        changes = {"f1": ("old", "new")}
        cache.set(sample_graph, changes, sample_graph, {}, {})

        # Invalidate
        cache.invalidate(sample_graph, changes)

        # Should be gone
        result = cache.get(sample_graph, changes)
        assert result is None

    def test_cache_invalidation_all(self, sample_graph):
        """전체 invalidation"""
        cache = RebuildCache()

        # Add multiple entries
        for i in range(1, 4):
            changes = {f"f{i}": ("old", "new")}
            cache.set(sample_graph, changes, sample_graph, {}, {})

        assert len(cache._cache) == 3

        # Clear all
        cache.invalidate()

        assert len(cache._cache) == 0

    def test_cache_metrics(self, sample_graph):
        """Metrics"""
        cache = RebuildCache()

        changes1 = {"f1": ("old", "new")}
        changes2 = {"f2": ("old", "new")}

        # Miss
        cache.get(sample_graph, changes1)

        # Set + Hit
        cache.set(sample_graph, changes1, sample_graph, {}, {})
        cache.get(sample_graph, changes1)

        # Another miss
        cache.get(sample_graph, changes2)

        metrics = cache.get_metrics()

        assert metrics["hits"] == 1
        assert metrics["misses"] == 2
        assert metrics["hit_rate"] == 1 / 3
        assert metrics["current_size"] == 1


class TestImpactAnalysisPlannerWithCache:
    """ImpactAnalysisPlanner + Cache 통합"""

    def test_builder_with_cache(self, sample_graph):
        """Builder with cache"""
        cache = RebuildCache()
        builder = ImpactAnalysisPlanner(sample_graph, cache=cache)

        assert builder.cache == cache

    def test_cache_integration(self, sample_graph):
        """Cache 통합 (hit/miss)"""
        cache = RebuildCache()

        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}

        # First build (miss)
        builder1 = ImpactAnalysisPlanner(sample_graph, cache=cache)
        builder1.analyze_changes(changes)
        plan1 = builder1.create_rebuild_plan()
        graph1 = builder1.execute_rebuild(plan1)

        assert cache.misses == 1
        assert cache.hits == 0

        # Second build (hit)
        builder2 = ImpactAnalysisPlanner(sample_graph, cache=cache)
        builder2.analyze_changes(changes)
        plan2 = builder2.create_rebuild_plan()
        graph2 = builder2.execute_rebuild(plan2)

        assert cache.misses == 1
        assert cache.hits == 1

        # Should be same graph
        assert len(graph1.graph_nodes) == len(graph2.graph_nodes)

    def test_cache_stats_in_builder(self, sample_graph):
        """Builder statistics with cache"""
        cache = RebuildCache()
        builder = ImpactAnalysisPlanner(sample_graph, cache=cache)

        changes = {"f1": ("old", "new")}
        builder.analyze_changes(changes)

        stats = builder.get_statistics()

        # Should have cache metrics
        assert "cache" in stats
        assert "hit_rate" in stats["cache"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
