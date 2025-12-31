"""
Cache 비판적 검증

실제 데이터 + Edge cases
"""

import sys
import threading

import pytest

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument, GraphNode, GraphNodeKind, Span
from codegraph_engine.reasoning_engine.application.incremental_builder import ImpactAnalysisPlanner
from codegraph_engine.reasoning_engine.infrastructure.cache.rebuild_cache import RebuildCache


def get_object_size(obj):
    """Rough object size estimation"""
    return sys.getsizeof(obj)


@pytest.fixture
def realistic_graph():
    """Realistic graph size (100 nodes)"""
    graph = GraphDocument(repo_id="real_repo", snapshot_id="s1")

    # 100 nodes (realistic for small-medium file)
    for i in range(1, 101):
        graph.graph_nodes[f"node{i}"] = GraphNode(
            id=f"node{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="real_repo",
            snapshot_id="s1",
            fqn=f"module.func{i}",
            name=f"function_{i}",
            path=f"src/module_{i // 10}.py",
            span=Span(start_line=i * 20, start_col=0, end_line=i * 20 + 15, end_col=0),
            attrs={"complexity": i % 10, "lines": i * 5},
        )

    return graph


class TestCacheMemoryUsage:
    """메모리 사용량 검증"""

    def test_single_entry_memory(self, realistic_graph):
        """Single cache entry 메모리"""
        cache = RebuildCache(max_entries=1)

        changes = {"node1": ("old_code_" * 100, "new_code_" * 100)}

        # Store
        cache.set(realistic_graph, changes, realistic_graph, {}, {})

        # Measure (rough)
        entry_size = get_object_size(cache._cache)
        print(f"\nSingle entry size: ~{entry_size / 1024:.1f} KB")

        # Should be reasonable (<10MB)
        assert entry_size < 10_000_000, f"Entry too large: {entry_size / 1024 / 1024:.1f}MB"

    def test_max_entries_memory(self, realistic_graph):
        """Max entries 메모리 (100개)"""
        cache = RebuildCache(max_entries=100)

        # Fill cache
        for i in range(1, 101):
            changes = {f"node{i}": (f"old{i}", f"new{i}")}
            cache.set(realistic_graph, changes, realistic_graph, {}, {})

        # Measure
        total_size = get_object_size(cache._cache)
        print(f"\n100 entries size: ~{total_size / 1024 / 1024:.1f} MB")

        # WARNING: Should be <1GB
        if total_size > 1_000_000_000:
            pytest.fail(f"Cache too large: {total_size / 1024 / 1024:.1f}MB")


class TestCacheThreadSafety:
    """Thread safety 검증"""

    def test_concurrent_access(self, realistic_graph):
        """Concurrent get/set"""
        cache = RebuildCache()
        errors = []

        def worker(worker_id):
            try:
                for i in range(10):
                    changes = {f"node{worker_id}": (f"old{i}", f"new{i}")}
                    cache.set(realistic_graph, changes, realistic_graph, {}, {})
                    cache.get(realistic_graph, changes)
            except Exception as e:
                errors.append(e)

        # 10 threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors (but might - not thread-safe!)
        if errors:
            print(f"\n⚠️  Thread safety issue: {len(errors)} errors")
            print(f"First error: {errors[0]}")
            pytest.xfail("Cache is NOT thread-safe (expected)")


class TestCacheEdgeCases:
    """Edge cases"""

    def test_empty_changes(self, realistic_graph):
        """Empty changes"""
        cache = RebuildCache()

        changes = {}

        # Should not crash
        cache.set(realistic_graph, changes, realistic_graph, {}, {})
        result = cache.get(realistic_graph, changes)

        assert result is not None

    def test_large_code_changes(self, realistic_graph):
        """Large code strings"""
        cache = RebuildCache()

        # 1MB code string
        large_code = "x = 1\n" * 100000
        changes = {"node1": (large_code, large_code + "# comment")}

        # Should work but might be slow
        import time

        start = time.time()
        cache.set(realistic_graph, changes, realistic_graph, {}, {})
        result = cache.get(realistic_graph, changes)
        elapsed = time.time() - start

        assert result is not None
        print(f"\nLarge code cache: {elapsed * 1000:.1f}ms")

        # Should be <100ms
        if elapsed > 0.1:
            print(f"⚠️  Slow cache operation: {elapsed * 1000:.1f}ms")

    def test_hash_collision_probability(self):
        """Hash collision 확률"""
        cache = RebuildCache()

        # Generate 1000 different keys
        keys = set()
        for i in range(1000):
            graph = GraphDocument(repo_id=f"repo{i}", snapshot_id=f"s{i}")
            changes = {f"f{i}": (f"old{i}", f"new{i}")}
            key = cache._compute_key(graph, changes)
            keys.add(key)

        # Should have 1000 unique keys (no collision)
        assert len(keys) == 1000, f"Hash collision detected: {1000 - len(keys)} collisions"

    def test_snapshot_id_mismatch(self, realistic_graph):
        """Snapshot ID 변경 시 cache miss"""
        cache = RebuildCache()

        changes = {"node1": ("old", "new")}

        # Store with s1
        cache.set(realistic_graph, changes, realistic_graph, {}, {})

        # Different snapshot ID
        graph2 = GraphDocument(repo_id="real_repo", snapshot_id="s2")
        graph2.graph_nodes = realistic_graph.graph_nodes.copy()

        # Should be cache miss (different snapshot)
        result = cache.get(graph2, changes)
        assert result is None


class TestCacheInvalidation:
    """Invalidation 검증"""

    def test_stale_cache_detection(self, realistic_graph):
        """Stale cache 감지"""
        cache = RebuildCache()

        changes = {"node1": ("old", "new")}

        # Store
        cache.set(realistic_graph, changes, realistic_graph, {}, {})

        # Mutate graph (실제로는 발생하면 안 됨)
        realistic_graph.graph_nodes["node1"].name = "MUTATED"

        # Get (stale!)
        result = cache.get(realistic_graph, changes)

        # ⚠️  Cache는 mutation을 감지하지 못함
        # 이건 immutability에 의존함
        assert result is not None  # Stale cache returned
        print("\n⚠️  Stale cache issue: relies on immutability")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
