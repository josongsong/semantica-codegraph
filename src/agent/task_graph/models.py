"""Task Graph 모델

ADR-004: Task Decomposition Graph
- DAG (Directed Acyclic Graph) 구조
- Task 의존성 관리
- Parallel execution planning

설계 원칙:
1. Task는 독립적으로 실행 가능해야 함
2. 의존성은 명시적이어야 함
3. Cycle 없음 (DAG 보장)
4. Parallel execution 지원
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(Enum):
    """Task 유형"""

    ANALYZE_CODE = "analyze_code"  # 코드 분석
    SEARCH_SYMBOLS = "search_symbols"  # 심볼 검색
    GET_CONTEXT = "get_context"  # 컨텍스트 수집
    GENERATE_CODE = "generate_code"  # 코드 생성
    REVIEW_CODE = "review_code"  # 코드 리뷰
    RUN_TESTS = "run_tests"  # 테스트 실행
    VALIDATE_CHANGES = "validate_changes"  # 변경사항 검증


class TaskStatus(Enum):
    """Task 실행 상태"""

    PENDING = "pending"  # 대기 중
    READY = "ready"  # 실행 가능 (의존성 충족)
    RUNNING = "running"  # 실행 중
    COMPLETED = "completed"  # 완료
    FAILED = "failed"  # 실패
    CANCELLED = "cancelled"  # 취소됨


@dataclass
class Task:
    """
    단일 작업 단위

    Attributes:
        id: Task 고유 ID
        type: Task 유형
        description: 설명
        depends_on: 의존하는 Task ID 리스트
        status: 현재 상태
        input_data: 입력 데이터
        output_data: 출력 데이터 (실행 후)
        error: 에러 메시지 (실패 시)
        metadata: 추가 메타데이터
    """

    id: str
    type: TaskType
    description: str
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """검증"""
        # 자기 자신에게 의존 불가
        if self.id in self.depends_on:
            raise ValueError(f"Task {self.id} cannot depend on itself")

    def is_ready(self, completed_tasks: set[str]) -> bool:
        """
        실행 가능한지 확인

        Args:
            completed_tasks: 완료된 Task ID 집합

        Returns:
            모든 의존성이 충족되면 True
        """
        if self.status != TaskStatus.PENDING:
            return False

        # 모든 의존 Task가 완료되었는지 확인
        return all(dep_id in completed_tasks for dep_id in self.depends_on)

    def can_run_parallel_with(self, other: "Task") -> bool:
        """
        다른 Task와 병렬 실행 가능한지 확인

        Args:
            other: 다른 Task

        Returns:
            병렬 실행 가능하면 True
        """
        # 서로 의존하지 않으면 병렬 실행 가능
        return self.id not in other.depends_on and other.id not in self.depends_on


@dataclass
class TaskGraph:
    """
    Task DAG

    Attributes:
        tasks: Task ID -> Task 매핑
        execution_order: 실행 순서 (topological sort 결과)
        parallel_groups: 병렬 실행 가능한 Task 그룹
    """

    tasks: dict[str, Task] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """
        Task 추가

        Args:
            task: 추가할 Task

        Raises:
            ValueError: 중복 ID 또는 의존성 오류
        """
        if task.id in self.tasks:
            raise ValueError(f"Task {task.id} already exists")

        # 의존 Task가 존재하는지 확인
        for dep_id in task.depends_on:
            if dep_id not in self.tasks:
                raise ValueError(f"Dependency {dep_id} does not exist for task {task.id}")

        self.tasks[task.id] = task

    def validate_dag(self) -> bool:
        """
        DAG 검증 (Cycle 체크)

        Returns:
            Cycle이 없으면 True

        Raises:
            ValueError: Cycle이 발견되면
        """
        # DFS로 Cycle 체크
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            task = self.tasks[task_id]
            for dep_id in task.depends_on:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(task_id)
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    raise ValueError("Cycle detected in task graph")

        return True

    def topological_sort(self) -> list[str]:
        """
        Topological Sort (실행 순서 결정)

        Returns:
            실행 순서 (Task ID 리스트)
        """
        # Kahn's algorithm
        in_degree = dict.fromkeys(self.tasks, 0)

        # 각 Task의 in-degree 계산
        # task가 depends_on에 dep_id가 있으면, task의 in-degree 증가
        for task_id, task in self.tasks.items():
            in_degree[task_id] = len(task.depends_on)

        # In-degree가 0인 Task부터 시작
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # In-degree가 0인 Task 처리
            current = queue.pop(0)
            result.append(current)

            # 현재 Task에 의존하는 Task들의 in-degree 감소
            for task_id, task in self.tasks.items():
                if current in task.depends_on:
                    in_degree[task_id] -= 1
                    if in_degree[task_id] == 0:
                        queue.append(task_id)

        # 모든 Task가 처리되었는지 확인
        if len(result) != len(self.tasks):
            raise ValueError("Graph has a cycle")

        self.execution_order = result
        return result

    def get_parallel_groups(self) -> list[list[str]]:
        """
        병렬 실행 가능한 Task 그룹 계산

        Returns:
            [[task1, task2], [task3], ...] 형태의 병렬 그룹
        """
        if not self.execution_order:
            self.topological_sort()

        groups = []
        completed = set()
        remaining = set(self.execution_order)

        while remaining:
            # 현재 실행 가능한 Task 찾기
            ready = []
            for task_id in remaining:
                task = self.tasks[task_id]
                if task.is_ready(completed):
                    ready.append(task_id)

            if not ready:
                # 더 이상 실행 가능한 Task가 없으면 종료
                break

            # 현재 그룹에 추가
            groups.append(ready)

            # 완료 처리
            for task_id in ready:
                completed.add(task_id)
                remaining.remove(task_id)

        self.parallel_groups = groups
        return groups

    def get_ready_tasks(self, completed_tasks: set[str]) -> list[Task]:
        """
        현재 실행 가능한 Task 목록

        Args:
            completed_tasks: 완료된 Task ID 집합

        Returns:
            실행 가능한 Task 리스트
        """
        ready = []
        for task in self.tasks.values():
            if task.is_ready(completed_tasks):
                ready.append(task)
        return ready

    def get_task_depth(self, task_id: str) -> int:
        """
        Task의 depth (최장 의존 경로 길이)

        Args:
            task_id: Task ID

        Returns:
            Depth (0부터 시작)
        """
        task = self.tasks[task_id]
        if not task.depends_on:
            return 0

        max_depth = 0
        for dep_id in task.depends_on:
            depth = self.get_task_depth(dep_id)
            max_depth = max(max_depth, depth + 1)

        return max_depth
