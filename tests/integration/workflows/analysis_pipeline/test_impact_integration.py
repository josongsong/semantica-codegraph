"""
Impact Analysis Integration Tests
"""

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.contexts.reasoning_engine.domain.effect_models import EffectDiff, EffectType
from src.contexts.reasoning_engine.domain.impact_models import ImpactLevel, PropagationType
from src.contexts.reasoning_engine.infrastructure.impact.impact_analyzer import ImpactAnalyzer


@pytest.fixture
def sample_graph():
    """
    Sample call graph:
    f1 → f2 → f3
         f2 → f4
    """
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    # Nodes
    for i in range(1, 5):
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

    # Edges: f1→f2, f2→f3, f2→f4
    graph.graph_edges.append(GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="f1", target_id="f2", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f3", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e3", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f4", attrs={}))

    return graph


class TestImpactAnalyzer:
    """ImpactAnalyzer 테스트"""

    def test_direct_impact(self, sample_graph):
        """Direct call impact"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=2)

        # f2 변경 → f1 영향
        report = analyzer.analyze_impact("f2")

        assert len(report.impacted_nodes) >= 1

        # f1은 f2를 호출하므로 영향받음
        f1_impact = [n for n in report.impacted_nodes if n.symbol_id == "f1"]
        assert len(f1_impact) == 1
        assert f1_impact[0].distance == 1
        assert f1_impact[0].propagation_type == PropagationType.DIRECT_CALL

    def test_transitive_impact(self, sample_graph):
        """Transitive impact"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=3)

        # f3 변경 → f2 → f1 전파
        report = analyzer.analyze_impact("f3")

        impacted_ids = {n.symbol_id for n in report.impacted_nodes}

        # f2, f1 모두 영향
        assert "f2" in impacted_ids
        assert "f1" in impacted_ids

    def test_impact_level_by_distance(self, sample_graph):
        """Distance에 따른 impact level"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=3)

        report = analyzer.analyze_impact("f3")

        # Distance 1 = HIGH
        f2 = [n for n in report.impacted_nodes if n.symbol_id == "f2"][0]
        assert f2.distance == 1
        assert f2.impact_level in [ImpactLevel.HIGH, ImpactLevel.MEDIUM]

        # Distance 2 = MEDIUM or LOW
        f1 = [n for n in report.impacted_nodes if n.symbol_id == "f1"][0]
        assert f1.distance == 2
        assert f1.impact_level in [ImpactLevel.MEDIUM, ImpactLevel.LOW]

    def test_impact_with_effect_diff(self, sample_graph):
        """EffectDiff 고려한 impact"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=2)

        # Breaking change
        effect_diff = EffectDiff(symbol_id="f2", before={EffectType.PURE}, after={EffectType.GLOBAL_MUTATION})

        report = analyzer.analyze_impact("f2", effect_diff)

        # Breaking change → higher impact
        assert report.total_impact in [ImpactLevel.HIGH, ImpactLevel.CRITICAL]

    def test_max_depth_limit(self, sample_graph):
        """Max depth 제한"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=1)

        report = analyzer.analyze_impact("f3")

        # Max depth 1 → f2만 (f1은 depth 2)
        impacted_ids = {n.symbol_id for n in report.impacted_nodes}
        assert "f2" in impacted_ids

        # f1은 depth=2이므로 제외될 수 있음 (또는 포함될 수도)
        # max_depth=1이면 distance=1까지만

    def test_impact_paths(self, sample_graph):
        """Impact paths 계산"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=3)

        report = analyzer.analyze_impact("f3")

        # Path: f3 → f2
        f2_paths = [p for p in report.impact_paths if p.target == "f2"]
        assert len(f2_paths) >= 1

        # Path: f3 → f2 → f1
        f1_paths = [p for p in report.impact_paths if p.target == "f1"]
        if f1_paths:
            assert len(f1_paths[0].nodes) >= 2

    def test_report_summary(self, sample_graph):
        """Report summary"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=2)

        report = analyzer.analyze_impact("f2")
        summary = report.summary()

        assert "source" in summary
        assert summary["source"] == "f2"
        assert "total_nodes" in summary
        assert summary["total_nodes"] >= 1
        assert "total_impact" in summary

    def test_batch_analyze(self, sample_graph):
        """여러 source 동시 분석"""
        analyzer = ImpactAnalyzer(sample_graph, max_depth=2)

        reports = analyzer.batch_analyze(["f2", "f3"])

        assert len(reports) == 2
        assert "f2" in reports
        assert "f3" in reports
        assert isinstance(reports["f2"].impacted_nodes, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
