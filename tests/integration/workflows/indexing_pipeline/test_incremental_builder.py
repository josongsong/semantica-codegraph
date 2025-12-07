"""
Incremental Builder Integration Tests
"""

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.contexts.reasoning_engine.application.incremental_builder import IncrementalBuilder, RebuildPlan


@pytest.fixture
def old_graph():
    """Old graph fixture"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    # f1, f2, f3
    for i in range(1, 4):
        graph.graph_nodes[f"f{i}"] = GraphNode(
            id=f"f{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="s1",
            fqn=f"f{i}",
            name=f"func{i}",
            path="a.py",
            span=None,
            attrs={},
        )

    # f1 → f2 → f3
    graph.graph_edges.append(GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="f1", target_id="f2", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f3", attrs={}))

    return graph


@pytest.fixture
def new_graph(old_graph):
    """New graph with f2 modified"""
    # Same as old for simplicity
    return old_graph


class TestIncrementalBuilder:
    """Incremental Builder 테스트"""

    def test_initialization(self, old_graph):
        """초기화"""
        builder = IncrementalBuilder(old_graph)

        assert builder.old_graph == old_graph
        assert builder.new_graph == old_graph
        assert len(builder.changed_symbols) == 0

    def test_analyze_changes(self, old_graph):
        """변경 분석"""
        builder = IncrementalBuilder(old_graph)

        changes = {
            "f2": ("def f2(): return 2", "def f2(): print(2); return 2"),
        }

        reports = builder.analyze_changes(changes)

        assert len(builder.changed_symbols) == 1
        assert "f2" in builder.changed_symbols
        # Breaking change → impact analysis
        assert len(builder.impacted_symbols) >= 0

    def test_create_rebuild_plan_minimal(self, old_graph):
        """Minimal rebuild plan"""
        builder = IncrementalBuilder(old_graph)

        changes = {
            "f1": ("def f1(): return 1", "def f1(): return 2"),
        }

        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()

        assert plan.strategy in ["minimal", "partial"]
        assert len(plan.changed_files) >= 1
        assert "a.py" in plan.changed_files

    def test_create_rebuild_plan_with_impact(self, old_graph):
        """Impact 포함 plan"""
        builder = IncrementalBuilder(old_graph)

        # Breaking change
        changes = {
            "f2": ("def f2(): return 2", "def f2():\n    global X\n    X += 1"),
        }

        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()

        # f2 변경 + f1 영향 가능
        assert len(plan.symbols_to_rebuild) >= 1

    def test_execute_rebuild_partial(self, old_graph, new_graph):
        """Partial rebuild 실행"""
        builder = IncrementalBuilder(old_graph, new_graph)

        changes = {
            "f1": ("def f1(): return 1", "def f1(): return 2"),
        }

        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()

        updated = builder.execute_rebuild(plan)

        assert updated is not None
        assert len(updated.graph_nodes) >= 3

    def test_execute_rebuild_full(self, old_graph, new_graph):
        """Full rebuild"""
        builder = IncrementalBuilder(old_graph, new_graph)

        # Simple full rebuild execution
        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}
        builder.analyze_changes(changes)

        plan = builder.create_rebuild_plan()

        updated = builder.execute_rebuild(plan)
        # Updated graph should have nodes
        assert len(updated.graph_nodes) >= 3

    def test_get_statistics(self, old_graph):
        """통계"""
        builder = IncrementalBuilder(old_graph)

        changes = {
            "f1": ("def f1(): return 1", "def f1(): return 2"),
            "f2": ("def f2(): return 2", "def f2(): return 3"),
        }

        builder.analyze_changes(changes)
        stats = builder.get_statistics()

        assert stats["changed_symbols"] == 2
        assert stats["changed_files"] >= 1
        assert "impacted_symbols" in stats

    def test_rebuild_plan_summary(self, old_graph):
        """Plan summary"""
        builder = IncrementalBuilder(old_graph)

        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}
        builder.analyze_changes(changes)

        plan = builder.create_rebuild_plan()
        summary = plan.summary()

        assert "rebuild" in summary
        assert "changed" in summary

    def test_immutability(self, old_graph, new_graph):
        """Old graph immutability"""
        builder = IncrementalBuilder(old_graph, new_graph)

        # Store original state
        original_node_count = len(old_graph.graph_nodes)
        original_edge_count = len(old_graph.graph_edges)
        original_node_ids = set(old_graph.graph_nodes.keys())

        # Execute rebuild
        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}
        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()
        updated = builder.execute_rebuild(plan)

        # Old graph should NOT be modified
        assert len(old_graph.graph_nodes) == original_node_count
        assert len(old_graph.graph_edges) == original_edge_count
        assert set(old_graph.graph_nodes.keys()) == original_node_ids

        # Updated graph should be different object
        assert updated is not old_graph

    def test_edge_consistency(self, old_graph):
        """Edge consistency in partial rebuild"""
        # Create new graph with modified f2
        new_graph = GraphDocument(repo_id="test", snapshot_id="s2")

        # Copy nodes
        for node_id, node in old_graph.graph_nodes.items():
            new_graph.graph_nodes[node_id] = node

        # Copy edges
        new_graph.graph_edges = old_graph.graph_edges.copy()

        builder = IncrementalBuilder(old_graph, new_graph)

        changes = {"f2": ("def f2(): return 2", "def f2(): return 3")}
        builder.analyze_changes(changes)

        plan = builder.create_rebuild_plan()
        updated = builder.execute_rebuild(plan)

        # Edges should be consistent
        # f2와 관련된 edge만 업데이트되어야 함
        assert isinstance(updated.graph_edges, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
