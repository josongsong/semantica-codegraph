"""
Architecture Principle 검증 (CRITICAL)

원칙:
- IRDocument = Source of Truth
- GraphDocument = Derived Index/View
- 변환: IR → Graph (단방향!)
- 금지: Graph → IR
"""

import pytest


class TestArchitecturePrinciple:
    """Architecture 원칙 검증"""

    def test_ir_to_graph_only(self):
        """
        변환 방향: IR → Graph (단방향)

        GraphBuilder.build_full(ir_doc) ✅
        (역변환 없음) ✅
        """
        from codegraph_engine.code_foundation.infrastructure.graph.builder import GraphBuilder

        # GraphBuilder.build_full exists
        assert hasattr(GraphBuilder, "build_full")

        # No reverse method
        assert not hasattr(GraphBuilder, "from_graph")
        assert not hasattr(GraphBuilder, "to_ir")

    def test_cost_analyzer_requires_ir_doc(self):
        """
        CostAnalyzer는 IRDocument 필요 (not Graph)

        이유:
        - CFG blocks (IRDocument에만 있음)
        - Expression IR (IRDocument에만 있음)
        - GraphDocument에는 이 정보 없음
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

        analyzer = CostAnalyzer()

        # Signature check
        import inspect

        sig = inspect.signature(analyzer.analyze_function)
        params = list(sig.parameters.keys())

        # First parameter should be ir_doc (not graph)
        assert "ir_doc" in params

    def test_reasoning_pipeline_signature(self):
        """
        ReasoningPipeline.analyze_cost()는 ir_doc를 명시적으로 받음

        이유:
        - Graph에 IR 정보 없음
        - Graph → IR 재구성 금지
        - Caller가 IRDocument 제공
        """
        import inspect

        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        sig = inspect.signature(ReasoningPipeline.analyze_cost)
        params = list(sig.parameters.keys())

        # Should have ir_doc parameter
        assert "ir_doc" in params, "analyze_cost() must accept ir_doc explicitly"


class TestPointDecoupling:
    """Point 1 (IRStage) ↔ Point 2 (ReasoningPipeline) 분리"""

    def test_irstage_has_ir_doc(self):
        """
        Point 1 (IRStage): IRDocument 있음

        SemanticIRStage는 IRDocument 직접 접근 가능
        ctx.ir_doc 사용
        """
        import inspect

        from codegraph_engine.analysis_indexing.infrastructure.stages.ir_stage import SemanticIRStage

        # _run_cost_analysis should use ctx.ir_doc
        source = inspect.getsource(SemanticIRStage._run_cost_analysis)
        assert "ctx.ir_doc" in source

    def test_reasoning_pipeline_needs_ir_doc(self):
        """
        Point 2 (ReasoningPipeline): IRDocument 없음

        GraphDocument만 있음 → IRDocument 별도로 받아야 함
        """
        import inspect

        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        # Signature check (no instantiation needed)
        sig = inspect.signature(ReasoningPipeline.analyze_cost)
        params = list(sig.parameters.keys())

        # analyze_cost()는 ir_doc 파라미터로 받음
        assert "ir_doc" in params, "analyze_cost() must accept ir_doc parameter"

        # ir_doc가 첫 번째 파라미터 (self 다음)
        assert params[1] == "ir_doc", "ir_doc should be first parameter after self"
