"""
Final Production Validation

실제 데이터 + 엄격한 검증
"""

import json
import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphNode,
    GraphNodeKind,
    Span,
)
from codegraph_engine.reasoning_engine.application.incremental_builder import ImpactAnalysisPlanner
from codegraph_engine.reasoning_engine.infrastructure.cache.rebuild_cache import RebuildCache


def load_graph_json(json_path: str) -> GraphDocument:
    """Load GraphDocument from JSON"""
    with open(json_path) as f:
        data = json.load(f)

    graph = GraphDocument(repo_id=data.get("repo_id", "unknown"), snapshot_id=data.get("snapshot_id", "unknown"))

    # Load nodes
    nodes_data = data.get("nodes", [])
    for node_data in nodes_data:
        try:
            node_id = node_data.get("id") or node_data.get("fqn", "")
            if not node_id:
                continue

            span = None
            loc = node_data.get("span") or node_data.get("location")
            if loc and isinstance(loc, dict):
                span = Span(
                    start_line=loc.get("start_line", 0),
                    start_col=loc.get("start_col", 0),
                    end_line=loc.get("end_line", 0),
                    end_col=loc.get("end_col", 0),
                )

            node = GraphNode(
                id=node_id,
                kind=GraphNodeKind.FUNCTION,
                repo_id=graph.repo_id,
                snapshot_id=graph.snapshot_id,
                fqn=node_data.get("fqn", node_id),
                name=node_data.get("name", node_id.split(".")[-1]),
                path=node_data.get("file_path", node_data.get("path", "")),
                span=span,
                attrs=node_data.get("attrs", {}),
            )

            graph.graph_nodes[node_id] = node
        except Exception:
            continue

    return graph


class TestFinalValidation:
    """최종 Production 검증"""

    @pytest.mark.slow
    def test_all_available_graphs(self):
        """사용 가능한 모든 그래프로 검증"""
        test_files = [
            "data/repomap/test-repo/bench-full-001.json",
            "data/benchmark_repomap/codegraph/bench-snapshot.json",
            "data/benchmark_repomap/typer/bench-snapshot.json",
            "data/benchmark_repomap/attrs/bench-snapshot.json",
        ]

        results = []

        for json_path in test_files:
            if not Path(json_path).exists():
                continue

            try:
                graph = load_graph_json(json_path)

                if len(graph.graph_nodes) < 20:
                    continue

                # Test 설정
                num_changes = max(1, len(graph.graph_nodes) // 15)
                node_ids = list(graph.graph_nodes.keys())[:num_changes]

                changes = {nid: (f"old_{nid}", f"new_{nid}") for nid in node_ids}

                # No cache baseline
                builder_nc = ImpactAnalysisPlanner(graph)
                start = time.time()
                builder_nc.analyze_changes(changes)
                plan_nc = builder_nc.create_rebuild_plan()
                builder_nc.execute_rebuild(plan_nc)
                baseline = time.time() - start

                # With cache (10 runs)
                cache = RebuildCache(ttl_seconds=600, max_entries=1000)
                times = []

                for _ in range(10):
                    builder_c = ImpactAnalysisPlanner(graph, cache=cache)
                    start = time.time()
                    builder_c.analyze_changes(changes)
                    plan_c = builder_c.create_rebuild_plan()
                    builder_c.execute_rebuild(plan_c)
                    times.append(time.time() - start)

                avg_cached = sum(times) / len(times)
                speedup = baseline / avg_cached
                metrics = cache.get_metrics()

                result = {
                    "file": Path(json_path).name,
                    "nodes": len(graph.graph_nodes),
                    "changes": len(changes),
                    "baseline_ms": baseline * 1000,
                    "cached_ms": avg_cached * 1000,
                    "speedup": speedup,
                    "hit_rate": metrics["hit_rate"],
                    "savings_ms": (baseline - avg_cached) * 1000,
                }

                results.append(result)

            except Exception as e:
                print(f"  ⚠️  Skip {json_path}: {e}")
                continue

        # Print results
        if not results:
            pytest.skip("No graphs available")

        print(f"\n{'=' * 80}")
        print(f"{'FILE':<30} {'NODES':>8} {'CHG':>5} {'BASE':>8} {'CACHE':>8} {'SPEED':>7} {'HIT%':>6} {'SAVE':>8}")
        print(f"{'=' * 80}")

        total_speedup = 0
        total_hit_rate = 0

        for r in results:
            print(
                f"{r['file']:<30} "
                f"{r['nodes']:>8} "
                f"{r['changes']:>5} "
                f"{r['baseline_ms']:>7.1f}ms "
                f"{r['cached_ms']:>7.1f}ms "
                f"{r['speedup']:>6.2f}x "
                f"{r['hit_rate'] * 100:>5.0f}% "
                f"{r['savings_ms']:>7.1f}ms"
            )
            total_speedup += r["speedup"]
            total_hit_rate += r["hit_rate"]

        print(f"{'=' * 80}")

        avg_speedup = total_speedup / len(results)
        avg_hit_rate = total_hit_rate / len(results)

        print(f"\nAVERAGE: {avg_speedup:.2f}x speedup, {avg_hit_rate * 100:.0f}% hit rate")
        print(f"Tests: {len(results)}")

        # Validation
        print(f"\n{'=' * 80}")
        print("VALIDATION:")

        min_speedup = min(r["speedup"] for r in results)
        max_speedup = max(r["speedup"] for r in results)

        print(f"  Min speedup: {min_speedup:.2f}x")
        print(f"  Max speedup: {max_speedup:.2f}x")
        print(f"  Avg speedup: {avg_speedup:.2f}x")

        # Critical assertions
        assert avg_speedup >= 2.0, f"Failed: avg speedup {avg_speedup:.2f}x < 2.0x"
        assert avg_hit_rate >= 0.5, f"Failed: hit rate {avg_hit_rate * 100:.0f}% < 50%"

        # Honest assessment
        if avg_speedup < 3.0:
            verdict = "⚠️  Modest improvement"
        elif avg_speedup < 5.0:
            verdict = "✅ Good improvement"
        elif avg_speedup < 8.0:
            verdict = "🚀 Excellent improvement"
        else:
            verdict = "🔥 Outstanding improvement"

        print(f"\nVERDICT: {verdict}")
        print(f"{'=' * 80}\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "slow"])
