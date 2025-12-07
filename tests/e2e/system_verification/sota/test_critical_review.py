"""
Critical Review - 정확한 측정

Cache의 실제 효과를 정확히 측정
"""

import time
from pathlib import Path

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument, GraphNode, GraphNodeKind, Span
from src.contexts.reasoning_engine.application.incremental_builder import IncrementalBuilder
from src.contexts.reasoning_engine.infrastructure.cache.rebuild_cache import RebuildCache


def create_realistic_graph(num_nodes=100):
    """Realistic graph"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    for i in range(num_nodes):
        graph.graph_nodes[f"node{i}"] = GraphNode(
            id=f"node{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="s1",
            fqn=f"module.func{i}",
            name=f"func{i}",
            path=f"file_{i // 10}.py",
            span=Span(start_line=i * 10, start_col=0, end_line=i * 10 + 5, end_col=0),
            attrs={},
        )

    return graph


class TestCriticalReview:
    """정확한 측정"""

    def test_breakdown_analysis(self):
        """각 단계별 시간 측정"""
        graph = create_realistic_graph(200)
        cache = RebuildCache()

        changes = {f"node{i}": (f"old{i}", f"new{i}") for i in range(10)}

        print("\n=== Breakdown Analysis (200 nodes, 10 changes) ===")

        # No cache - 각 단계 측정
        builder1 = IncrementalBuilder(graph)

        start = time.time()
        builder1.analyze_changes(changes)
        analyze_time = time.time() - start

        start = time.time()
        plan1 = builder1.create_rebuild_plan()
        plan_time = time.time() - start

        start = time.time()
        updated1 = builder1.execute_rebuild(plan1)
        execute_time = time.time() - start

        total_no_cache = analyze_time + plan_time + execute_time

        print("\nNo Cache:")
        print(f"  analyze_changes: {analyze_time * 1000:.2f}ms")
        print(f"  create_plan:     {plan_time * 1000:.2f}ms")
        print(f"  execute_rebuild: {execute_time * 1000:.2f}ms")
        print(f"  TOTAL:           {total_no_cache * 1000:.2f}ms")

        # With cache - cache miss
        builder2 = IncrementalBuilder(graph, cache=cache)

        start = time.time()
        builder2.analyze_changes(changes)
        analyze_time2 = time.time() - start

        start = time.time()
        plan2 = builder2.create_rebuild_plan()
        plan_time2 = time.time() - start

        start = time.time()
        updated2 = builder2.execute_rebuild(plan2)
        execute_time2 = time.time() - start

        total_cache_miss = analyze_time2 + plan_time2 + execute_time2

        print("\nCache Miss:")
        print(f"  analyze_changes: {analyze_time2 * 1000:.2f}ms")
        print(f"  create_plan:     {plan_time2 * 1000:.2f}ms")
        print(f"  execute_rebuild: {execute_time2 * 1000:.2f}ms (+ cache store)")
        print(f"  TOTAL:           {total_cache_miss * 1000:.2f}ms")

        # With cache - cache hit
        builder3 = IncrementalBuilder(graph, cache=cache)

        start = time.time()
        builder3.analyze_changes(changes)
        analyze_time3 = time.time() - start

        start = time.time()
        plan3 = builder3.create_rebuild_plan()
        plan_time3 = time.time() - start

        start = time.time()
        updated3 = builder3.execute_rebuild(plan3)
        execute_time3 = time.time() - start

        total_cache_hit = analyze_time3 + plan_time3 + execute_time3

        print("\nCache Hit:")
        print(f"  analyze_changes: {analyze_time3 * 1000:.2f}ms")
        print(f"  create_plan:     {plan_time3 * 1000:.2f}ms")
        print(f"  execute_rebuild: {execute_time3 * 1000:.2f}ms (cache hit!)")
        print(f"  TOTAL:           {total_cache_hit * 1000:.2f}ms")

        # Analysis
        execute_speedup = execute_time / execute_time3 if execute_time3 > 0 else float("inf")
        total_speedup = total_no_cache / total_cache_hit

        print("\n=== Speedup Analysis ===")
        print(f"execute_rebuild only: {execute_speedup:.2f}x")
        print(f"Total pipeline:       {total_speedup:.2f}x")

        print("\n=== Reality Check ===")
        print(f"Cache saves:  {(execute_time - execute_time3) * 1000:.2f}ms")
        print(f"Still costs:  {(analyze_time3 + plan_time3) * 1000:.2f}ms")
        print(f"Efficiency:   {(execute_time3 / total_cache_hit) * 100:.1f}% (cache hit / total)")

        # Honest metrics
        metrics = cache.get_metrics()
        print(f"\nCache metrics: {metrics}")

    def test_realistic_scenario(self):
        """실제 시나리오 (반복 rebuild)"""
        graph = create_realistic_graph(200)
        cache = RebuildCache()

        changes = {f"node{i}": (f"old{i}", f"new{i}") for i in range(10)}

        print("\n=== Realistic Scenario ===")
        print("Developer workflow: 같은 파일을 여러 번 수정")

        times_no_cache = []
        times_with_cache = []

        # 10번 반복
        for i in range(10):
            # No cache
            builder_nc = IncrementalBuilder(graph)
            start = time.time()
            builder_nc.analyze_changes(changes)
            plan = builder_nc.create_rebuild_plan()
            builder_nc.execute_rebuild(plan)
            times_no_cache.append(time.time() - start)

            # With cache
            builder_c = IncrementalBuilder(graph, cache=cache)
            start = time.time()
            builder_c.analyze_changes(changes)
            plan = builder_c.create_rebuild_plan()
            builder_c.execute_rebuild(plan)
            times_with_cache.append(time.time() - start)

        avg_no_cache = sum(times_no_cache) / len(times_no_cache)
        avg_with_cache = sum(times_with_cache) / len(times_with_cache)

        print("\nAverage over 10 runs:")
        print(f"  No cache:    {avg_no_cache * 1000:.2f}ms")
        print(f"  With cache:  {avg_with_cache * 1000:.2f}ms")
        print(f"  Speedup:     {avg_no_cache / avg_with_cache:.2f}x")

        metrics = cache.get_metrics()
        print(f"\nCache hit rate: {metrics['hit_rate'] * 100:.1f}%")

        # Honest assessment
        print("\n=== Honest Assessment ===")
        savings_per_rebuild = (avg_no_cache - avg_with_cache) * 1000
        print(f"Time saved per rebuild: {savings_per_rebuild:.2f}ms")

        if savings_per_rebuild < 1.0:
            print("⚠️  WARNING: Savings < 1ms - cache overhead may not be worth it")
        elif savings_per_rebuild < 5.0:
            print("⚠️  Modest savings - cache is helpful but not transformative")
        else:
            print("✅ Significant savings - cache is valuable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
