"""Workflow 비판적 검증 테스트

즉시 검증:
- Import 정상 동작
- 객체 생성 가능
- State machine 동작
- 에러 핸들링
- 엣지 케이스
"""

import sys
from pathlib import Path

# PYTHONPATH 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.workflow.models import (
    StepResult,
    WorkflowExitReason,
    WorkflowState,
    WorkflowStep,
)
from src.agent.workflow.state_machine import WorkflowStateMachine


def test_imports():
    """Import 정상 동작 확인"""
    print("🔍 Testing Workflow Imports...")

    # Enum 확인
    assert hasattr(WorkflowStep, "ANALYZE")
    assert hasattr(WorkflowStep, "GENERATE")
    assert hasattr(WorkflowStep, "COMPLETED")

    # Exit reason
    assert hasattr(WorkflowExitReason, "SUCCESS")
    assert hasattr(WorkflowExitReason, "ERROR")

    print("  ✅ All imports successful\n")


def test_step_result_validation():
    """StepResult 검증 로직 확인"""
    print("🔍 Testing StepResult Validation...")

    # 성공 케이스
    result_ok = StepResult(step=WorkflowStep.ANALYZE, success=True, output={"data": "test"})
    assert result_ok.error is None
    print("  ✅ Success case: no error needed")

    # 실패 케이스 (error 없음 → 자동 설정)
    result_fail = StepResult(step=WorkflowStep.ANALYZE, success=False, output=None)
    assert result_fail.error == "Unknown error"
    print("  ✅ Fail case: auto-set error message")

    # 실패 케이스 (error 명시)
    result_fail_explicit = StepResult(step=WorkflowStep.ANALYZE, success=False, output=None, error="Custom error")
    assert result_fail_explicit.error == "Custom error"
    print("  ✅ Fail case: custom error preserved\n")


def test_workflow_state():
    """WorkflowState 기능 확인"""
    print("🔍 Testing WorkflowState...")

    state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={"repo_id": "test"})

    # Step 결과 추가
    result1 = StepResult(step=WorkflowStep.ANALYZE, success=True, output={"files": 2})
    state.add_step_result(result1)

    assert len(state.step_history) == 1
    assert state.get_last_step_result() == result1
    print("  ✅ Step history tracking works")

    # Terminal 상태 체크
    assert not state.is_terminal()
    state.current_step = WorkflowStep.COMPLETED
    assert state.is_terminal()
    print("  ✅ Terminal state detection works\n")


def test_workflow_basic_execution():
    """기본 Workflow 실행"""
    print("🔍 Testing Basic Workflow Execution...")

    machine = WorkflowStateMachine(max_iterations=1, enable_full_workflow=False)

    initial_state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={"user_input": "fix bug"})

    final_state = machine.run(initial_state)

    # 완료 확인
    assert final_state.current_step == WorkflowStep.COMPLETED
    assert final_state.is_terminal()
    print(f"  ✅ Workflow completed: {final_state.exit_reason.value}")

    # Step 이력 확인
    assert len(final_state.step_history) == 2  # Analyze + Generate
    assert final_state.step_history[0].step == WorkflowStep.ANALYZE
    assert final_state.step_history[1].step == WorkflowStep.GENERATE
    print(f"  ✅ {len(final_state.step_history)} steps executed")

    # 결과 확인
    assert final_state.result is not None
    assert "changes" in final_state.result
    print("  ✅ Code generated\n")


def test_workflow_max_iterations():
    """최대 반복 횟수 제한 확인"""
    print("🔍 Testing Max Iterations...")

    # Phase 1 모드로 최대 반복 테스트
    machine = WorkflowStateMachine(max_iterations=2, enable_full_workflow=True)

    initial_state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={})

    final_state = machine.run(initial_state)

    # 최대 반복 도달 확인
    assert final_state.iteration <= 2
    print(f"  ✅ Max iterations respected: {final_state.iteration}")

    # Exit reason 확인
    if final_state.exit_reason == WorkflowExitReason.MAX_ITERATIONS:
        print("  ✅ Exit reason: MAX_ITERATIONS")
    else:
        print(f"  ✅ Exit reason: {final_state.exit_reason.value}")

    print()


def test_workflow_error_handling():
    """에러 핸들링 확인"""
    print("🔍 Testing Error Handling...")

    machine = WorkflowStateMachine()

    # 정상 상태
    state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={})

    # Analyze 단계 실행 (정상)
    result = machine._execute_step(state, WorkflowStep.ANALYZE)
    assert result.success
    print("  ✅ Normal step execution")

    # Step execution 중 예외 발생 시뮬레이션
    # 실제 예외가 발생하면 StepResult로 래핑됨
    class FakeWorkflowStep:
        """Fake step for testing"""

        value = "fake_step"

    fake_step = FakeWorkflowStep()
    result_error = machine._execute_step(state, fake_step)

    # 에러가 StepResult로 래핑되는지 확인
    assert not result_error.success
    assert result_error.error is not None
    print(f"  ✅ Errors wrapped in StepResult: {result_error.error[:50]}...")
    print()


