"""
SOTA Real-World Benchmark

실제 src/contexts 코드베이스로 테스트
"""

import ast
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    Span,
)
from src.contexts.reasoning_engine.application.incremental_builder import IncrementalBuilder
from src.contexts.reasoning_engine.infrastructure.cache.rebuild_cache import RebuildCache


def build_graph_from_real_code(max_files: int = 50) -> tuple[GraphDocument, dict[str, str]]:
    """
    실제 src/contexts 코드에서 GraphDocument 생성

    Returns:
        (graph, file_contents)
    """
    graph = GraphDocument(repo_id="semantica", snapshot_id="prod_v1")
    file_contents = {}

    # Find Python files
    src_path = Path("src/contexts")
    py_files = list(src_path.rglob("*.py"))[:max_files]

    print(f"\nBuilding graph from {len(py_files)} real Python files...")

    node_count = 0
    for py_file in py_files:
        try:
            content = py_file.read_text()
            file_contents[str(py_file)] = content

            # Parse AST
            tree = ast.parse(content)

            # Extract functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    node_id = f"{py_file.stem}.{node.name}"
                    graph.graph_nodes[node_id] = GraphNode(
                        id=node_id,
                        kind=GraphNodeKind.FUNCTION,
                        repo_id="semantica",
                        snapshot_id="prod_v1",
                        fqn=f"{py_file.stem}.{node.name}",
                        name=node.name,
                        path=str(py_file),
                        span=Span(
                            start_line=node.lineno,
                            start_col=node.col_offset,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            end_col=getattr(node, "end_col_offset", 0),
                        ),
                        attrs={"docstring": ast.get_docstring(node) or ""},
                    )
                    node_count += 1

                elif isinstance(node, ast.ClassDef):
                    node_id = f"{py_file.stem}.{node.name}"
                    graph.graph_nodes[node_id] = GraphNode(
                        id=node_id,
                        kind=GraphNodeKind.CLASS,
                        repo_id="semantica",
                        snapshot_id="prod_v1",
                        fqn=f"{py_file.stem}.{node.name}",
                        name=node.name,
                        path=str(py_file),
                        span=Span(
                            start_line=node.lineno,
                            start_col=node.col_offset,
                            end_line=getattr(node, "end_lineno", node.lineno),
                            end_col=getattr(node, "end_col_offset", 0),
                        ),
                        attrs={"docstring": ast.get_docstring(node) or ""},
                    )
                    node_count += 1

        except Exception as e:
            print(f"  ⚠️  Error parsing {py_file}: {e}")
            continue

    print(f"  ✅ Created graph: {node_count} nodes from {len(py_files)} files")
    return graph, file_contents


