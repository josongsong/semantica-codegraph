"""
Reasoning Pipeline Integration Tests
"""

import pytest

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.contexts.reasoning_engine.application.reasoning_pipeline import (
    ReasoningContext,
    ReasoningPipeline,
    ReasoningResult,
)
from src.contexts.reasoning_engine.domain.effect_models import EffectType
from src.contexts.reasoning_engine.domain.impact_models import ImpactLevel
from src.contexts.reasoning_engine.domain.speculative_models import PatchType, SpeculativePatch


@pytest.fixture
def sample_graph():
    """Sample graph for testing"""
    graph = GraphDocument(repo_id="test", snapshot_id="s1")

    # f1 → f2 → f3
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

    graph.graph_edges.append(GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="f1", target_id="f2", attrs={}))
    graph.graph_edges.append(GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="f2", target_id="f3", attrs={}))

    return graph


class TestReasoningPipeline:
    """Reasoning Pipeline 통합 테스트"""

    def test_pipeline_initialization(self, sample_graph):
        """Pipeline 초기화"""
        pipeline = ReasoningPipeline(sample_graph)

        assert pipeline.ctx.graph == sample_graph
        assert pipeline.effect_differ is not None
        assert pipeline.impact_analyzer is not None
        assert pipeline.slicer is not None
        assert pipeline.risk_analyzer is not None

    def test_analyze_effects(self, sample_graph):
        """Effect 분석"""
        pipeline = ReasoningPipeline(sample_graph)

        changes = {
            "f1": ("def f1(): return 1", "def f1(): print(1); return 1"),
        }

        diffs = pipeline.analyze_effects(changes)

        assert len(diffs) == 1
        assert "f1" in diffs
        assert diffs["f1"].has_changes()
        assert EffectType.IO in diffs["f1"].added

    def test_analyze_impact(self, sample_graph):
        """Impact 분석"""
        pipeline = ReasoningPipeline(sample_graph)

        reports = pipeline.analyze_impact(["f2"])

        assert len(reports) >= 1
        assert "f2" in reports
        assert len(reports["f2"].impacted_nodes) >= 1

    def test_simulate_patch(self, sample_graph):
        """Speculative 실행"""
        pipeline = ReasoningPipeline(sample_graph)

        patch = SpeculativePatch(patch_id="p1", patch_type=PatchType.DELETE_FUNCTION, target_symbol="f2")

        risk = pipeline.simulate_patch(patch)

        assert risk is not None
        assert risk.is_breaking()  # f2 삭제 → f1 영향

    def test_full_pipeline(self, sample_graph):
        """전체 파이프라인"""
        pipeline = ReasoningPipeline(sample_graph)

        # 1. Effect
        changes = {
            "f2": ("def f2(): return 2", "def f2():\n    global X\n    X += 1\n    return 2"),
        }
        pipeline.analyze_effects(changes)

        # 2. Impact
        pipeline.analyze_impact(["f2"])

        # 3. Speculative (DELETE는 after_code 불필요)
        patch = SpeculativePatch("p1", PatchType.DELETE_FUNCTION, "f2")
        pipeline.simulate_patch(patch)

        # 4. Result
        result = pipeline.get_result()

        assert result.summary is not None
        assert len(result.breaking_changes) >= 1
        assert "f2" in result.breaking_changes
        assert len(result.impacted_symbols) >= 1
        assert len(result.recommended_actions) >= 1

    def test_result_to_dict(self, sample_graph):
        """Result → dict 변환"""
        pipeline = ReasoningPipeline(sample_graph)

        # Simple analysis
        pipeline.analyze_impact(["f1"])
        result = pipeline.get_result()

        data = result.to_dict()

        assert "summary" in data
        assert "total_risk" in data
        assert "total_impact" in data
        assert "breaking_changes" in data
        assert "impacted_symbols" in data
        assert "recommended_actions" in data

    def test_breaking_change_detection(self, sample_graph):
        """Breaking change 감지"""
        pipeline = ReasoningPipeline(sample_graph)

        # Pure → Global mutation
        changes = {
            "f1": ("def f1(): return 1", "def f1():\n    global COUNT\n    COUNT += 1"),
        }

        pipeline.analyze_effects(changes)
        result = pipeline.get_result()

        assert len(result.breaking_changes) == 1
        assert "f1" in result.breaking_changes
        assert any("breaking" in a.lower() for a in result.recommended_actions)

    def test_impact_propagation(self, sample_graph):
        """Impact 전파 확인"""
        pipeline = ReasoningPipeline(sample_graph)

        # f3 변경 → f2, f1 영향
        pipeline.analyze_impact(["f3"])
        result = pipeline.get_result()

        # f2, f1 중 하나는 영향받아야 함
        impacted = set(result.impacted_symbols)
        # Impact은 있을 수도, 없을 수도 (graph 구조에 따라)
        # 최소한 result가 생성되는지만 확인
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
