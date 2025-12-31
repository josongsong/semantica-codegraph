"""
Unit Tests: Subchat 3중 종료 + Wrap-up

P0-1 Task: 에이전트 루프 안정성 강화
- 3중 종료 조건 (실패/반복/토큰)
- Wrap-up 요약 생성
"""

import pytest

from apps.orchestrator.orchestrator.workflow.models import (
    StepResult,
    WorkflowExitReason,
    WorkflowState,
    WorkflowStep,
)
from apps.orchestrator.orchestrator.workflow.state_machine import WorkflowStateMachine


class TestSubchatTripleExit:
    """Subchat 3중 종료 테스트"""

    def test_exit_by_max_iterations(self):
        """종료 조건 2: 반복 한계"""
        # Given: max_iterations=2, Phase 1 (early exit 비활성화)
        machine = WorkflowStateMachine(max_iterations=2, enable_full_workflow=True)

        # Mock: 테스트를 항상 실패하게 해서 early exit 방지
        def mock_test_fail(state):
            return StepResult(
                step=WorkflowStep.TEST,
                success=True,
                output={"passed": False, "total": 10, "failed": 10},
            )

        machine._test = mock_test_fail

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When: 실행
        result = machine.run(state)

        # Then: MAX_ITERATIONS로 종료
        assert result.exit_reason == WorkflowExitReason.MAX_ITERATIONS
        assert result.iteration == 2
        assert result.summary is not None
        assert "반복 횟수: 2/2" in result.summary

    def test_exit_by_token_limit(self):
        """종료 조건 3: 토큰 한계 (NEW)"""
        # Given: max_tokens=100, 각 step이 50 토큰 사용
        machine = WorkflowStateMachine(max_iterations=10, max_tokens=100)

        # Mock: 각 step이 50 토큰 사용하도록 설정
        original_analyze = machine._analyze

        def mock_analyze_with_tokens(state):
            result = original_analyze(state)
            result.tokens_used = 50
            return result

        machine._analyze = mock_analyze_with_tokens

        original_generate = machine._generate

        def mock_generate_with_tokens(state):
            result = original_generate(state)
            result.tokens_used = 50
            return result

        machine._generate = mock_generate_with_tokens

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When: 실행
        result = machine.run(state)

        # Then: TOKEN_LIMIT로 종료 (50+50=100)
        assert result.exit_reason == WorkflowExitReason.TOKEN_LIMIT
        assert result.summary is not None
        assert "토큰 사용:" in result.summary
        assert "100/100" in result.summary

    def test_exit_by_success(self):
        """종료 조건 4: 작업 완료"""
        # Given: Phase 0 (1회 실행 후 자동 종료)
        machine = WorkflowStateMachine(max_iterations=10, enable_full_workflow=False)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When: 실행
        result = machine.run(state)

        # Then: SUCCESS로 종료
        assert result.exit_reason == WorkflowExitReason.SUCCESS
        assert result.iteration == 1
        assert result.summary is not None

    def test_exit_by_error(self):
        """종료 조건 1: 실패"""
        # Given: 에러 발생하도록 설정
        machine = WorkflowStateMachine()

        # Mock: _analyze가 실패하도록
        def mock_analyze_fail(state):
            return StepResult(
                step=WorkflowStep.ANALYZE,
                success=False,
                output=None,
                error="Analysis failed",
            )

        machine._analyze = mock_analyze_fail

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When: 실행
        result = machine.run(state)

        # Then: ERROR로 종료
        assert result.exit_reason == WorkflowExitReason.ERROR
        assert result.error == "Analysis failed"
        assert result.current_step == WorkflowStep.FAILED


class TestWrapUpSummary:
    """Wrap-up 요약 테스트"""

    def test_wrap_up_includes_exit_reason(self):
        """요약에 종료 사유 포함"""
        # Given
        machine = WorkflowStateMachine(max_iterations=1)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then
        assert result.summary is not None
        assert "종료 사유:" in result.summary
        assert "max_iterations" in result.summary or "success" in result.summary

    def test_wrap_up_includes_iterations(self):
        """요약에 반복 횟수 포함"""
        # Given
        machine = WorkflowStateMachine(max_iterations=2)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then
        assert result.summary is not None
        assert "반복 횟수:" in result.summary

    def test_wrap_up_includes_tokens(self):
        """요약에 토큰 사용량 포함"""
        # Given
        machine = WorkflowStateMachine(max_iterations=1, max_tokens=8000)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then
        assert result.summary is not None
        assert "토큰 사용:" in result.summary
        assert "8000" in result.summary

    def test_wrap_up_custom_prompt(self):
        """커스텀 Wrap-up 프롬프트"""
        # Given
        custom_prompt = "작업 완료! 요약해주세요."
        machine = WorkflowStateMachine(max_iterations=1, wrap_up_prompt=custom_prompt)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: 프롬프트와 무관하게 요약 생성됨 (Phase 0는 간단 요약)
        assert result.summary is not None
        assert machine.wrap_up_prompt == custom_prompt

    def test_wrap_up_includes_executed_steps(self):
        """요약에 실행된 단계 포함"""
        # Given
        machine = WorkflowStateMachine(max_iterations=1)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then
        assert result.summary is not None
        assert "실행 단계:" in result.summary
        assert "analyze" in result.summary or "generate" in result.summary


