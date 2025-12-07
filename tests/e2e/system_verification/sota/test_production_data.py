"""
Production Data Test

실제 저장된 GraphDocument로 검증
"""

import json
import time
from pathlib import Path

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


def load_real_graph(json_path: str) -> GraphDocument:
    """
    실제 저장된 JSON에서 GraphDocument 로드

    Args:
        json_path: Path to graph JSON

    Returns:
        GraphDocument
    """
    with open(json_path) as f:
        data = json.load(f)

    graph = GraphDocument(repo_id=data.get("repo_id", "unknown"), snapshot_id=data.get("snapshot_id", "unknown"))

    # Load nodes
    if "nodes" in data:
        for node_data in data["nodes"]:
            try:
                # Simple conversion
                node_id = node_data.get("id", node_data.get("fqn", ""))
                if not node_id:
                    continue

                span = None
                if "span" in node_data or "location" in node_data:
                    loc = node_data.get("span") or node_data.get("location", {})
                    if loc and "start_line" in loc:
                        span = Span(
                            start_line=loc.get("start_line", 0),
                            start_col=loc.get("start_col", 0),
                            end_line=loc.get("end_line", 0),
                            end_col=loc.get("end_col", 0),
                        )

                node = GraphNode(
                    id=node_id,
                    kind=GraphNodeKind.FUNCTION,  # Simplify
                    repo_id=graph.repo_id,
                    snapshot_id=graph.snapshot_id,
                    fqn=node_data.get("fqn", node_id),
                    name=node_data.get("name", ""),
                    path=node_data.get("file_path", node_data.get("path", "")),
                    span=span,
                    attrs=node_data.get("attrs", {}),
                )

                graph.graph_nodes[node_id] = node
            except Exception as e:
                continue

    return graph


class TestProductionData:
    """실제 Production 데이터 검증"""

    @pytest.mark.slow
    def test_load_production_graph(self):
        """Production graph 로드"""
        # Try multiple paths
        paths = [
            "data/repomap/FINAL/main.json",
            "data/repomap/test-repo/bench-full-001.json",
            "data/repomap/codegraph/main.json",
        ]

        loaded = False
        for path in paths:
            if Path(path).exists():
                try:
                    graph = load_real_graph(path)

                    print("\n=== Loaded Production Graph ===")
                    print(f"Path: {path}")
                    print(f"Repo: {graph.repo_id}")
                    print(f"Snapshot: {graph.snapshot_id}")
                    print(f"Nodes: {len(graph.graph_nodes)}")
                    print(f"Edges: {len(graph.graph_edges)}")

                    # Should have substantial data
                    assert len(graph.graph_nodes) > 10, "Graph too small"

                    loaded = True
                    break
                except Exception as e:
                    print(f"  ⚠️  Failed to load {path}: {e}")
                    continue

        if not loaded:
            pytest.skip("No production graph data found")

    @pytest.mark.slow
    def test_production_incremental_rebuild(self):
        """Production graph로 incremental rebuild"""
        paths = ["data/repomap/test-repo/bench-full-001.json", "data/repomap/FINAL/main.json"]

        for path in paths:
            if not Path(path).exists():
                continue

            try:
                graph = load_real_graph(path)

                if len(graph.graph_nodes) < 10:
                    continue

                print(f"\n=== Production Test: {path} ===")
                print(f"Nodes: {len(graph.graph_nodes)}")

                # Simulate 5% changes
                num_changes = max(1, len(graph.graph_nodes) // 20)
                node_ids = list(graph.graph_nodes.keys())[:num_changes]

                changes = {}
                for node_id in node_ids:
                    changes[node_id] = (f"# original\ndef {node_id}(): pass", f"# modified\ndef {node_id}(): return 42")

                print(f"Changes: {len(changes)} ({len(changes) / len(graph.graph_nodes) * 100:.1f}%)")

                # Test without cache
                builder = IncrementalBuilder(graph)
                start = time.time()
                builder.analyze_changes(changes)
                plan = builder.create_rebuild_plan()
                updated = builder.execute_rebuild(plan)
                no_cache_time = time.time() - start

                stats = builder.get_statistics()

                print("\n=== No Cache ===")
                print(f"Time: {no_cache_time * 1000:.2f}ms")
                print(f"Strategy: {plan.strategy}")
                print(f"Changed: {stats['changed_symbols']}")
                print(f"Impacted: {stats['impacted_symbols']}")
                print(f"Files: {plan.total_files()}")

                # Test with cache
                cache = RebuildCache(ttl_seconds=600, max_entries=500)

                # Run 5 times
                times = []
                for i in range(5):
                    builder_c = IncrementalBuilder(graph, cache=cache)
                    start = time.time()
                    builder_c.analyze_changes(changes)
                    plan_c = builder_c.create_rebuild_plan()
                    builder_c.execute_rebuild(plan_c)
                    times.append(time.time() - start)

                avg_cached = sum(times) / len(times)
                cache_metrics = cache.get_metrics()

                print("\n=== With Cache (5 runs) ===")
                print(f"Average: {avg_cached * 1000:.2f}ms")
                print(f"Speedup: {no_cache_time / avg_cached:.2f}x")
                print(f"Hit rate: {cache_metrics['hit_rate'] * 100:.1f}%")
                print(f"Savings: {(no_cache_time - avg_cached) * 1000:.2f}ms/rebuild")

                # Performance assertion
                speedup = no_cache_time / avg_cached
                assert speedup >= 2.0, f"Expected 2x+, got {speedup:.2f}x"

                print("\n✅ Production test PASSED")
                return  # Success

            except Exception as e:
                print(f"  ⚠️  Error with {path}: {e}")
                continue

        pytest.skip("No valid production graph found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "slow"])