class TestRealWorldBenchmark:
    """SOTA Real-world 벤치마크"""

    @pytest.mark.slow
    def test_real_graph_scale(self):
        """실제 코드베이스 규모 테스트"""
        graph, files = build_graph_from_real_code(max_files=50)

        print("\n=== Real Graph Stats ===")
        print(f"Nodes: {len(graph.graph_nodes)}")
        print(f"Files: {len(files)}")
        print(f"Avg nodes/file: {len(graph.graph_nodes) / len(files):.1f}")

        # Should have substantial data
        assert len(graph.graph_nodes) > 50, "Need more nodes for SOTA test"
        assert len(files) > 10, "Need more files"

    @pytest.mark.slow
    def test_real_incremental_rebuild(self):
        """실제 incremental rebuild 성능"""
        graph, files = build_graph_from_real_code(max_files=50)

        # Simulate realistic changes (5% of nodes)
        num_changes = max(1, len(graph.graph_nodes) // 20)
        node_ids = list(graph.graph_nodes.keys())[:num_changes]

        changes = {}
        for node_id in node_ids:
            changes[node_id] = (f"# old version\ndef {node_id}(): pass", f"# new version\ndef {node_id}(): return 42")

        print("\n=== Incremental Rebuild Test ===")
        print(f"Graph size: {len(graph.graph_nodes)} nodes")
        print(f"Changes: {len(changes)} ({len(changes) / len(graph.graph_nodes) * 100:.1f}%)")

        # Rebuild
        builder = IncrementalBuilder(graph)

        start = time.time()
        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()
        updated = builder.execute_rebuild(plan)
        elapsed = time.time() - start

        stats = builder.get_statistics()

        print("\n=== Results ===")
        print(f"Time: {elapsed * 1000:.1f}ms")
        print(f"Strategy: {plan.strategy}")
        print(f"Changed: {stats['changed_symbols']}")
        print(f"Impacted: {stats['impacted_symbols']}")
        print(f"Files to rebuild: {plan.total_files()}")

        # Performance assertions
        assert elapsed < 0.5, f"Too slow: {elapsed * 1000:.1f}ms"
        assert plan.strategy in ["minimal", "partial"], "Should use incremental strategy"

    @pytest.mark.slow
    def test_real_cache_performance(self):
        """실제 cache 성능 (SOTA)"""
        graph, files = build_graph_from_real_code(max_files=50)
        cache = RebuildCache(ttl_seconds=600, max_entries=200)

        # Realistic changes
        num_changes = max(1, len(graph.graph_nodes) // 20)
        node_ids = list(graph.graph_nodes.keys())[:num_changes]

        changes = {}
        for node_id in node_ids:
            changes[node_id] = (f"old_{node_id}", f"new_{node_id}")

        print("\n=== Cache Performance Test ===")
        print(f"Graph: {len(graph.graph_nodes)} nodes")
        print(f"Changes: {len(changes)}")

        # Run 1: No cache (baseline)
        builder1 = IncrementalBuilder(graph)
        start = time.time()
        builder1.analyze_changes(changes)
        plan1 = builder1.create_rebuild_plan()
        builder1.execute_rebuild(plan1)
        baseline_time = time.time() - start

        # Run 2: Cache miss
        builder2 = IncrementalBuilder(graph, cache=cache)
        start = time.time()
        builder2.analyze_changes(changes)
        plan2 = builder2.create_rebuild_plan()
        builder2.execute_rebuild(plan2)
        cache_miss_time = time.time() - start

        # Run 3: Cache hit
        builder3 = IncrementalBuilder(graph, cache=cache)
        start = time.time()
        builder3.analyze_changes(changes)
        plan3 = builder3.create_rebuild_plan()
        builder3.execute_rebuild(plan3)
        cache_hit_time = time.time() - start

        # Run 4-10: More cache hits
        for i in range(4, 11):
            builder = IncrementalBuilder(graph, cache=cache)
            builder.analyze_changes(changes)
            plan = builder.create_rebuild_plan()
            builder.execute_rebuild(plan)

        metrics = cache.get_metrics()
        speedup = baseline_time / cache_hit_time

        print("\n=== Performance Results ===")
        print(f"Baseline:    {baseline_time * 1000:.2f}ms")
        print(f"Cache miss:  {cache_miss_time * 1000:.2f}ms")
        print(f"Cache hit:   {cache_hit_time * 1000:.2f}ms")
        print(f"Speedup:     {speedup:.2f}x")

        print("\n=== Cache Metrics ===")
        print(f"Hit rate:    {metrics['hit_rate'] * 100:.1f}%")
        print(f"Hits:        {metrics['hits']}")
        print(f"Misses:      {metrics['misses']}")
        print(f"Size:        {metrics['current_size']}/{metrics['max_size']}")

        # SOTA assertions
        assert speedup >= 3.0, f"Expected 3x+ speedup, got {speedup:.2f}x"
        assert metrics["hit_rate"] >= 0.80, f"Hit rate too low: {metrics['hit_rate']}"
        assert cache_hit_time < 0.05, f"Cache hit too slow: {cache_hit_time * 1000:.1f}ms"

    @pytest.mark.slow
    def test_memory_usage_real_data(self):
        """실제 데이터 메모리 사용량"""
        graph, files = build_graph_from_real_code(max_files=50)
        cache = RebuildCache(max_entries=100)

        # Fill cache with different changes
        for i in range(50):
            node_ids = list(graph.graph_nodes.keys())[i : i + 5]
            changes = {nid: (f"old_{i}", f"new_{i}") for nid in node_ids if nid}

            if changes:
                builder = IncrementalBuilder(graph, cache=cache)
                builder.analyze_changes(changes)
                plan = builder.create_rebuild_plan()
                builder.execute_rebuild(plan)

        metrics = cache.get_metrics()

        print("\n=== Memory Test ===")
        print(f"Graph size: {len(graph.graph_nodes)} nodes")
        print(f"Cache size: {metrics['current_size']}/{metrics['max_size']}")
        print(f"Evictions: {metrics['evictions']}")
        print(f"Hit rate: {metrics['hit_rate'] * 100:.1f}%")

        # Should handle evictions gracefully
        assert metrics["current_size"] <= metrics["max_size"]
        assert metrics["evictions"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "slow"])
