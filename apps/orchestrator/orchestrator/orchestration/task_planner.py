"""Task Graph Planner

ADR-004: Task Decomposition Graph

책임:
1. User request → Task 분해
2. Task 의존성 분석
3. 실행 계획 생성 (순차/병렬)
"""

from typing import Any

from .models import PlanStatus, RiskLevel, Task, TaskGraph, TaskType


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

    # 위험 키워드 패턴
    DANGEROUS_PATTERNS = [
        "drop",
        "delete",
        "remove",
        "truncate",
        "destroy",
        "production",
        "prod",
        "live",
        "rm -rf",
        "format",
        "wipe",
    ]

    def assess_risk(self, user_intent: str, context: dict[str, Any]) -> tuple[RiskLevel, str]:
        """
        요청의 위험도 평가

        Args:
            user_intent: 사용자 의도
            context: 컨텍스트

        Returns:
            (위험도, 이유)
        """
        user_input = context.get("user_input", "").lower()
        combined = f"{user_intent} {user_input}".lower()

        # CRITICAL: 프로덕션 DB drop 등
        critical_db_ops = ["drop database", "drop table", "truncate table", "drop prod"]
        prod_keywords = ["production", "prod", "live"]

        has_critical_op = any(op in combined for op in critical_db_ops)
        has_prod_keyword = any(kw in combined for kw in prod_keywords)

        if has_critical_op and has_prod_keyword:
            return RiskLevel.CRITICAL, "Production database modification detected"

        # CRITICAL: 여러 위험 패턴 동시 (production + delete)
        if has_prod_keyword and "delete" in combined:
            return RiskLevel.CRITICAL, "Production data deletion detected"

        # HIGH: 삭제 작업
        if any(word in combined for word in ["delete all", "remove all", "rm -rf"]):
            return RiskLevel.HIGH, "Bulk deletion detected"

        # MEDIUM: 대규모 변경
        if "files_count" in context and context["files_count"] > 10:
            return RiskLevel.MEDIUM, "Large-scale changes (>10 files)"

        return RiskLevel.SAFE, "Normal operation"

    def needs_clarification(self, user_intent: str, context: dict[str, Any]) -> tuple[bool, str]:
        """
        명확화 필요 여부

        Args:
            user_intent: 사용자 의도
            context: 컨텍스트

        Returns:
            (필요 여부, 질문)
        """
        user_input = context.get("user_input", "").strip()

        # 너무 짧거나 모호한 요청
        if len(user_input) < 10:
            return True, "Could you provide more details about what needs to be fixed?"

        # "이상함", "문제" 같은 모호한 표현
        vague_words = ["이상", "문제", "안됨", "weird", "issue", "problem", "broken"]
        if any(word in user_input.lower() for word in vague_words):
            # 구체적 정보가 없으면
            if "file" not in context and "function" not in context:
                return True, "Which file or function is causing the issue?"

        return False, ""

    def plan(self, user_intent: str, context: dict[str, Any]) -> tuple[PlanStatus, TaskGraph | str]:
        """
        User intent → Task Graph 생성 (안전성 체크 포함)

        Args:
            user_intent: 사용자 의도 (e.g., "fix_bug", "add_feature")
            context: 컨텍스트 정보

        Returns:
            (상태, TaskGraph 또는 질문/거부 메시지)
        """
        # 1. 명확화 필요 체크
        needs_clarify, question = self.needs_clarification(user_intent, context)
        if needs_clarify:
            return PlanStatus.NEEDS_CLARIFICATION, question

        # 2. 위험도 평가
        risk_level, risk_reason = self.assess_risk(user_intent, context)

        # CRITICAL은 즉시 거부
        if risk_level == RiskLevel.CRITICAL:
            return PlanStatus.REJECTED, f"Request rejected: {risk_reason}"

        # 3. Task Graph 생성
        if self.enable_llm_decomposition:
            graph = self._plan_with_llm(user_intent, context)
        else:
            graph = self._plan_with_rules(user_intent, context)

        # 4. 위험도를 그래프에 기록
        if risk_level != RiskLevel.SAFE:
            for task in graph.tasks.values():
                task.metadata["risk_level"] = risk_level
                task.metadata["risk_reason"] = risk_reason

        return PlanStatus.VALID, graph

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
