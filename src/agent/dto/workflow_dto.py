"""
Workflow DTO (Data Transfer Object)

LangGraph StateGraph에서 사용하는 직렬화 가능한 DTO.
❌ 비즈니스 로직 포함 금지
✅ Domain Model ↔ DTO 변환만 담당
"""

from typing import Any, TypedDict

from src.agent.domain.models import (
    AgentTask,
    CodeChange,
    ExecutionResult,
    WorkflowResult,
    WorkflowState,
)


class WorkflowStateDTO(TypedDict, total=False):
    """
    LangGraph StateGraph용 DTO.

    TypedDict 사용 이유:
    - LangGraph가 dict 기반으로 동작
    - 직렬화 용이
    - Type hint 지원
    """

    task_id: str
    description: str
    repo_id: str
    snapshot_id: str
    context_files: list[str]
    current_step: str
    changes: list[dict[str, Any]]
    test_results: list[dict[str, Any]]
    errors: list[str]
    iteration: int
    max_iterations: int
    metadata: dict[str, Any]
    started_at: str  # ISO format datetime string


class CodeChangeDTO(TypedDict, total=False):
    """CodeChange DTO"""

    file_path: str
    change_type: str
    original_lines: list[str]
    new_lines: list[str]
    start_line: int | None
    end_line: int | None
    rationale: str


class ExecutionResultDTO(TypedDict):
    """ExecutionResult DTO"""

    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int


class WorkflowResultDTO(TypedDict):
    """WorkflowResult DTO"""

    success: bool
    total_iterations: int
    total_time_seconds: float
    changes: list[CodeChangeDTO]
    test_results: list[ExecutionResultDTO]
    errors: list[str]


# ============================================================
# Domain Model ↔ DTO 변환 함수
# ============================================================


def workflow_state_to_dto(state: WorkflowState) -> WorkflowStateDTO:
    """Domain Model → DTO"""
    return WorkflowStateDTO(
        task_id=state.task.task_id,
        description=state.task.description,
        repo_id=state.task.repo_id,
        snapshot_id=state.task.snapshot_id,
        context_files=state.task.context_files,
        current_step=state.current_step.value,
        changes=[code_change_to_dto(c) for c in state.changes],
        test_results=[execution_result_to_dto(r) for r in state.test_results],
        errors=state.errors,
        iteration=state.iteration,
        max_iterations=state.max_iterations,
        metadata=state.metadata,
        started_at=state.started_at.isoformat(),
    )


def dto_to_workflow_state(dto: WorkflowStateDTO) -> WorkflowState:
    """DTO → Domain Model"""
    from datetime import datetime

    from src.agent.domain.models import WorkflowStepType

    task = AgentTask(
        task_id=dto["task_id"],
        description=dto["description"],
        repo_id=dto["repo_id"],
        snapshot_id=dto["snapshot_id"],
        context_files=dto.get("context_files", []),
    )

    # started_at 변환 (ISO format → datetime)
    started_at_str = dto.get("started_at")
    started_at = datetime.fromisoformat(started_at_str) if started_at_str else datetime.now()

    return WorkflowState(
        task=task,
        current_step=WorkflowStepType(dto["current_step"]),
        changes=[dto_to_code_change(c) for c in dto.get("changes", [])],
        test_results=[dto_to_execution_result(r) for r in dto.get("test_results", [])],
        errors=dto.get("errors", []),
        iteration=dto.get("iteration", 0),
        max_iterations=dto.get("max_iterations", 5),
        metadata=dto.get("metadata", {}),
        started_at=started_at,
    )


def code_change_to_dto(change: CodeChange) -> CodeChangeDTO:
    """CodeChange → DTO"""
    return CodeChangeDTO(
        file_path=change.file_path,
        change_type=change.change_type.value,
        original_lines=change.original_lines,
        new_lines=change.new_lines,
        start_line=change.start_line,
        end_line=change.end_line,
        rationale=change.rationale,
    )


def dto_to_code_change(dto: CodeChangeDTO) -> CodeChange:
    """DTO → CodeChange"""
    from src.agent.domain.models import ChangeType

    return CodeChange(
        file_path=dto["file_path"],
        change_type=ChangeType(dto["change_type"]),
        original_lines=dto.get("original_lines", []),
        new_lines=dto.get("new_lines", []),
        start_line=dto.get("start_line"),
        end_line=dto.get("end_line"),
        rationale=dto.get("rationale", ""),
    )


def execution_result_to_dto(result: ExecutionResult) -> ExecutionResultDTO:
    """ExecutionResult → DTO"""
    return ExecutionResultDTO(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        execution_time_ms=result.execution_time_ms,
    )


def dto_to_execution_result(dto: ExecutionResultDTO) -> ExecutionResult:
    """DTO → ExecutionResult"""
    return ExecutionResult(
        stdout=dto["stdout"],
        stderr=dto["stderr"],
        exit_code=dto["exit_code"],
        execution_time_ms=dto["execution_time_ms"],
    )


def workflow_result_to_dto(result: WorkflowResult) -> WorkflowResultDTO:
    """WorkflowResult → DTO"""
    return WorkflowResultDTO(
        success=result.success,
        total_iterations=result.total_iterations,
        total_time_seconds=result.total_time_seconds,
        changes=[code_change_to_dto(c) for c in result.changes],
        test_results=[execution_result_to_dto(r) for r in result.test_results],
        errors=result.errors,
    )