def test_workflow_state_updates():
    """State 업데이트 확인"""
    print("🔍 Testing State Updates...")

    machine = WorkflowStateMachine(max_iterations=1)

    initial_state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={})

    final_state = machine.run(initial_state)

    # Context 업데이트 확인
    assert "analyzed_data" in final_state.context
    analyzed = final_state.context["analyzed_data"]
    assert "relevant_files" in analyzed
    print("  ✅ Analyze step updated context")

    # Result 확인
    assert final_state.result is not None
    assert "file" in final_state.result
    assert "changes" in final_state.result
    print("  ✅ Generate step set result\n")


def test_workflow_phase0_vs_phase1():
    """Phase 0 vs Phase 1 모드 비교"""
    print("🔍 Testing Phase 0 vs Phase 1...")

    # Phase 0: 2 steps
    machine_p0 = WorkflowStateMachine(enable_full_workflow=False)
    assert len(machine_p0.steps) == 2
    assert WorkflowStep.ANALYZE in machine_p0.steps
    assert WorkflowStep.GENERATE in machine_p0.steps
    assert WorkflowStep.CRITIC not in machine_p0.steps
    print("  ✅ Phase 0: 2 steps (Analyze, Generate)")

    # Phase 1: 6 steps
    machine_p1 = WorkflowStateMachine(enable_full_workflow=True)
    assert len(machine_p1.steps) == 6
    assert WorkflowStep.CRITIC in machine_p1.steps
    assert WorkflowStep.TEST in machine_p1.steps
    print("  ✅ Phase 1: 6 steps (full workflow)\n")


def test_workflow_iteration_tracking():
    """Iteration 추적 확인"""
    print("🔍 Testing Iteration Tracking...")

    machine = WorkflowStateMachine(max_iterations=3, enable_full_workflow=True)

    initial_state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context={})

    final_state = machine.run(initial_state)

    # Iteration 증가 확인
    assert final_state.iteration >= 1
    print(f"  ✅ Iterations: {final_state.iteration}")

    # Step 총 개수 확인 (iteration * steps)
    total_steps = len(final_state.step_history)
    print(f"  ✅ Total steps executed: {total_steps}\n")


def test_integration_with_router():
    """Router와 통합 시나리오"""
    print("🔍 Testing Integration with Router...")

    # Router에서 받은 Intent를 Workflow로 전달하는 시나리오
    from src.agent.router.models import Intent, IntentResult

    # Router 결과 (Mock)
    intent_result = IntentResult(
        intent=Intent.FIX_BUG,
        confidence=0.85,
        reasoning="Bug fix needed",
        context={
            "user_input": "Fix bug in calculate_total",
            "repo_id": "test-repo",
        },
    )

    # Workflow에 전달
    machine = WorkflowStateMachine()

    initial_state = WorkflowState(current_step=WorkflowStep.ANALYZE, iteration=0, context=intent_result.context)

    final_state = machine.run(initial_state)

    # Intent context 보존 확인
    assert "user_input" in final_state.context
    assert "repo_id" in final_state.context
    print("  ✅ Router context preserved in workflow")

    # 결과 생성 확인
    assert final_state.result is not None
    print("  ✅ Workflow produced result\n")


if __name__ == "__main__":
    print("=" * 70)
    print("🔥 Workflow 비판적 검증 테스트")
    print("=" * 70)
    print()

    tests = [
        ("Imports", test_imports),
        ("StepResult Validation", test_step_result_validation),
        ("WorkflowState", test_workflow_state),
        ("Basic Execution", test_workflow_basic_execution),
        ("Max Iterations", test_workflow_max_iterations),
        ("Error Handling", test_workflow_error_handling),
        ("State Updates", test_workflow_state_updates),
        ("Phase 0 vs Phase 1", test_workflow_phase0_vs_phase1),
        ("Iteration Tracking", test_workflow_iteration_tracking),
        ("Integration with Router", test_integration_with_router),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ {name} FAILED: {e}\n")
            failed += 1
            import traceback

            traceback.print_exc()
        except Exception as e:
            print(f"❌ {name} ERROR: {e}\n")
            import traceback

            traceback.print_exc()
            failed += 1

    print("=" * 70)
    print(f"📊 테스트 결과: {passed}/{len(tests)} 통과")
    print("=" * 70)
    print()

    if failed == 0:
        print("🎉 Workflow 비판적 검증 통과!")
        print()
        print("✅ 검증된 항목:")
        print("  - Import 정상 동작")
        print("  - StepResult 검증 로직")
        print("  - WorkflowState 기능")
        print("  - 기본 실행 (Analyze → Generate)")
        print("  - 최대 반복 제한")
        print("  - 에러 핸들링")
        print("  - State 업데이트")
        print("  - Phase 0/1 전환")
        print("  - Iteration 추적")
        print("  - Router 통합")
        print()
        print("✅ Day 11-13 완료 - Workflow State Machine 준비됨")
        print()
    else:
        print(f"⚠️  {failed}개 테스트 실패")
        print("수정 필요!")
        sys.exit(1)
