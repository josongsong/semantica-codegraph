"""Workflow State Machine (ADR-003)

Phase 0: Analyze → Generate (간단한 2단계)
Phase 1: 전체 6단계 구현
"""

from .models import (
    StepResult,
    WorkflowExitReason,
    WorkflowState,
    WorkflowStep,
)


class WorkflowStateMachine:
    """
    ADR-003: Graph Workflow Engine

    Phase 0:
    - Analyze → Generate (2단계)
    - Early exit: max_iterations

    Phase 1:
    - 전체 6단계 구현
    - Critic → Test → Self-heal 추가
    - Dynamic replanning
    """

    def __init__(
        self,
        max_iterations: int = 3,
        enable_full_workflow: bool = False,
        max_tokens: int = 8000,  # 토큰 한계
        wrap_up_prompt: str | None = None,  # Wrap-up 프롬프트
    ):
        """
        Args:
            max_iterations: 최대 반복 횟수
            enable_full_workflow: Phase 1 전체 워크플로우 활성화
            max_tokens: 최대 토큰 수 (종료 조건)
            wrap_up_prompt: Wrap-up 요약 요청 프롬프트
        """
        self.max_iterations = max_iterations
        self.enable_full_workflow = enable_full_workflow
        self.max_tokens = max_tokens
        self.wrap_up_prompt = wrap_up_prompt or "지금까지 작업을 간결하게 요약해주세요."

        # Phase 0: Analyze → Generate만
        self.steps_phase0 = [
            WorkflowStep.ANALYZE,
            WorkflowStep.GENERATE,
        ]

        # Phase 1: 전체 단계
        self.steps_phase1 = [
            WorkflowStep.ANALYZE,
            WorkflowStep.PLAN,
            WorkflowStep.GENERATE,
            WorkflowStep.CRITIC,
            WorkflowStep.TEST,
            WorkflowStep.SELF_HEAL,
        ]

        self.steps = self.steps_phase1 if enable_full_workflow else self.steps_phase0

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        """
        Workflow 실행

        Args:
            initial_state: 초기 상태

        Returns:
            최종 상태
        """
        state = initial_state
        total_tokens = 0  # ✅ Local variable (thread-safe)

        # 최대 반복 체크
        while state.iteration < self.max_iterations:
            # 각 단계 실행
            for step in self.steps:
                state.current_step = step

                # Step 실행
                step_result = self._execute_step(state, step)
                state.add_step_result(step_result)

                # 토큰 누적
                total_tokens += step_result.tokens_used

                # 종료 조건 1: 실패
                if not step_result.success:
                    state.error = step_result.error
                    state.current_step = WorkflowStep.FAILED
                    state.exit_reason = WorkflowExitReason.ERROR
                    return state

                # 종료 조건 2: 토큰 한계 (즉시 체크) ✅ FIXED
                if total_tokens >= self.max_tokens:
                    state.exit_reason = WorkflowExitReason.TOKEN_LIMIT
                    state.current_step = WorkflowStep.COMPLETED
                    # Wrap-up with error handling
                    if self.wrap_up_prompt:
                        try:
                            state.summary = self._request_wrap_up(state, total_tokens)
                        except Exception:
                            state.summary = f"[Wrap-up 실패] 종료: token_limit, 토큰: {total_tokens}/{self.max_tokens}"
                    return state

                # 결과 state에 반영
                if step_result.output:
                    self._update_state_from_result(state, step, step_result)

            # Iteration 증가
            state.iteration += 1

            # 종료 조건 3: 반복 한계
            if state.iteration >= self.max_iterations:
                state.exit_reason = WorkflowExitReason.MAX_ITERATIONS
                break

            # 종료 조건 4: 작업 완료 (Early exit)
            if self._should_exit_early(state):
                state.exit_reason = WorkflowExitReason.SUCCESS
                break

        # 종료 사유가 설정되지 않은 경우 (정상 완료)
        if state.exit_reason is None:
            state.exit_reason = WorkflowExitReason.SUCCESS

        # Wrap-up 요약 생성 (with error handling) ✅ FIXED
        if self.wrap_up_prompt:
            try:
                state.summary = self._request_wrap_up(state, total_tokens)
            except Exception:
                # Fallback: 간단 요약
                exit_reason = state.exit_reason.value if state.exit_reason else "unknown"
                state.summary = (
                    f"[Wrap-up 실패] 종료: {exit_reason}, "
                    f"반복: {state.iteration}/{self.max_iterations}, "
                    f"토큰: {total_tokens}/{self.max_tokens}"
                )

        state.current_step = WorkflowStep.COMPLETED
        return state

    def _execute_step(self, state: WorkflowState, step: WorkflowStep) -> StepResult:
        """
        단일 Step 실행

        Args:
            state: 현재 상태
            step: 실행할 단계

        Returns:
            Step 결과
        """
        try:
            if step == WorkflowStep.ANALYZE:
                return self._analyze(state)
            elif step == WorkflowStep.PLAN:
                return self._plan(state)
            elif step == WorkflowStep.GENERATE:
                return self._generate(state)
            elif step == WorkflowStep.CRITIC:
                return self._critic(state)
            elif step == WorkflowStep.TEST:
                return self._test(state)
            elif step == WorkflowStep.SELF_HEAL:
                return self._self_heal(state)
            else:
                return StepResult(step=step, success=False, output=None, error=f"Unknown step: {step}")
        except Exception as e:
            return StepResult(step=step, success=False, output=None, error=f"Step execution failed: {e}")

    def _analyze(self, state: WorkflowState) -> StepResult:
        """
        Analyze 단계: 코드 분석

        Phase 0: 단순 Mock
        Phase 1: 실제 contexts/retrieval_search 연동
        """
        # Phase 0: 단순 구현
        analyzed_data = {
            "code_found": True,
            "relevant_files": ["src/app.py", "src/utils.py"],
            "symbols": ["calculate_total", "validate_items"],
        }

        return StepResult(
            step=WorkflowStep.ANALYZE,
            success=True,
            output=analyzed_data,
            metadata={
                "files_analyzed": 2,
                "symbols_found": 2,
            },
        )

    def _plan(self, state: WorkflowState) -> StepResult:
        """
        Plan 단계: 실행 계획 수립

        Phase 0: 생략
        Phase 1: 구현
        """
        # Phase 0: 간단한 계획
        plan = {
            "steps": [
                "1. 관련 코드 찾기",
                "2. 수정 사항 생성",
                "3. 테스트 실행",
            ],
            "estimated_complexity": "low",
        }

        return StepResult(step=WorkflowStep.PLAN, success=True, output=plan)

    def _generate(self, state: WorkflowState) -> StepResult:
        """
        Generate 단계: 코드 생성

        Phase 0: Mock 코드 생성
        Phase 1: 실제 LLM 호출
        """
        # Phase 0: Mock 코드
        generated_code = {
            "file": "src/app.py",
            "changes": """
def calculate_total(items):
    if not items:  # Added null check
        return 0
    total = 0
    for item in items:
        total += item.price
    return total
""",
            "explanation": "Added null check for items parameter",
        }

        return StepResult(
            step=WorkflowStep.GENERATE,
            success=True,
            output=generated_code,
            metadata={
                "lines_changed": 3,
                "files_modified": 1,
            },
        )

    def _critic(self, state: WorkflowState) -> StepResult:
        """
        Critic 단계: 생성된 코드 검증

        Phase 0: 생략
        Phase 1: safety/critic 연동
        """
        # Phase 0: 간단한 검증
        critique = {
            "approved": True,
            "issues": [],
            "suggestions": ["Consider adding type hints"],
        }

        return StepResult(step=WorkflowStep.CRITIC, success=True, output=critique)

    def _test(self, state: WorkflowState) -> StepResult:
        """
        Test 단계: 테스트 실행

        Phase 0: 생략
        Phase 1: execution/sandbox 연동
        """
        # Phase 0: Mock 테스트
        test_result = {
            "passed": True,
            "total": 10,
            "failed": 0,
        }

        return StepResult(step=WorkflowStep.TEST, success=True, output=test_result)

    def _self_heal(self, state: WorkflowState) -> StepResult:
        """
        Self-heal 단계: 자동 수정

        Phase 0: 생략
        Phase 1: 구현
        """
        # Phase 0: No-op
        return StepResult(
            step=WorkflowStep.SELF_HEAL, success=True, output={"healed": False, "reason": "No issues found"}
        )

    def _update_state_from_result(self, state: WorkflowState, step: WorkflowStep, result: StepResult) -> None:
        """Step 결과를 state에 반영"""
        if step == WorkflowStep.ANALYZE:
            state.context["analyzed_data"] = result.output
        elif step == WorkflowStep.GENERATE:
            state.result = result.output
        elif step == WorkflowStep.TEST:
            state.context["test_result"] = result.output

    def _should_exit_early(self, state: WorkflowState) -> bool:
        """
        Early exit 조건 체크

        Phase 0: 항상 1회 실행 후 종료
        Phase 1: 테스트 통과 시 종료
        """
        # Phase 0: 1회 실행 후 종료
        if not self.enable_full_workflow:
            return True

        # Phase 1: 테스트 통과 체크
        test_result = state.context.get("test_result")
        if test_result and test_result.get("passed"):
            return True

        return False

    def _request_wrap_up(self, state: WorkflowState, total_tokens: int) -> str:
        """
        Wrap-up 요약 생성 (Refact 스타일)

        Args:
            state: 현재 상태
            total_tokens: 사용한 총 토큰 수

        Returns:
            작업 요약 텍스트
        """
        # Phase 0: 간단한 요약 생성 (LLM 없이)
        summary_parts = []

        # 종료 사유
        exit_reason = state.exit_reason.value if state.exit_reason else "unknown"
        summary_parts.append(f"종료 사유: {exit_reason}")

        # 반복 횟수
        summary_parts.append(f"반복 횟수: {state.iteration}/{self.max_iterations}")

        # 토큰 사용량
        summary_parts.append(f"토큰 사용: {total_tokens}/{self.max_tokens}")

        # 실행된 단계
        steps_executed = [result.step.value for result in state.step_history if result.success]
        summary_parts.append(f"실행 단계: {', '.join(steps_executed)}")

        # 최종 결과
        if state.result:
            summary_parts.append("결과: 생성 완료")
        elif state.error:
            summary_parts.append(f"오류: {state.error}")
        else:
            summary_parts.append("결과: 없음")

        return "\n".join(summary_parts)
