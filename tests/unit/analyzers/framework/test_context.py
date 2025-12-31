"""
AnalysisContext Tests

RFC-024 Part 2: Framework - Context Tests

Coverage:
- 타입 안전 저장/조회
- SCCP baseline 필수 검증
- 증분 모드
- Changed functions
- Error cases
"""

import pytest

from codegraph_engine.code_foundation.domain.analyzers.context import AnalysisContext
from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult
from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer


class TestContextBasics:
    """Context 기본 기능"""

    def test_context_creation(self):
        """Context 생성"""
        context = AnalysisContext()

        assert context._results == {}
        assert context.incremental is False
        assert context.get_changed_functions() == set()

    def test_set_and_get_type_safe(self):
        """타입 안전 저장/조회"""
        context = AnalysisContext()

        # Mock result
        result = ConstantPropagationResult(
            ssa_values={},
            var_values={},
            reachable_blocks=set(),
            unreachable_blocks=set(),
            constants_found=0,
            bottom_count=0,
        )

        # 타입 기반 저장
        context.set(ConstantPropagationAnalyzer, result)

        # 타입 기반 조회
        retrieved = context.get(ConstantPropagationAnalyzer)

        assert retrieved is result

    def test_has(self):
        """존재 확인"""
        context = AnalysisContext()

        assert context.has(ConstantPropagationAnalyzer) is False

        context.set(ConstantPropagationAnalyzer, None)  # type: ignore

        assert context.has(ConstantPropagationAnalyzer) is True

    def test_get_missing_raises_key_error(self):
        """없는 결과 조회 → KeyError"""
        context = AnalysisContext()

        with pytest.raises(KeyError, match="Analysis result not found"):
            context.get(ConstantPropagationAnalyzer)


class TestSCCPBaseline:
    """SCCP baseline 필수 검증 (RFC-024 핵심!)"""

    def test_require_sccp_without_sccp_raises(self):
        """SCCP 없이 require_sccp() → RuntimeError"""
        context = AnalysisContext()

        with pytest.raises(RuntimeError, match="SCCP baseline not executed"):
            context.require_sccp()

    def test_require_sccp_with_sccp_returns(self):
        """SCCP 있으면 반환"""
        context = AnalysisContext()

        result = ConstantPropagationResult(
            ssa_values={},
            var_values={},
            reachable_blocks={"entry"},
            unreachable_blocks=set(),
            constants_found=5,
            bottom_count=2,
        )

        context.set(ConstantPropagationAnalyzer, result)

        sccp = context.require_sccp()

        assert sccp is result
        assert sccp.constants_found == 5


class TestIncrementalMode:
    """증분 모드"""

    def test_incremental_flag(self):
        """증분 모드 플래그"""
        context = AnalysisContext()

        assert context.incremental is False

        context.set_incremental(True)

        assert context.incremental is True

    def test_changed_functions(self):
        """변경된 함수 추적"""
        context = AnalysisContext()

        changed = {"func1", "func2", "func3"}
        context.set_changed_functions(changed)

        retrieved = context.get_changed_functions()

        assert retrieved == changed
        # 복사본 반환 (immutability)
        assert retrieved is not context._changed_functions


class TestClear:
    """Context 초기화"""

    def test_clear(self):
        """clear() 호출 시 모든 상태 초기화"""
        context = AnalysisContext()

        # 상태 설정
        context.set(ConstantPropagationAnalyzer, None)  # type: ignore
        context.set_incremental(True)
        context.set_changed_functions({"func1"})

        # 초기화
        context.clear()

        # 검증
        assert context._results == {}
        assert context.incremental is False
        assert context.get_changed_functions() == set()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
