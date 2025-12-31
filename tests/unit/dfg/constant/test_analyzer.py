"""
Constant Propagation Analyzer Tests

RFC-024 Part 1: SCCP Baseline - Analyzer Unit Tests

Coverage:
- Analyzer 생성
- 캐시 동작
- DFG 자동 빌드
- CFG 검증
- Port 인터페이스 준수

Note:
    실제 IR 통합 테스트는 Day 15-17에 작성
    여기서는 기본 동작만 테스트
"""

import pytest

from codegraph_engine.code_foundation.domain.constant_propagation.ports import IConstantPropagator
from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer


class TestAnalyzerCreation:
    """Analyzer 생성 테스트"""

    def test_analyzer_creation(self):
        """Analyzer 생성"""
        analyzer = ConstantPropagationAnalyzer()

        assert analyzer is not None
        assert analyzer._lattice is not None
        assert analyzer._solver is not None
        assert analyzer._cache == {}

    def test_implements_port(self):
        """IConstantPropagator Port 구현 확인"""
        analyzer = ConstantPropagationAnalyzer()

        # Protocol 체크 (duck typing)
        assert hasattr(analyzer, "analyze")
        assert hasattr(analyzer, "analyze_function")
        assert callable(analyzer.analyze)
        assert callable(analyzer.analyze_function)

        # Port 인터페이스 준수 (runtime_checkable)
        assert isinstance(analyzer, IConstantPropagator)


class TestCacheManagement:
    """캐시 관리 테스트"""

    def test_clear_cache(self):
        """캐시 초기화"""
        analyzer = ConstantPropagationAnalyzer()

        # 캐시에 임의 데이터 추가
        analyzer._cache["test"] = None  # type: ignore

        analyzer.clear_cache()

        assert analyzer._cache == {}


class TestEdgeCases:
    """엣지 케이스"""

    def test_missing_dfg_raises_error(self):
        """DFG 없으면 ValueError (먼저 체크됨!)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

        analyzer = ConstantPropagationAnalyzer()

        # DFG 없는 IRDocument
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1", dfg_snapshot=None)

        with pytest.raises(ValueError, match="DFG snapshot not found"):
            analyzer.analyze(ir_doc)

    def test_missing_cfg_raises_error(self):
        """CFG 없으면 ValueError"""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

        analyzer = ConstantPropagationAnalyzer()

        # DFG는 있지만 CFG 없는 IRDocument
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),  # DFG 있음
            cfg_blocks=[],  # CFG 없음!
        )

        with pytest.raises(ValueError, match="CFG blocks not found"):
            analyzer.analyze(ir_doc)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
