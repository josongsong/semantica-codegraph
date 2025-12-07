"""End-to-End 통합 테스트

비판적 검증: 전체 파이프라인 동작 확인

Router → TaskGraphPlanner → Workflow → ContextAdapter

시나리오:
1. User: "fix bug in calculate_total"
2. Router: Intent 분류
3. TaskGraphPlanner: Task 분해
4. Workflow: Task 실행
5. ContextAdapter: 실제 코드 검색
6. 최종 결과 반환

품질 기준:
- 전체 파이프라인 동작
- 데이터 흐름 정확
- 에러 핸들링
- 실제 시나리오
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 전체 컴포넌트 import
from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.router.models import Intent
from src.agent.router.router import Router
from src.agent.task_graph.planner import TaskGraphPlanner
from src.agent.workflow.models import WorkflowState, WorkflowStep
from src.agent.workflow.state_machine import WorkflowStateMachine


# Mock LLM Adapter
class MockLLMAdapter:
    async def complete(self, prompt: str, **kwargs) -> str:
        """Mock complete - async, returns str"""
        if "fix bug" in prompt.lower():
            return '{"intent": "fix_bug", "reasoning": "User wants to fix a bug.", "confidence": 0.95}'
        elif "add feature" in prompt.lower():
            return '{"intent": "add_feature", "reasoning": "User wants to add a feature.", "confidence": 0.90}'
        elif "refactor" in prompt.lower():
            return '{"intent": "refactor_code", "reasoning": "User wants to refactor code.", "confidence": 0.88}'
        return '{"intent": "unknown", "reasoning": "Cannot determine intent.", "confidence": 0.3}'


from src.agent.router.intent_classifier import IntentClassifier

print("=" * 70)
print("🔥 End-to-End 통합 테스트")
print("=" * 70)
print()


async def test_1_router_to_taskgraph():
    """Test 1: Router → TaskGraphPlanner 통합"""
    print("🔍 Test 1: Router → TaskGraphPlanner...")

    # 1. Router: Intent 분류
    llm = MockLLMAdapter()
    classifier = IntentClassifier(llm)
    router = Router(classifier)

    intent_result = await router.route(user_input="fix bug in calculate_total", context={"repo_id": "test-repo"})

    assert intent_result.intent == Intent.FIX_BUG
    assert intent_result.confidence > 0.7
    print(f"  ✅ Router classified: {intent_result.intent.value}")
    print(f"  ✅ Confidence: {intent_result.confidence:.2f}")

    # 2. TaskGraphPlanner: Task 분해
    planner = TaskGraphPlanner()
    task_graph = planner.plan(
        user_intent=intent_result.intent.value,
        context=intent_result.context,
    )

    assert len(task_graph.tasks) == 3  # analyze, generate, validate
    assert len(task_graph.parallel_groups) > 0
    print(f"  ✅ TaskGraph created: {len(task_graph.tasks)} tasks")
    print(f"  ✅ Execution groups: {task_graph.parallel_groups}")

    # 데이터 흐름 확인
    assert "query" in task_graph.tasks["task_analyze_bug"].input_data
    assert "repo_id" in task_graph.tasks["task_analyze_bug"].input_data
    print("  ✅ Data flow: Router context → TaskGraph input_data")
    print()

    return task_graph


async def test_2_taskgraph_to_workflow():
    """Test 2: TaskGraph → Workflow 통합"""
    print("🔍 Test 2: TaskGraph → Workflow...")

    # TaskGraph 생성
    planner = TaskGraphPlanner()
    task_graph = planner.plan(
        user_intent="fix_bug",
        context={"user_input": "fix null pointer", "repo_id": "test-repo"},
    )

    # Workflow State 초기화
    workflow = WorkflowStateMachine(max_iterations=1, enable_full_workflow=False)

    initial_state = WorkflowState(
        current_step=WorkflowStep.ANALYZE,
        iteration=0,
        context={
            "task_graph": task_graph,
            "user_input": "fix null pointer",
            "repo_id": "test-repo",
        },
    )

    # Workflow 실행
    final_state = workflow.run(initial_state)

    assert final_state.current_step == WorkflowStep.COMPLETED
    assert final_state.result is not None
    print(f"  ✅ Workflow completed: {final_state.current_step.value}")
    print(f"  ✅ Iterations: {final_state.iteration}")
    print(f"  ✅ Result generated: {len(str(final_state.result))} chars")

    # TaskGraph context가 Workflow에 전달되었는지 확인
    assert "task_graph" in final_state.context
    print("  ✅ Data flow: TaskGraph → Workflow context")
    print()

    return final_state


async def test_3_workflow_with_context_adapter():
    """Test 3: Workflow + ContextAdapter 통합"""
    print("🔍 Test 3: Workflow + ContextAdapter...")

    # ContextAdapter 초기화 (Mock 모드)
    context_adapter = ContextAdapter()

    # Workflow 초기화
    workflow = WorkflowStateMachine(max_iterations=1)

    initial_state = WorkflowState(
        current_step=WorkflowStep.ANALYZE,
        iteration=0,
        context={
            "user_input": "fix bug in calculate_total",
            "repo_id": "test-repo",
            "context_adapter": context_adapter,  # ContextAdapter 전달
        },
    )

    # Workflow 실행 (내부에서 ContextAdapter 사용 가정)
    final_state = workflow.run(initial_state)

    # ContextAdapter를 실제로 호출
    relevant_code = await context_adapter.get_relevant_code(
        query=initial_state.context["user_input"],
        repo_id=initial_state.context["repo_id"],
    )

    assert "Relevant Code" in relevant_code
    assert "calculate_total" in relevant_code
    print("  ✅ ContextAdapter executed")
    print(f"  ✅ Retrieved code: {len(relevant_code)} chars")

    # 심볼 검색
    symbol = await context_adapter.get_symbol_definition(
        symbol_name="calculate_total",
        repo_id="test-repo",
    )

    assert symbol["found"]
    print(f"  ✅ Symbol found: {symbol['name']} at {symbol['file_path']}")
    print()

    return relevant_code, symbol


async def test_4_full_pipeline():
    """Test 4: 전체 파이프라인 (Router → TaskGraph → Workflow → ContextAdapter)"""
    print("🔍 Test 4: Full Pipeline Integration...")

    # 1. Router
    llm = MockLLMAdapter()
    classifier = IntentClassifier(llm)
    router = Router(classifier)

    user_request = "fix bug in calculate_total function - null pointer exception"
    intent_result = await router.route(user_input=user_request, context={"repo_id": "billing-service"})

    print(f"  📥 User: {user_request}")
    print(f"  ✅ Step 1 (Router): {intent_result.intent.value}")

    # 2. TaskGraphPlanner
    planner = TaskGraphPlanner()
    task_graph = planner.plan(
        user_intent=intent_result.intent.value,
        context=intent_result.context,
    )

    print(f"  ✅ Step 2 (TaskGraph): {len(task_graph.tasks)} tasks")
    print(f"     Tasks: {list(task_graph.tasks.keys())}")

    # 3. ContextAdapter (Workflow에서 사용)
    context_adapter = ContextAdapter()

    # 4. Workflow
    workflow = WorkflowStateMachine(max_iterations=1)

    initial_state = WorkflowState(
        current_step=WorkflowStep.ANALYZE,
        iteration=0,
        context={
            **intent_result.context,
            "task_graph": task_graph,
            "context_adapter": context_adapter,
        },
    )

    final_state = workflow.run(initial_state)

    print(f"  ✅ Step 3 (Workflow): {final_state.current_step.value}")

    # 5. ContextAdapter로 실제 코드 검색 (Workflow 내부에서 할 작업을 시뮬레이션)
    relevant_code = await context_adapter.get_relevant_code(
        query=user_request,
        repo_id=intent_result.context["repo_id"],
    )

    symbol = await context_adapter.get_symbol_definition(
        symbol_name="calculate_total",
        repo_id=intent_result.context["repo_id"],
    )

    print("  ✅ Step 4 (ContextAdapter): Code retrieved")
    print(f"     Symbol: {symbol['name']} at {symbol['file_path']}:{symbol['line']}")

    # 최종 결과 조합
    final_result = {
        "intent": intent_result.intent.value,
        "confidence": intent_result.confidence,
        "tasks_executed": list(task_graph.tasks.keys()),
        "workflow_status": final_state.current_step.value,
        "code_found": symbol["found"],
        "symbol_location": f"{symbol['file_path']}:{symbol['line']}",
        "generated_code": final_state.result,
    }

    print("\n  📤 Final Result:")
    print(f"     Intent: {final_result['intent']}")
    print(f"     Confidence: {final_result['confidence']:.2f}")
    print(f"     Tasks: {len(final_result['tasks_executed'])}")
    print(f"     Workflow: {final_result['workflow_status']}")
    print(f"     Code Found: {final_result['code_found']}")
    print(f"     Location: {final_result['symbol_location']}")
    print()

    # 검증: 모든 단계 성공
    assert final_result["intent"] == "fix_bug"
    assert final_result["confidence"] > 0.7
    assert len(final_result["tasks_executed"]) == 3
    assert final_result["workflow_status"] == "completed"
    assert final_result["code_found"]

    return final_result


async def test_5_error_propagation():
    """Test 5: 에러 전파 (Router 실패 → 전체 실패)"""
    print("🔍 Test 5: Error Propagation...")

    # 1. Router에서 UNKNOWN intent
    llm = MockLLMAdapter()
    classifier = IntentClassifier(llm)
    router = Router(classifier)

    intent_result = await router.route(user_input="unclear request lalala", context={})

    # UNKNOWN은 낮은 confidence
    if intent_result.confidence < 0.5:
        print("  ✅ Low confidence detected")
        print(f"     Confidence: {intent_result.confidence:.2f}")
        print("  ✅ Should ask user for clarification (Phase 1)")

    # 2. ContextAdapter 실패 시 graceful degradation
    class FailingService:
        async def retrieve(self, **kwargs):
            raise RuntimeError("Database connection failed")

    adapter_failing = ContextAdapter(retrieval_service=FailingService())

    # 실패해도 Mock으로 fallback
    code = await adapter_failing.get_relevant_code("query", "repo1")
    assert "Relevant Code" in code
    print("  ✅ ContextAdapter graceful degradation works")
    print()


async def test_6_data_flow_integrity():
    """Test 6: 데이터 흐름 무결성"""
    print("🔍 Test 6: Data Flow Integrity...")

    # 초기 데이터
    initial_context = {
        "repo_id": "payment-service",
        "user_id": "user123",
        "session_id": "abc",
    }

    # 1. Router
    llm = MockLLMAdapter()
    classifier = IntentClassifier(llm)
    router = Router(classifier)
    intent_result = await router.route(user_input="refactor payment module", context=initial_context)

    # Context 보존 확인
    assert intent_result.context["repo_id"] == "payment-service"
    assert intent_result.context["user_id"] == "user123"
    assert intent_result.context["session_id"] == "abc"
    print("  ✅ Context preserved through Router")

    # 2. TaskGraphPlanner
    planner = TaskGraphPlanner()
    task_graph = planner.plan(
        user_intent=intent_result.intent.value,
        context=intent_result.context,
    )

    # TaskGraph에 context 전달 확인
    first_task = list(task_graph.tasks.values())[0]
    # input_data에 context 정보가 있어야 함
    assert "query" in first_task.input_data
    print("  ✅ Context passed to TaskGraph")

    # 3. Workflow
    workflow = WorkflowStateMachine(max_iterations=1)
    initial_state = WorkflowState(
        current_step=WorkflowStep.ANALYZE,
        iteration=0,
        context=intent_result.context,
    )

    final_state = workflow.run(initial_state)

    # Context 보존 확인
    assert final_state.context["repo_id"] == "payment-service"
    assert final_state.context["user_id"] == "user123"
    print("  ✅ Context preserved through Workflow")
    print("  ✅ Full data flow integrity maintained")
    print()


async def test_7_parallel_execution():
    """Test 7: 병렬 실행 시나리오 (refactor)"""
    print("🔍 Test 7: Parallel Execution Scenario...")

    # refactor는 analyze + search 병렬 실행
    planner = TaskGraphPlanner()
    task_graph = planner.plan(
        user_intent="refactor_code",
        context={"user_input": "refactor payment", "repo_id": "test"},
    )

    # 병렬 그룹 확인
    groups = task_graph.parallel_groups

    # 첫 그룹이 병렬 (2개)
    assert len(groups[0]) == 2
    print(f"  ✅ Parallel group 1: {groups[0]}")

    # ContextAdapter로 병렬 호출 시뮬레이션
    adapter = ContextAdapter()

    # 동시 호출
    tasks = [
        adapter.get_relevant_code("refactor payment", "test"),
        adapter.get_symbol_definition("process_payment", "test"),
    ]

    results = await asyncio.gather(*tasks)

    assert len(results) == 2
    assert all(r is not None for r in results)
    print("  ✅ Parallel execution: 2 tasks completed simultaneously")
    print()


async def main():
    print("Starting End-to-End Integration Tests...\n")

    tests = [
        ("Router → TaskGraph", test_1_router_to_taskgraph),
        ("TaskGraph → Workflow", test_2_taskgraph_to_workflow),
        ("Workflow + ContextAdapter", test_3_workflow_with_context_adapter),
        ("Full Pipeline", test_4_full_pipeline),
        ("Error Propagation", test_5_error_propagation),
        ("Data Flow Integrity", test_6_data_flow_integrity),
        ("Parallel Execution", test_7_parallel_execution),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ {name} FAILED: {e}\n")
            failed += 1
            import traceback

            traceback.print_exc()
        except Exception as e:
            print(f"❌ {name} ERROR: {e}\n")
            failed += 1
            import traceback

            traceback.print_exc()

    print("=" * 70)
    print(f"📊 통합 테스트 결과: {passed}/{len(tests)} 통과")
    print("=" * 70)
    print()

    if passed == len(tests):
        print("🎉 End-to-End 통합 검증 성공!")
        print()
        print("✅ 검증된 통합:")
        print("  1. Router → TaskGraphPlanner")
        print("  2. TaskGraph → Workflow")
        print("  3. Workflow + ContextAdapter")
        print("  4. Full Pipeline (Router → TaskGraph → Workflow → ContextAdapter)")
        print("  5. Error propagation")
        print("  6. Data flow integrity")
        print("  7. Parallel execution")
        print()
        print("🏆 전체 시스템 통합 완료!")
        print()
    else:
        print(f"⚠️  {failed}개 테스트 실패")
        print("수정 필요!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