class TestBackwardCompatibility:
    """Backward Compatibility 테스트"""

    def test_default_max_tokens(self):
        """기본 max_tokens 값"""
        # Given
        machine = WorkflowStateMachine()

        # Then
        assert machine.max_tokens == 8000

    def test_default_wrap_up_prompt(self):
        """기본 wrap_up_prompt 값"""
        # Given
        machine = WorkflowStateMachine()

        # Then
        assert machine.wrap_up_prompt is not None
        assert "요약" in machine.wrap_up_prompt

    def test_existing_functionality_preserved(self):
        """기존 기능 유지"""
        # Given: 기존 방식대로 사용
        machine = WorkflowStateMachine(max_iterations=1, enable_full_workflow=False)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: 정상 동작
        assert result.current_step == WorkflowStep.COMPLETED
        assert result.iteration == 1
        assert result.exit_reason in [WorkflowExitReason.SUCCESS, WorkflowExitReason.MAX_ITERATIONS]


class TestEdgeCases:
    """Edge Cases 테스트"""

    def test_zero_tokens_step(self):
        """토큰 사용 0인 step"""
        # Given
        machine = WorkflowStateMachine(max_tokens=100)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: 토큰 0이어도 정상 실행
        assert result.exit_reason is not None
        assert result.summary is not None
        assert "0/100" in result.summary  # ✅ 토큰 0 확인

    def test_exact_token_limit(self):
        """토큰 한계 정확히 도달"""
        # Given
        machine = WorkflowStateMachine(max_iterations=10, max_tokens=100)

        # Mock: 첫 번째 step에서 정확히 100 토큰 사용
        original_analyze = machine._analyze

        def mock_analyze_100(state):
            result = original_analyze(state)
            result.tokens_used = 100
            return result

        machine._analyze = mock_analyze_100

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: TOKEN_LIMIT로 종료 (즉시)
        assert result.exit_reason == WorkflowExitReason.TOKEN_LIMIT
        assert result.iteration == 0  # ✅ 즉시 종료

    def test_no_wrap_up_prompt(self):
        """wrap_up_prompt=None"""
        # Given
        machine = WorkflowStateMachine(max_iterations=1, wrap_up_prompt=None)
        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: 기본 프롬프트 사용
        assert result.summary is not None
        assert machine.wrap_up_prompt is not None

    def test_negative_tokens_validation(self):
        """tokens_used 음수 검증 ✅ NEW"""
        # Given/When/Then: 음수 토큰은 ValueError 발생
        with pytest.raises(ValueError, match="tokens_used must be >= 0"):
            StepResult(
                step=WorkflowStep.ANALYZE,
                success=True,
                output={},
                tokens_used=-100,
            )

    def test_wrap_up_exception_handling(self):
        """Wrap-up 실패 시 fallback 요약 ✅ NEW"""
        # Given: max_iterations 충분히 크게
        machine = WorkflowStateMachine(max_iterations=10)

        # Mock: Wrap-up에서 exception
        def mock_wrap_up_fail(state, total_tokens):
            raise Exception("Wrap-up failed!")

        machine._request_wrap_up = mock_wrap_up_fail

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: Workflow는 성공 (Phase 0 early exit), Fallback 요약 생성
        assert result.exit_reason == WorkflowExitReason.SUCCESS
        assert result.summary is not None
        assert "Wrap-up 실패" in result.summary

    def test_token_limit_immediate_exit(self):
        """토큰 한계 도달 시 즉시 종료 ✅ NEW"""
        # Given: max_tokens=100, Step 2에서 초과
        machine = WorkflowStateMachine(max_iterations=10, max_tokens=100)

        original_analyze = machine._analyze
        original_generate = machine._generate

        # Mock: analyze=50, generate=60 (총 110 > 100)
        def mock_analyze_50(state):
            result = original_analyze(state)
            result.tokens_used = 50
            return result

        def mock_generate_60(state):
            result = original_generate(state)
            result.tokens_used = 60
            return result

        machine._analyze = mock_analyze_50
        machine._generate = mock_generate_60

        state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={},
        )

        # When
        result = machine.run(state)

        # Then: generate 직후 즉시 종료 (iteration 완료 전)
        assert result.exit_reason == WorkflowExitReason.TOKEN_LIMIT
        assert result.iteration == 0  # ✅ Iteration 완료 안 됨
        assert len(result.step_history) == 2  # analyze + generate만
