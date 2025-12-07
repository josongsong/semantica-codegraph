"""
Cache Performance Test

2-3배 성능 향상 검증
"""

import time

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument, GraphNode, GraphNodeKind, Span
from src.contexts.reasoning_engine.application.incremental_builder import IncrementalBuilder
from src.contexts.reasoning_engine.infrastructure.cache.rebuild_cache import RebuildCache


@pytest.fixture
def large_graph():
    """Larger graph for performance testing"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    # Create 50 functions
    for i in range(1, 51):
        graph.graph_nodes[f"f{i}"] = GraphNode(
            id=f"f{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="s1",
            fqn=f"f{i}",
            name=f"func{i}",
            path=f"file{i // 10}.py",
            span=Span(start_line=i * 10, start_col=0, end_line=i * 10 + 5, end_col=0),
            attrs={},
        )

    return graph


class TestCachePerformance:
    """성능 측정"""

    def test_cache_speedup(self, large_graph):
        """Cache 2-3배 speedup 검증"""
        cache = RebuildCache()

        changes = {f"f{i}": (f"old{i}", f"new{i}") for i in range(1, 11)}

        # No cache (baseline)
        builder_no_cache = IncrementalBuilder(large_graph)
        start = time.time()
        builder_no_cache.analyze_changes(changes)
        plan = builder_no_cache.create_rebuild_plan()
        builder_no_cache.execute_rebuild(plan)
        no_cache_time = time.time() - start

        # With cache (first run - miss)
        builder_cache1 = IncrementalBuilder(large_graph, cache=cache)
        start = time.time()
        builder_cache1.analyze_changes(changes)
        plan = builder_cache1.create_rebuild_plan()
        builder_cache1.execute_rebuild(plan)
        cache_miss_time = time.time() - start

        # With cache (second run - hit)
        builder_cache2 = IncrementalBuilder(large_graph, cache=cache)
        start = time.time()
        builder_cache2.analyze_changes(changes)
        plan = builder_cache2.create_rebuild_plan()
        builder_cache2.execute_rebuild(plan)
        cache_hit_time = time.time() - start

        # Print results
        print("\n--- Performance Results ---")
        print(f"No cache:    {no_cache_time * 1000:.2f}ms")
        print(f"Cache miss:  {cache_miss_time * 1000:.2f}ms")
        print(f"Cache hit:   {cache_hit_time * 1000:.2f}ms")
        print(f"Speedup:     {no_cache_time / cache_hit_time:.2f}x")

        # Verify speedup
        speedup = no_cache_time / cache_hit_time
        assert speedup >= 2.0, f"Expected 2x speedup, got {speedup:.2f}x"

        # Cache metrics
        metrics = cache.get_metrics()
        print("\n--- Cache Metrics ---")
        print(f"Hit rate:    {metrics['hit_rate'] * 100:.1f}%")
        print(f"Hits:        {metrics['hits']}")
        print(f"Misses:      {metrics['misses']}")

    def test_hit_rate_multiple_runs(self, large_graph):
        """Multiple runs hit rate"""
        cache = RebuildCache()

        changes = {"f1": ("old", "new")}

        # Run 10 times
        for _ in range(10):
            builder = IncrementalBuilder(large_graph, cache=cache)
            builder.analyze_changes(changes)
            plan = builder.create_rebuild_plan()
            builder.execute_rebuild(plan)

        metrics = cache.get_metrics()

        # 1 miss + 9 hits = 90% hit rate
        assert metrics["hit_rate"] >= 0.85
        print(f"\nHit rate after 10 runs: {metrics['hit_rate'] * 100:.1f}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
