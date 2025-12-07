"""Task Graph Planner

ADR-004: Task Decomposition Graph

책임:
1. User request → Task 분해
2. Task 의존성 분석
3. 실행 계획 생성 (순차/병렬)
"""

from typing import Any

from .models import Task, TaskGraph, TaskType


class TaskGraphPlanner:
    """
    Task Graph 생성 및 실행 계획 수립

    Phase 0: 간단한 분해 (fix_bug → analyze + generate + validate)
    Phase 1: LLM 기반 복잡한 분해
    """

    def __init__(self, enable_llm_decomposition: bool = False):
        """
        Args:
            enable_llm_decomposition: LLM 기반 분해 활성화 (Phase 1)
        """
        self.enable_llm_decomposition = enable_llm_decomposition

    def plan(self, user_intent: str, context: dict[str, Any]) -> TaskGraph:
        """
        User intent → Task Graph 생성

        Args:
            user_intent: 사용자 의도 (e.g., "fix_bug", "add_feature")
            context: 컨텍스트 정보

        Returns:
            실행 가능한 TaskGraph
        """
        if self.enable_llm_decomposition:
            # Phase 1: LLM 기반 분해
            return self._plan_with_llm(user_intent, context)
        else:
            # Phase 0: 규칙 기반 분해
            return self._plan_with_rules(user_intent, context)

    def _plan_with_rules(self, user_intent: str, context: dict[str, Any]) -> TaskGraph:
        """
        규칙 기반 Task 분해 (Phase 0)

        Intent별 고정된 Task 그래프 생성
        """
        graph = TaskGraph()

        # Intent에 따라 Task 생성
        if user_intent == "fix_bug":
            # fix_bug: analyze → generate → validate

            task_analyze = Task(
                id="task_analyze_bug",
                type=TaskType.ANALYZE_CODE,
                description="Analyze code to find bug location",
                depends_on=[],
                input_data={
                    "query": context.get("user_input", ""),
                    "repo_id": context.get("repo_id", ""),
                },
            )

            task_generate = Task(
                id="task_generate_fix",
                type=TaskType.GENERATE_CODE,
                description="Generate bug fix code",
                depends_on=["task_analyze_bug"],
                input_data={},
            )

            task_validate = Task(
                id="task_validate_fix",
                type=TaskType.VALIDATE_CHANGES,
                description="Validate the bug fix",
                depends_on=["task_generate_fix"],
                input_data={},
            )

            graph.add_task(task_analyze)
            graph.add_task(task_generate)
            graph.add_task(task_validate)

        elif user_intent == "add_feature":
            # add_feature: analyze → search_symbols → generate → review → validate

            task_analyze = Task(
                id="task_analyze_requirements",
                type=TaskType.ANALYZE_CODE,
                description="Analyze feature requirements",
                depends_on=[],
                input_data={
                    "query": context.get("user_input", ""),
                },
            )

            task_search = Task(
                id="task_search_related_code",
                type=TaskType.SEARCH_SYMBOLS,
                description="Search for related code and symbols",
                depends_on=["task_analyze_requirements"],
                input_data={},
            )

            task_generate = Task(
                id="task_generate_feature",
                type=TaskType.GENERATE_CODE,
                description="Generate new feature code",
                depends_on=["task_search_related_code"],
                input_data={},
            )

            task_review = Task(
                id="task_review_feature",
                type=TaskType.REVIEW_CODE,
                description="Review generated feature code",
                depends_on=["task_generate_feature"],
                input_data={},
            )

            task_validate = Task(
                id="task_validate_feature",
                type=TaskType.VALIDATE_CHANGES,
                description="Validate feature implementation",
                depends_on=["task_review_feature"],
                input_data={},
            )

            graph.add_task(task_analyze)
            graph.add_task(task_search)
            graph.add_task(task_generate)
            graph.add_task(task_review)
            graph.add_task(task_validate)

        elif user_intent == "refactor_code":
            # refactor: analyze + search_symbols (병렬) → generate → validate

            task_analyze = Task(
                id="task_analyze_refactor_target",
                type=TaskType.ANALYZE_CODE,
                description="Analyze code to be refactored",
                depends_on=[],
                input_data={
                    "query": context.get("user_input", ""),
                },
            )

            task_search = Task(
                id="task_search_dependencies",
                type=TaskType.SEARCH_SYMBOLS,
                description="Search for code dependencies",
                depends_on=[],  # analyze와 병렬 실행 가능
                input_data={
                    "query": context.get("user_input", ""),
                },
            )

            task_generate = Task(
                id="task_generate_refactored_code",
                type=TaskType.GENERATE_CODE,
                description="Generate refactored code",
                depends_on=["task_analyze_refactor_target", "task_search_dependencies"],
                input_data={},
            )

            task_validate = Task(
                id="task_validate_refactoring",
                type=TaskType.VALIDATE_CHANGES,
                description="Validate refactoring",
                depends_on=["task_generate_refactored_code"],
                input_data={},
            )

            graph.add_task(task_analyze)
            graph.add_task(task_search)
            graph.add_task(task_generate)
            graph.add_task(task_validate)

        else:
            # 기본: analyze → generate
            task_analyze = Task(
                id="task_analyze_generic",
                type=TaskType.ANALYZE_CODE,
                description="Analyze code",
                depends_on=[],
                input_data={
                    "query": context.get("user_input", ""),
                },
            )

            task_generate = Task(
                id="task_generate_generic",
                type=TaskType.GENERATE_CODE,
                description="Generate code",
                depends_on=["task_analyze_generic"],
                input_data={},
            )

            graph.add_task(task_analyze)
            graph.add_task(task_generate)

        # DAG 검증
        graph.validate_dag()

        # 실행 순서 계산
        graph.topological_sort()

        # 병렬 그룹 계산
        graph.get_parallel_groups()

        return graph

    def _plan_with_llm(self, user_intent: str, context: dict[str, Any]) -> TaskGraph:
        """
        LLM 기반 Task 분해 (Phase 1)

        LLM이 user_intent를 분석하여 동적으로 Task 생성
        """
        # Phase 1: LLM 호출하여 Task 생성
        # 현재는 규칙 기반으로 fallback
        return self._plan_with_rules(user_intent, context)

    def optimize_parallel_execution(self, graph: TaskGraph) -> TaskGraph:
        """
        병렬 실행 최적화

        Args:
            graph: 원본 TaskGraph

        Returns:
            최적화된 TaskGraph
        """
        # Phase 0: 단순히 병렬 그룹만 재계산
        graph.get_parallel_groups()
        return graph

    def estimate_execution_time(self, graph: TaskGraph) -> float:
        """
        예상 실행 시간 계산

        Args:
            graph: TaskGraph

        Returns:
            예상 시간 (초)
        """
        # Phase 0: 단순 계산 (각 Task 1초 가정)
        # 병렬 그룹 수 = 최소 시간
        if not graph.parallel_groups:
            graph.get_parallel_groups()

        # 각 그룹은 1초 (병렬 실행)
        return len(graph.parallel_groups)
