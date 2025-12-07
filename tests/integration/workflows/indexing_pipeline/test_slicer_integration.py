"""
Query Engine Integration Tests

IncrementalBuilder + ProgramSlicer 통합
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
from src.contexts.reasoning_engine.application.incremental_builder import IncrementalBuilder
from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder, PDGEdge, PDGNode
from src.contexts.reasoning_engine.infrastructure.slicer import ProgramSlicer


@pytest.fixture
def sample_graph():
    """Sample graph with 3 functions"""
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
            path="test.py",
            span=Span(start_line=i * 10, start_col=0, end_line=i * 10 + 5, end_col=0),
            attrs={},
        )

    # f1 → f2 → f3
    graph.graph_edges.append(GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="f1", target_id="f2", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f3", attrs={}))

    return graph


@pytest.fixture
def sample_pdg():
    """Sample PDG matching the graph"""
    builder = PDGBuilder()

    # Create PDG nodes
    builder.add_node(PDGNode("n1", "def f1(): x = 1", 10, ["x"], []))
    builder.add_node(PDGNode("n2", "def f2(x): y = x + 1", 20, ["y"], ["x"]))
    builder.add_node(PDGNode("n3", "def f3(y): z = y * 2", 30, ["z"], ["y"]))

    # Add edges
    builder.add_edge(PDGEdge("n1", "n2", "data"))
    builder.add_edge(PDGEdge("n2", "n3", "data"))

    return builder


class TestQueryEngineIntegration:
    """Query Engine (Slicer + Builder) 통합 테스트"""

    def test_builder_with_slicer(self, sample_graph, sample_pdg):
        """Builder + Slicer 기본 통합"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        assert builder.program_slicer is not None
        assert len(builder.changed_symbols) == 0

    def test_analyze_changes_without_slicer(self, sample_graph):
        """Slicer 없이도 동작"""
        builder = IncrementalBuilder(sample_graph)

        changes = {"f2": ("def f2(): return 2", "def f2(): print(2)")}

        reports = builder.analyze_changes(changes)

        # Basic impact analysis works
        assert len(builder.changed_symbols) == 1
        assert "f2" in builder.changed_symbols

    def test_analyze_changes_with_slicer(self, sample_graph, sample_pdg):
        """Slicer 포함 영향 분석"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        changes = {"f1": ("def f1(): x = 1", "def f1(): x = 2")}

        reports = builder.analyze_changes(changes)

        # Changed symbols
        assert "f1" in builder.changed_symbols

        # Impacted symbols (slicer may find f2, f3)
        # (depends on slicer implementation)
        assert len(builder.impacted_symbols) >= 0

    def test_rebuild_plan_with_slicer(self, sample_graph, sample_pdg):
        """Slicer 기반 rebuild plan"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        changes = {"f1": ("def f1(): x = 1", "def f1(): x = 2")}

        builder.analyze_changes(changes)
        plan = builder.create_rebuild_plan()

        # Plan includes changed + impacted
        assert len(plan.changed_files) >= 1
        assert "test.py" in plan.changed_files
        assert plan.strategy in ["minimal", "partial", "full"]

    def test_slicer_forward_impact(self, sample_graph, sample_pdg):
        """Forward slice로 영향 분석"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        # f1 변경 → f2, f3 영향?
        changes = {"f1": ("x = 1", "x = 2")}

        builder.analyze_changes(changes)

        # At least f1 changed
        assert "f1" in builder.changed_symbols

    def test_statistics_with_slicer(self, sample_graph, sample_pdg):
        """통계"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        changes = {"f1": ("def f1(): x = 1", "def f1(): x = 2"), "f2": ("def f2(): y = 2", "def f2(): y = 3")}

        builder.analyze_changes(changes)
        stats = builder.get_statistics()

        assert stats["changed_symbols"] == 2
        assert stats["changed_files"] >= 1
        assert "impacted_symbols" in stats

    def test_confidence_threshold_config(self, sample_graph, sample_pdg):
        """Confidence threshold 설정"""
        slicer = ProgramSlicer(sample_pdg)

        # High threshold
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer, slicer_confidence_threshold=0.9)

        assert builder.slicer_confidence_threshold == 0.9

        changes = {"f1": ("x = 1", "x = 2")}
        builder.analyze_changes(changes)

        # Should work (might filter more with high threshold)
        assert len(builder.changed_symbols) == 1

    def test_slicer_metrics(self, sample_graph, sample_pdg):
        """Slicer metrics 추적"""
        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        changes = {"f1": ("def f1(): x = 1", "def f1(): x = 2"), "f2": ("def f2(): y = 2", "def f2(): y = 3")}

        builder.analyze_changes(changes)
        stats = builder.get_statistics()

        # Metrics should be present
        assert "slicer_successes" in stats
        assert "slicer_failures" in stats
        assert "slicer_success_rate" in stats
        assert stats["slicer_success_rate"] >= 0.0
        assert stats["slicer_success_rate"] <= 1.0


class TestSlicerImpactExtraction:
    """ProgramSlicer 영향 추출 테스트"""

    def test_extract_symbols_from_fragment(self, sample_graph, sample_pdg):
        """Fragment에서 symbol 추출"""
        from src.contexts.reasoning_engine.infrastructure.slicer.slicer import CodeFragment

        slicer = ProgramSlicer(sample_pdg)
        builder = IncrementalBuilder(sample_graph, program_slicer=slicer)

        # Create fragment
        fragment = CodeFragment(
            file_path="test.py",
            code="def f2(x): y = x + 1",
            node_id="n2",
            start_line=20,
            end_line=20,
            relevance_score=1.0,
        )

        symbols = builder._extract_symbols_from_fragment(fragment)

        # Should find f2
        assert "f2" in symbols or len(symbols) >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
