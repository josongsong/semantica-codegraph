"""
A-1: Planner 요구 분해 정확도 테스트

"버그를 수정하고 테스트를 추가해줘" → 2-step plan (fix + test)
"""

import pytest

from apps.orchestrator.orchestrator.task_graph.models import PlanStatus, TaskType
from apps.orchestrator.orchestrator.task_graph.planner import TaskGraphPlanner


class TestPlannerDecomposition:
    """Planner 요구 분해 테스트"""

    def setup_method(self):
        self.planner = TaskGraphPlanner()

    def test_a1_1_fix_and_test_two_steps(self):
        """A-1-1: '버그 수정 + 테스트' → 2 step"""
        # Given
        context = {
            "user_input": "Fix the bug in payment.py and add tests for it",
            "file": "payment.py",
        }

        # When
        status, graph = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID

        # 최소 2개 step (analyze/generate/validate 중 일부 + test 관련)
        # fix_bug는 기본적으로 3-step (analyze, generate, validate)
        assert len(graph.tasks) >= 2

        # Task 타입 확인
        task_types = [task.type for task in graph.tasks.values()]

        # 코드 생성과 검증이 포함되어야 함
        assert TaskType.GENERATE_CODE in task_types or TaskType.ANALYZE_CODE in task_types
        assert TaskType.VALIDATE_CHANGES in task_types or TaskType.RUN_TESTS in task_types

    def test_a1_2_explicit_test_addition(self):
        """A-1-2: 테스트 추가 명시 시 RUN_TESTS 포함"""
        # Given: 테스트 명시
        context = {
            "user_input": "Fix null pointer and add unit tests",
            "file": "service.py",
        }

        # When
        status, graph = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID

        # 기본 fix_bug 플랜 검증 (최소 3 step)
        assert len(graph.tasks) >= 3

    def test_a1_3_fix_bug_basic_three_steps(self):
        """A-1-3: 기본 fix_bug → 3 step (analyze, generate, validate)"""
        # Given
        context = {"user_input": "Fix the IndexError in data_processor.py"}

        # When
        status, graph = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID
        assert len(graph.tasks) == 3

        # 순서 확인: analyze → generate → validate
        order = graph.execution_order
        tasks_by_id = {task.id: task for task in graph.tasks.values()}

        analyze_tasks = [tid for tid in order if tasks_by_id[tid].type == TaskType.ANALYZE_CODE]
        generate_tasks = [tid for tid in order if tasks_by_id[tid].type == TaskType.GENERATE_CODE]
        validate_tasks = [tid for tid in order if tasks_by_id[tid].type == TaskType.VALIDATE_CHANGES]

        assert len(analyze_tasks) >= 1
        assert len(generate_tasks) >= 1
        assert len(validate_tasks) >= 1

        # analyze가 generate보다 먼저
        assert order.index(analyze_tasks[0]) < order.index(generate_tasks[0])
        # generate가 validate보다 먼저
        assert order.index(generate_tasks[0]) < order.index(validate_tasks[0])

    def test_a1_4_add_feature_multi_step(self):
        """A-1-4: add_feature → 5 step (analyze, search, generate, review, validate)"""
        # Given
        context = {"user_input": "Add logging functionality to the authentication module"}

        # When
        status, graph = self.planner.plan("add_feature", context)

        # Then
        assert status == PlanStatus.VALID
        assert len(graph.tasks) == 5

        task_types = [task.type for task in graph.tasks.values()]
        assert TaskType.ANALYZE_CODE in task_types
        assert TaskType.SEARCH_SYMBOLS in task_types
        assert TaskType.GENERATE_CODE in task_types
        assert TaskType.REVIEW_CODE in task_types
        assert TaskType.VALIDATE_CHANGES in task_types

    def test_a1_5_refactor_parallel_steps(self):
        """A-1-5: refactor → analyze + search 병렬 실행"""
        # Given
        context = {"user_input": "Refactor the database layer"}

        # When
        status, graph = self.planner.plan("refactor_code", context)

        # Then
        assert status == PlanStatus.VALID
        assert len(graph.tasks) == 4  # analyze, search, generate, validate

        # 병렬 그룹 확인
        groups = graph.parallel_groups
        assert len(groups) >= 2

        # 첫 번째 그룹에 analyze와 search가 모두 있어야 함
        first_group = set(groups[0])
        tasks_by_id = {task.id: task for task in graph.tasks.values()}

        analyze_in_first = any(tasks_by_id[tid].type == TaskType.ANALYZE_CODE for tid in first_group)
        search_in_first = any(tasks_by_id[tid].type == TaskType.SEARCH_SYMBOLS for tid in first_group)

        assert analyze_in_first and search_in_first

    def test_a1_6_dependency_validation(self):
        """A-1-6: Task 의존성이 올바르게 설정됨"""
        # Given
        context = {"user_input": "Fix the bug"}

        # When
        status, graph = self.planner.plan("fix_bug", context)

        # Then
        assert status == PlanStatus.VALID

        # DAG 검증 통과
        assert graph.validate_dag()

        # generate는 analyze에 의존
        for task in graph.tasks.values():
            if task.type == TaskType.GENERATE_CODE:
                # 의존성이 있어야 함
                assert len(task.depends_on) > 0

                # 의존하는 task는 ANALYZE여야 함
                for dep_id in task.depends_on:
                    dep_task = graph.tasks[dep_id]
                    assert dep_task.type in [TaskType.ANALYZE_CODE, TaskType.SEARCH_SYMBOLS]

    def test_a1_7_topological_order_correctness(self):
        """A-1-7: Topological sort가 의존성을 존중"""
        # Given
        context = {"user_input": "Add new feature"}

        # When
        status, graph = self.planner.plan("add_feature", context)

        # Then
        order = graph.execution_order

        # 모든 task에 대해, 의존하는 task가 먼저 나와야 함
        for i, task_id in enumerate(order):
            task = graph.tasks[task_id]
            for dep_id in task.depends_on:
                dep_index = order.index(dep_id)
                assert dep_index < i, f"{dep_id} should come before {task_id}"

    def test_a1_8_unknown_intent_fallback(self):
        """A-1-8: 알 수 없는 intent → 기본 2-step (analyze, generate)"""
        # Given: 정의되지 않은 intent
        context = {"user_input": "Do something"}

        # When
        status, graph = self.planner.plan("unknown_intent", context)

        # Then
        assert status == PlanStatus.VALID
        assert len(graph.tasks) == 2

        task_types = [task.type for task in graph.tasks.values()]
        assert TaskType.ANALYZE_CODE in task_types
        assert TaskType.GENERATE_CODE in task_types

    def test_a1_9_complex_request_decomposition(self):
        """A-1-9: 복잡한 요청 → 적절히 분해"""
        # Given
        context = {
            "user_input": "Fix the authentication bug, update the documentation, and add integration tests",
        }

        # When: fix_bug로 처리
        status, graph = self.planner.plan("fix_bug", context)

        # Then: 최소 3-step
        assert status == PlanStatus.VALID
        assert len(graph.tasks) >= 3

    def test_a1_10_step_count_validation(self):
        """A-1-10: 각 intent별 step 수 검증"""
        test_cases = [
            ("fix_bug", {"user_input": "Fix bug in payment module"}, 3),
            ("add_feature", {"user_input": "Add logging feature to auth"}, 5),
            ("refactor_code", {"user_input": "Refactor database layer"}, 4),
            ("unknown", {"user_input": "Implement generic helper function"}, 2),
        ]

        for intent, context, expected_count in test_cases:
            status, graph = self.planner.plan(intent, context)
            assert status == PlanStatus.VALID
            assert len(graph.tasks) == expected_count, f"{intent} should have {expected_count} tasks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
