"""
ReasoningPipeline Cost Integration Unit Tests (RFC-028 Point 2)

Unit-level 검증 (의존성 최소화)
"""

import pytest


class TestCostAnalyzerMethod:
    """analyze_cost() 메서드 존재 확인"""

    def test_method_exists(self):
        """ReasoningPipeline에 analyze_cost() 메서드 있어야 함"""
        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        assert hasattr(ReasoningPipeline, "analyze_cost")

    def test_signature_requires_ir_doc(self):
        """
        analyze_cost() 시그니처 검증

        핵심 발견:
        - GraphDocument에는 IR 정보 없음
        - IRDocument는 indexing 단계에서만 존재
        - analyze_cost(ir_doc, functions) 시그니처 필요
        """
        import inspect

        from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningPipeline

        sig = inspect.signature(ReasoningPipeline.analyze_cost)
        params = list(sig.parameters.keys())

        # Should have ir_doc parameter
        assert "ir_doc" in params
        assert "functions" in params


class TestPoint2TODO:
    """Point 2 TODO 문서화"""

    def test_graph_to_ir_conversion_needed(self):
        """
        Point 2 완료를 위해 필요한 것:

        1. Graph → IRDocument 변환 로직
           - GraphDocument에 IR 정보가 있는가?
           - IRDocument를 별도 저장소에서 로드?
           - Graph에서 IR 재구성?

        2. ReasoningPipeline.analyze_cost() 구현
           - IR 가져오기
           - CostAnalyzer 호출
           - 결과 저장

        현재 상태: analyze_cost() 메서드 추가됨 (NotImplementedError)
        다음 단계: Graph → IR 변환 로직 구현
        """
        # This is a documentation test
        # Point 2 is PARTIALLY complete:
        # - Method added ✅
        # - NotImplementedError (correct!) ✅
        # - Full implementation: TODO (needs Graph → IR)
        pass
