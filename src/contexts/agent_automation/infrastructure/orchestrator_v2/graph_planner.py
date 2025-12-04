"""
Graph-aware Planner - Code Graph 구조 기반 Task 분해

Impact Analysis와 Dependency Graph를 활용하여 지능적으로 task를 분해합니다.
"""

import uuid
from typing import TYPE_CHECKING

from src.contexts.agent_automation.infrastructure.orchestrator_v2.state import SubTask
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer
    from src.contexts.multi_index.infrastructure.graph.store import GraphStore

logger = get_logger(__name__)


class GraphAwarePlanner:
    """
    Graph-aware Task Planner.

    Code Graph 구조를 분석하여:
    1. 변경 영향도 파악 (Impact Analysis)
    2. 의존성 기반 작업 순서 결정
    3. 병렬 가능한 작업 식별
    """

    def __init__(
        self,
        impact_analyzer: "GraphImpactAnalyzer | None" = None,
        graph_store: "GraphStore | None" = None,
    ):
        """
        Args:
            impact_analyzer: Impact analyzer (optional)
            graph_store: Graph store (optional)
        """
        self.impact_analyzer = impact_analyzer
        self.graph_store = graph_store

    async def plan(
        self,
        user_request: str,
        repo_id: str,
        changed_files: list[str] | None = None,
    ) -> list[SubTask]:
        """
        Graph 기반 task 분해.

        Args:
            user_request: 사용자 요청
            repo_id: 저장소 ID
            changed_files: 변경 대상 파일 (optional)

        Returns:
            SubTask 리스트 (의존성 정보 포함)
        """
        logger.info(f"Planning with graph awareness: {user_request[:100]}")

        tasks = []

        # 1. 변경 대상 파일 분석
        if changed_files and self.impact_analyzer:
            tasks = await self._plan_with_impact_analysis(user_request, repo_id, changed_files)
        else:
            # Fallback: 휴리스틱 기반 분해
            tasks = self._plan_heuristic(user_request)

        logger.info(f"Planned {len(tasks)} tasks")
        return tasks

    async def _plan_with_impact_analysis(
        self,
        user_request: str,
        repo_id: str,
        changed_files: list[str],
    ) -> list[SubTask]:
        """
        Impact Analysis 기반 planning.

        Args:
            user_request: 사용자 요청
            repo_id: 저장소 ID
            changed_files: 변경 대상 파일

        Returns:
            SubTask 리스트
        """
        tasks = []

        # 1. 영향 받는 파일 분석
        if self.impact_analyzer:
            try:
                impact_result = await self.impact_analyzer.analyze_impact(
                    changed_symbols=[],  # 파일 수준 분석
                    repo_id=repo_id,
                )

                affected_files = impact_result.get("affected_files", [])
                logger.info(f"Impact analysis: {len(affected_files)} affected files")

            except Exception as e:
                logger.warning(f"Impact analysis failed: {e}")
                affected_files = []
        else:
            affected_files = []

        # 2. 변경 파일 → Task
        for file in changed_files:
            task_id = f"task-{uuid.uuid4().hex[:8]}"
            tasks.append(
                SubTask(
                    task_id=task_id,
                    description=f"Modify {file}",
                    file_paths=[file],
                    dependencies=[],
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "primary_change"},
                )
            )

        # 3. 영향 받는 파일 → Task (의존성 포함)
        primary_task_ids = [t["task_id"] for t in tasks]

        for file in affected_files[:10]:  # 최대 10개로 제한
            if file not in changed_files:
                task_id = f"task-{uuid.uuid4().hex[:8]}"
                tasks.append(
                    SubTask(
                        task_id=task_id,
                        description=f"Update dependent file {file}",
                        file_paths=[file],
                        dependencies=primary_task_ids,  # Primary 변경 후 실행
                        status="pending",
                        result=None,
                        error=None,
                        metadata={"type": "dependent_update"},
                    )
                )

        # 4. 테스트 추가
        if "test" in user_request.lower() or any("test" in f for f in changed_files):
            test_task_id = f"task-{uuid.uuid4().hex[:8]}"
            all_task_ids = [t["task_id"] for t in tasks]
            tasks.append(
                SubTask(
                    task_id=test_task_id,
                    description="Run tests",
                    file_paths=[],
                    dependencies=all_task_ids,  # 모든 변경 후 테스트
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "test"},
                )
            )

        return tasks

    def _plan_heuristic(self, user_request: str) -> list[SubTask]:
        """
        휴리스틱 기반 planning (fallback).

        Args:
            user_request: 사용자 요청

        Returns:
            SubTask 리스트
        """
        tasks = []
        request_lower = user_request.lower()

        # 1. Implementation task
        if any(keyword in request_lower for keyword in ["implement", "add", "create"]):
            tasks.append(
                SubTask(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    description=f"Implementation: {user_request}",
                    file_paths=[],
                    dependencies=[],
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "implementation"},
                )
            )

        # 2. Refactor task
        if "refactor" in request_lower:
            tasks.append(
                SubTask(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    description=f"Refactor: {user_request}",
                    file_paths=[],
                    dependencies=[],
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "refactor"},
                )
            )

        # 3. Test task
        if "test" in request_lower:
            impl_task_id = tasks[0]["task_id"] if tasks else None
            tasks.append(
                SubTask(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    description=f"Tests: {user_request}",
                    file_paths=[],
                    dependencies=[impl_task_id] if impl_task_id else [],
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "test"},
                )
            )

        # 4. Documentation task
        if "document" in request_lower or "doc" in request_lower:
            all_task_ids = [t["task_id"] for t in tasks]
            tasks.append(
                SubTask(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    description=f"Documentation: {user_request}",
                    file_paths=[],
                    dependencies=all_task_ids,
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "documentation"},
                )
            )

        # Fallback: 최소 1개 task
        if not tasks:
            tasks.append(
                SubTask(
                    task_id=f"task-{uuid.uuid4().hex[:8]}",
                    description=user_request,
                    file_paths=[],
                    dependencies=[],
                    status="pending",
                    result=None,
                    error=None,
                    metadata={"type": "generic"},
                )
            )

        return tasks

    async def _get_dependencies(
        self,
        file_path: str,
        repo_id: str,
    ) -> list[str]:
        """
        파일의 의존성 가져오기.

        Args:
            file_path: 파일 경로
            repo_id: 저장소 ID

        Returns:
            의존하는 파일 경로 리스트
        """
        if not self.graph_store:
            return []

        try:
            # Graph에서 import 관계 조회
            # 실제 구현은 GraphStore API에 따라 달라짐
            dependencies = await self.graph_store.get_file_dependencies(
                file_path=file_path,
                repo_id=repo_id,
            )
            return dependencies

        except Exception as e:
            logger.warning(f"Failed to get dependencies for {file_path}: {e}")
            return []

    def topological_sort(self, tasks: list[SubTask]) -> list[SubTask]:
        """
        의존성 기반 topological sort.

        Args:
            tasks: SubTask 리스트

        Returns:
            정렬된 SubTask 리스트
        """
        # Kahn's algorithm
        task_map = {t["task_id"]: t for t in tasks}
        in_degree = {t["task_id"]: 0 for t in tasks}

        # In-degree 계산
        for task in tasks:
            for dep in task["dependencies"]:
                if dep in in_degree:
                    in_degree[task["task_id"]] += 1

        # In-degree 0인 노드부터 처리
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        sorted_tasks = []

        while queue:
            tid = queue.pop(0)
            sorted_tasks.append(task_map[tid])

            # 의존하는 노드의 in-degree 감소
            for task in tasks:
                if tid in task["dependencies"]:
                    in_degree[task["task_id"]] -= 1
                    if in_degree[task["task_id"]] == 0:
                        queue.append(task["task_id"])

        # 순환 의존성 체크
        if len(sorted_tasks) != len(tasks):
            logger.warning("Circular dependency detected in tasks")
            return tasks  # Fallback

        return sorted_tasks
