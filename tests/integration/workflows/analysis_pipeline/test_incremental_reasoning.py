"""
End-to-End Incremental Reasoning Tests

ReasoningPipeline + IncrementalBuilder 통합
"""

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    Span,
)
from src.contexts.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline


@pytest.fixture
def sample_graph():
    """Sample graph for testing"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    # Create 3 functions
    for i in range(1, 4):
        graph.graph_nodes[f"f{i}"] = GraphNode(
            id=f"f{i}",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="s1",
            fqn=f"test.f{i}",
            name=f"func{i}",
            path="test.py",
            span=Span(start_line=i * 10, start_col=0, end_line=i * 10 + 5, end_col=0),
            attrs={},
        )

    # f1 → f2 → f3
    graph.graph_edges.append(GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="f1", target_id="f2", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f3", attrs={}))

    return graph


class TestIncrementalReasoning:
    """End-to-end incremental reasoning 테스트"""

    def test_pipeline_initialization(self, sample_graph):
        """파이프라인 초기화"""
        pipeline = ReasoningPipeline(sample_graph)

        assert pipeline.ctx.graph == sample_graph
        assert pipeline.effect_differ is not None
        assert pipeline.impact_analyzer is not None
        assert pipeline.incremental_builder is None  # Not initialized yet

    def test_incremental_rebuild_basic(self, sample_graph):
        """기본 incremental rebuild"""
        pipeline = ReasoningPipeline(sample_graph)

        # Simulate code changes
        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}

        # Rebuild incrementally
        updated_graph = pipeline.rebuild_graph_incrementally(changes)

        # Should return a graph
        assert updated_graph is not None
        assert len(updated_graph.graph_nodes) >= 3

        # Metadata should be populated
        assert "rebuild_plan" in pipeline.ctx.metadata
        assert "rebuild_stats" in pipeline.ctx.metadata

    def test_incremental_rebuild_with_impact(self, sample_graph):
        """영향 분석 포함 rebuild"""
        pipeline = ReasoningPipeline(sample_graph)

        # Breaking change
        changes = {"f2": ("def f2(): return 2", "def f2():\n    global X\n    X += 1\n    return 2")}

        updated_graph = pipeline.rebuild_graph_incrementally(changes)

        # Check metadata
        plan_meta = pipeline.ctx.metadata["rebuild_plan"]
        assert plan_meta["strategy"] in ["minimal", "partial", "full"]
        assert len(plan_meta["changed_files"]) >= 1

        # Check stats
        stats = pipeline.ctx.metadata["rebuild_stats"]
        assert stats["changed_symbols"] == 1
        assert "impacted_symbols" in stats

    def test_rebuild_plan_strategy(self, sample_graph):
        """Rebuild strategy 검증"""
        pipeline = ReasoningPipeline(sample_graph)

        # Minimal change
        changes = {"f3": ("def f3(): pass", "def f3(): return 3")}

        pipeline.rebuild_graph_incrementally(changes)
        plan_meta = pipeline.ctx.metadata["rebuild_plan"]

        # Should be minimal or partial
        assert plan_meta["strategy"] in ["minimal", "partial"]
        assert plan_meta["estimated_cost"] < 10

    def test_immutability_in_pipeline(self, sample_graph):
        """파이프라인에서 immutability 보장"""
        pipeline = ReasoningPipeline(sample_graph)

        original_node_count = len(sample_graph.graph_nodes)
        original_edge_count = len(sample_graph.graph_edges)

        changes = {"f1": ("def f1(): return 1", "def f1(): return 2")}
        updated_graph = pipeline.rebuild_graph_incrementally(changes)

        # Original graph should NOT be modified
        assert len(sample_graph.graph_nodes) == original_node_count
        assert len(sample_graph.graph_edges) == original_edge_count

        # Updated graph should be different object
        assert updated_graph is not sample_graph

    def test_integration_with_effect_analysis(self, sample_graph):
        """Effect analysis + Incremental rebuild 통합"""
        pipeline = ReasoningPipeline(sample_graph)

        changes = {"f1": ("def f1(): x = 1", "def f1(): x = 2")}

        # Step 1: Analyze effects
        pipeline.analyze_effects(changes)

        # Step 2: Incremental rebuild
        updated_graph = pipeline.rebuild_graph_incrementally(changes)

        # Both should work together
        assert len(pipeline.ctx.effect_diffs) >= 1
        assert updated_graph is not None

    def test_slicer_integration(self, sample_graph):
        """ProgramSlicer 통합 확인"""
        pipeline = ReasoningPipeline(sample_graph)

        changes = {"f1": ("x = 1", "x = 2")}

        pipeline.rebuild_graph_incrementally(changes)

        # Slicer metrics should be available
        stats = pipeline.ctx.metadata.get("rebuild_stats", {})

        # May or may not have slicer metrics depending on PDG availability
        # Just check it doesn't crash
        assert "changed_symbols" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
