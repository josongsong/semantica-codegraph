"""
SOTAPipeline Tests

RFC-024 Part 2: Framework - Pipeline Tests (DAG 핵심!)

Coverage:
- Topological Sort 정확성
- 순환 의존성 탐지
- SCCP baseline 보장
- 의존성 그래프 구축
- Error cases
"""

import pytest

from codegraph_engine.code_foundation.domain.analyzers.builder import AnalyzerBuilder
from codegraph_engine.code_foundation.domain.analyzers.context import AnalysisContext
from codegraph_engine.code_foundation.domain.analyzers.ports import AnalyzerCategory, AnalyzerTier, IAnalyzer
from codegraph_engine.code_foundation.infrastructure.analyzers.pipeline_v2 import AnalyzerPipeline
from codegraph_engine.code_foundation.infrastructure.analyzers.registry_v2 import get_registry
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


# Mock Analyzers for testing
class MockSCCPAnalyzer:
    """Mock SCCP (Tier 1)"""

    name = "sccp_baseline"
    category = AnalyzerCategory.BASELINE
    tier = AnalyzerTier.TIER_1
    dependencies = []

    def analyze(self, ir_doc, context):
        return {"constants": 10}


class MockTaintAnalyzer:
    """Mock Taint (Tier 2, SCCP 의존)"""

    name = "taint"
    category = AnalyzerCategory.TAINT
    tier = AnalyzerTier.TIER_2
    dependencies = [MockSCCPAnalyzer]

    def analyze(self, ir_doc, context):
        sccp = context.require_sccp()  # SCCP 필수!
        return {"taint_paths": 5}


class MockNullAnalyzer:
    """Mock Null (Tier 2, SCCP 의존)"""

    name = "null"
    category = AnalyzerCategory.HEAP
    tier = AnalyzerTier.TIER_2
    dependencies = [MockSCCPAnalyzer]

    def analyze(self, ir_doc, context):
        return {"null_issues": 2}


class TestPipelineBasics:
    """Pipeline 기본 기능"""

    def setup_method(self):
        """각 테스트 전 Registry 초기화"""
        registry = get_registry()
        registry.clear()

    def test_pipeline_creation(self):
        """Pipeline 생성"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        assert pipeline._ir_doc is ir_doc
        assert pipeline._analyzer_names == []
        assert isinstance(pipeline._context, AnalysisContext)

    def test_add_analyzer(self):
        """분석기 추가 (Fluent API)"""
        registry = get_registry()
        registry.register_builder("test", AnalyzerBuilder(MockSCCPAnalyzer))

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        result = pipeline.add("test")

        assert result is pipeline  # Fluent!
        assert "test" in pipeline._analyzer_names

    def test_add_unknown_analyzer_raises(self):
        """등록되지 않은 분석기 → KeyError"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        with pytest.raises(KeyError, match="not found in registry"):
            pipeline.add("unknown_analyzer")


class TestTopologicalSort:
    """Topological Sort (Kahn's Algorithm) 검증"""

    def setup_method(self):
        registry = get_registry()
        registry.clear()

    def test_simple_dag(self):
        """간단한 DAG: A → B"""
        graph = {
            "A": set(),  # 의존성 없음
            "B": {"A"},  # A에 의존
        }

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        sorted_list = pipeline._topological_sort(graph)

        assert len(sorted_list) == 2
        assert sorted_list.index("A") < sorted_list.index("B")  # A가 B보다 먼저

    def test_diamond_dag(self):
        """다이아몬드 DAG: A → B,C → D"""
        graph = {
            "A": set(),
            "B": {"A"},
            "C": {"A"},
            "D": {"B", "C"},
        }

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        sorted_list = pipeline._topological_sort(graph)

        assert len(sorted_list) == 4
        # A가 모든 것보다 먼저
        assert sorted_list[0] == "A"
        # D가 마지막
        assert sorted_list[3] == "D"
        # B, C는 A 이후, D 이전
        assert sorted_list.index("B") > sorted_list.index("A")
        assert sorted_list.index("C") > sorted_list.index("A")
        assert sorted_list.index("D") > sorted_list.index("B")
        assert sorted_list.index("D") > sorted_list.index("C")

    def test_circular_dependency_detected(self):
        """순환 의존성 탐지!"""
        graph = {
            "A": {"B"},  # A → B
            "B": {"A"},  # B → A (순환!)
        }

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        with pytest.raises(RuntimeError, match="Circular dependency"):
            pipeline._topological_sort(graph)

    def test_self_loop_detected(self):
        """자기 자신 의존 탐지"""
        graph = {
            "A": {"A"},  # 자기 자신 (순환!)
        }

        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        with pytest.raises(RuntimeError, match="Circular dependency"):
            pipeline._topological_sort(graph)


class TestSCCPBaseline:
    """SCCP baseline 보장 (RFC-024 정책!)"""

    def setup_method(self):
        registry = get_registry()
        registry.clear()

    def test_tier2_without_sccp_raises(self):
        """Tier 2 without SCCP → RuntimeError"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        sorted_names = ["taint", "null"]  # SCCP 없음!

        with pytest.raises(RuntimeError, match="SCCP baseline required"):
            pipeline._ensure_sccp_baseline(sorted_names)

    def test_tier2_with_sccp_passes(self):
        """Tier 2 with SCCP → OK"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
        pipeline = AnalyzerPipeline(ir_doc)

        sorted_names = ["sccp_baseline", "taint", "null"]

        # 에러 안 남
        pipeline._ensure_sccp_baseline(sorted_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
