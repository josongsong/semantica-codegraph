"""Task Graph 비판적 검증

Week 1 수준의 엄격한 검증:
1. Import 정상
2. DAG 검증 (Cycle 방지)
3. Topological Sort 정확성
4. 병렬 그룹 정확성
5. Task 의존성 검증
6. Edge Cases
7. Planner 통합
8. 메모리 누수
9. 에러 핸들링
10. 실제 시나리오
"""

import gc
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.task_graph.models import (
    Task,
    TaskGraph,
    TaskStatus,
    TaskType,
)
from src.agent.task_graph.planner import TaskGraphPlanner

print("=" * 70)
print("🔥 Task Graph 비판적 검증")
print("=" * 70)
print()


def test_1_imports():
    """Test 1: Import 정상 동작"""
    print("🔍 Test 1: Imports...")

    assert Task is not None
    assert TaskGraph is not None
    assert TaskType is not None
    assert TaskStatus is not None
    assert TaskGraphPlanner is not None

    print("  ✅ All imports successful")
    print()


def test_2_task_creation():
    """Test 2: Task 생성 및 검증"""
    print("🔍 Test 2: Task Creation & Validation...")

    # 정상 Task
    task = Task(
        id="task1",
        type=TaskType.ANALYZE_CODE,
        description="Test task",
        depends_on=[],
    )
    assert task.id == "task1"
    assert task.status == TaskStatus.PENDING
    print("  ✅ Task created successfully")

    # 자기 자신 의존 방지
    try:
        task_self_dep = Task(
            id="task_bad",
            type=TaskType.ANALYZE_CODE,
            description="Bad task",
            depends_on=["task_bad"],  # 자기 자신
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot depend on itself" in str(e)
        print("  ✅ Self-dependency prevented")

    print()


def test_3_dag_validation():
    """Test 3: DAG 검증 (Cycle 방지)"""
    print("🔍 Test 3: DAG Validation (Cycle Detection)...")

    # 정상 DAG
    graph = TaskGraph()

    task1 = Task(id="t1", type=TaskType.ANALYZE_CODE, description="Task 1")
    task2 = Task(id="t2", type=TaskType.GENERATE_CODE, description="Task 2", depends_on=["t1"])
    task3 = Task(id="t3", type=TaskType.VALIDATE_CHANGES, description="Task 3", depends_on=["t2"])

    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_task(task3)

    assert graph.validate_dag()
    print("  ✅ Valid DAG accepted (t1 → t2 → t3)")

    # Cycle 테스트: 직접 tasks에 추가하여 의존성 체크 우회
    graph_cycle = TaskGraph()

    task_c1 = Task(id="c1", type=TaskType.ANALYZE_CODE, description="C1", depends_on=["c3"])
    task_c2 = Task(id="c2", type=TaskType.GENERATE_CODE, description="C2", depends_on=["c1"])
    task_c3 = Task(id="c3", type=TaskType.VALIDATE_CHANGES, description="C3", depends_on=["c2"])

    # 의존성 체크 우회를 위해 직접 추가
    graph_cycle.tasks["c1"] = task_c1
    graph_cycle.tasks["c2"] = task_c2
    graph_cycle.tasks["c3"] = task_c3

    try:
        graph_cycle.validate_dag()
        assert False, "Should have detected cycle"
    except ValueError as e:
        assert "Cycle detected" in str(e)
        print("  ✅ Cycle detected and rejected")

    print()


def test_4_topological_sort():
    """Test 4: Topological Sort 정확성"""
    print("🔍 Test 4: Topological Sort...")

    graph = TaskGraph()

    # DAG: t1, t2 (병렬) → t3 → t4
    task1 = Task(id="t1", type=TaskType.ANALYZE_CODE, description="T1")
    task2 = Task(id="t2", type=TaskType.SEARCH_SYMBOLS, description="T2")
    task3 = Task(id="t3", type=TaskType.GENERATE_CODE, description="T3", depends_on=["t1", "t2"])
    task4 = Task(id="t4", type=TaskType.VALIDATE_CHANGES, description="T4", depends_on=["t3"])

    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_task(task3)
    graph.add_task(task4)

    order = graph.topological_sort()

    # 검증: 의존성 순서 보장
    assert order.index("t1") < order.index("t3")
    assert order.index("t2") < order.index("t3")
    assert order.index("t3") < order.index("t4")

    print(f"  ✅ Topological sort: {order}")
    print("  ✅ Dependencies respected")
    print()


def test_5_parallel_groups():
    """Test 5: 병렬 실행 그룹 정확성"""
    print("🔍 Test 5: Parallel Execution Groups...")

    graph = TaskGraph()

    # DAG: [t1, t2] (병렬) → [t3] → [t4, t5] (병렬)
    task1 = Task(id="t1", type=TaskType.ANALYZE_CODE, description="T1")
    task2 = Task(id="t2", type=TaskType.SEARCH_SYMBOLS, description="T2")
    task3 = Task(id="t3", type=TaskType.GENERATE_CODE, description="T3", depends_on=["t1", "t2"])
    task4 = Task(id="t4", type=TaskType.REVIEW_CODE, description="T4", depends_on=["t3"])
    task5 = Task(id="t5", type=TaskType.RUN_TESTS, description="T5", depends_on=["t3"])

    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_task(task3)
    graph.add_task(task4)
    graph.add_task(task5)

    groups = graph.get_parallel_groups()

    # 검증: 3개 그룹
    assert len(groups) == 3
    assert set(groups[0]) == {"t1", "t2"}
    assert groups[1] == ["t3"]
    assert set(groups[2]) == {"t4", "t5"}

    print(f"  ✅ Parallel groups: {groups}")
    print("  ✅ Group 1: t1, t2 (parallel)")
    print("  ✅ Group 2: t3 (sequential)")
    print("  ✅ Group 3: t4, t5 (parallel)")
    print()


def test_6_task_ready_check():
    """Test 6: Task ready 상태 확인"""
    print("🔍 Test 6: Task Ready Check...")

    task1 = Task(id="t1", type=TaskType.ANALYZE_CODE, description="T1")
    task2 = Task(id="t2", type=TaskType.GENERATE_CODE, description="T2", depends_on=["t1"])

    # task1은 의존성 없으므로 ready
    assert task1.is_ready(set())
    print("  ✅ t1 ready (no dependencies)")

    # task2는 t1 완료 전에는 not ready
    assert not task2.is_ready(set())
    print("  ✅ t2 not ready (t1 pending)")

    # task2는 t1 완료 후 ready
    assert task2.is_ready({"t1"})
    print("  ✅ t2 ready (t1 completed)")
    print()


def test_7_planner_fix_bug():
    """Test 7: Planner - fix_bug"""
    print("🔍 Test 7: Planner (fix_bug)...")

    planner = TaskGraphPlanner()

    graph = planner.plan(
        user_intent="fix_bug",
        context={"user_input": "fix null pointer", "repo_id": "test-repo"},
    )

    # 검증: 3개 Task (analyze → generate → validate)
    assert len(graph.tasks) == 3
    assert "task_analyze_bug" in graph.tasks
    assert "task_generate_fix" in graph.tasks
    assert "task_validate_fix" in graph.tasks

    # 실행 순서 확인
    order = graph.execution_order
    assert order.index("task_analyze_bug") < order.index("task_generate_fix")
    assert order.index("task_generate_fix") < order.index("task_validate_fix")

    print(f"  ✅ Tasks: {list(graph.tasks.keys())}")
    print(f"  ✅ Execution order: {order}")
    print()


def test_8_planner_refactor():
    """Test 8: Planner - refactor (병렬 실행)"""
    print("🔍 Test 8: Planner (refactor - parallel)...")

    planner = TaskGraphPlanner()

    graph = planner.plan(
        user_intent="refactor_code",
        context={"user_input": "refactor payment module"},
    )

    # 검증: analyze와 search가 병렬 실행 가능
    groups = graph.parallel_groups

    # 첫 번째 그룹에 analyze와 search 모두 포함
    assert len(groups[0]) == 2
    assert "task_analyze_refactor_target" in groups[0]
    assert "task_search_dependencies" in groups[0]

    print(f"  ✅ Parallel group 1: {groups[0]}")
    print("  ✅ analyze + search run in parallel")
    print()


def test_9_edge_cases():
    """Test 9: Edge Cases"""
    print("🔍 Test 9: Edge Cases...")

    # Empty graph
    graph_empty = TaskGraph()
    assert len(graph_empty.tasks) == 0
    assert graph_empty.topological_sort() == []
    assert graph_empty.get_parallel_groups() == []
    print("  ✅ Empty graph handled")

    # Single task
    graph_single = TaskGraph()
    task_single = Task(id="t1", type=TaskType.ANALYZE_CODE, description="Single")
    graph_single.add_task(task_single)
    assert graph_single.topological_sort() == ["t1"]
    assert graph_single.get_parallel_groups() == [["t1"]]
    print("  ✅ Single task handled")

    # Duplicate task ID
    graph_dup = TaskGraph()
    task_dup1 = Task(id="dup", type=TaskType.ANALYZE_CODE, description="Dup1")
    task_dup2 = Task(id="dup", type=TaskType.GENERATE_CODE, description="Dup2")
    graph_dup.add_task(task_dup1)
    try:
        graph_dup.add_task(task_dup2)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "already exists" in str(e)
        print("  ✅ Duplicate ID prevented")

    # Missing dependency
    graph_missing = TaskGraph()
    task_missing = Task(id="t1", type=TaskType.GENERATE_CODE, description="Bad", depends_on=["missing"])
    try:
        graph_missing.add_task(task_missing)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "does not exist" in str(e)
        print("  ✅ Missing dependency detected")

    print()


def test_10_memory_leaks():
    """Test 10: 메모리 누수"""
    print("🔍 Test 10: Memory Leaks...")

    gc.collect()
    initial_objects = len(gc.get_objects())

    # 100번 반복
    for i in range(100):
        graph = TaskGraph()
        for j in range(10):
            task = Task(
                id=f"task_{i}_{j}",
                type=TaskType.ANALYZE_CODE,
                description=f"Task {i}-{j}",
                depends_on=[f"task_{i}_{j - 1}"] if j > 0 else [],
            )
            if j == 0 or f"task_{i}_{j - 1}" in graph.tasks:
                graph.add_task(task)

        graph.topological_sort()
        graph.get_parallel_groups()

    gc.collect()
    final_objects = len(gc.get_objects())

    # 메모리 증가 확인 (너무 많이 증가하면 누수)
    increase = final_objects - initial_objects
    assert increase < 1000, f"Potential memory leak: {increase} objects"

    print("  ✅ 100 iterations completed")
    print(f"  ✅ Object increase: {increase} (acceptable)")
    print()


if __name__ == "__main__":
    tests = [
        ("Imports", test_1_imports),
        ("Task Creation", test_2_task_creation),
        ("DAG Validation", test_3_dag_validation),
        ("Topological Sort", test_4_topological_sort),
        ("Parallel Groups", test_5_parallel_groups),
        ("Task Ready Check", test_6_task_ready_check),
        ("Planner fix_bug", test_7_planner_fix_bug),
        ("Planner refactor", test_8_planner_refactor),
        ("Edge Cases", test_9_edge_cases),
        ("Memory Leaks", test_10_memory_leaks),
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
            failed += 1
            import traceback

            traceback.print_exc()

    print("=" * 70)
    print(f"📊 테스트 결과: {passed}/{len(tests)} 통과")
    print("=" * 70)
    print()

    if passed == len(tests):
        print("🎉 Task Graph 비판적 검증 통과!")
        print()
        print("✅ 검증된 항목:")
        print("  1. Imports")
        print("  2. Task creation & validation")
        print("  3. DAG validation (cycle detection)")
        print("  4. Topological sort")
        print("  5. Parallel execution groups")
        print("  6. Task ready check")
        print("  7. Planner (fix_bug)")
        print("  8. Planner (refactor - parallel)")
        print("  9. Edge cases")
        print("  10. Memory leaks")
        print()
        print("✅ Day 17-18 완료 - Task Graph Planner 준비됨")
        print()
    else:
        print(f"⚠️  {failed}개 테스트 실패")
        print("수정 필요!")
        sys.exit(1)
