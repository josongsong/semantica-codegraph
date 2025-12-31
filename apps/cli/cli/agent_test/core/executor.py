"""Agent 실행 래퍼 (Production-Ready)."""

import traceback
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from rich.console import Console

from apps.orchestrator.orchestrator.domain.models import AgentTask
from apps.orchestrator.orchestrator.orchestrator.fast_path_orchestrator import FastPathRequest as AgentRequest
from apps.orchestrator.orchestrator.orchestrator.fast_path_orchestrator import FastPathResponse as AgentResponse
from src.cli.agent_test.core.models import (
    ExecutionEvent,
    StepStatus,
)
from codegraph_shared.container import container

console = Console()


class AgentExecutor:
    """Agent 실행을 관리하는 래퍼 클래스."""

    def __init__(self, repo_path: Path, orchestrator=None):
        """
        Initialize executor.

        Args:
            repo_path: 저장소 경로
            orchestrator: Agent orchestrator (테스트 시 mock 주입 가능)

        Raises:
            ValueError: repo_path가 유효하지 않을 때
        """
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        self.repo_path = repo_path
        self.orchestrator = orchestrator or getattr(container, "v7_agent_orchestrator", None)

        if self.orchestrator is None:
            raise RuntimeError("Orchestrator is not available in container")

    async def execute_streaming(
        self,
        instructions: str,
        on_event: Callable[[ExecutionEvent], None] | None = None,
    ) -> AsyncIterator[ExecutionEvent]:
        """
        Agent를 실행하고 이벤트를 스트리밍.

        Args:
            instructions: 작업 지시사항
            on_event: 이벤트 콜백 (선택)

        Yields:
            ExecutionEvent: 실행 중 발생하는 이벤트
        """
        # 시작 이벤트
        event = ExecutionEvent.execution_start(
            instructions=instructions,
            repo=str(self.repo_path),
        )
        if on_event:
            on_event(event)
        yield event

        try:
            # Agent 요청 생성 (실제 구현)
            # Snapshot ID는 외부에서 주입받아야 함
            raise NotImplementedError(
                "AgentExecutor.execute_streaming() requires snapshot_id parameter. "
                "Use execute_with_snapshot() instead or create snapshot first:\n"
                "  agent-test snapshot create <repo>\n"
                "  agent-test run execute <task> --snapshot <snapshot_id>"
            )

            # 단계 시작 이벤트
            event = ExecutionEvent.step_start(
                step="planning",
                message="작업 계획 수립 중...",
            )
            if on_event:
                on_event(event)
            yield event

            # Agent 실행 (async)
            # response: AgentResponse = await self.orchestrator.execute(request)

            # 단계 완료 이벤트
            event = ExecutionEvent.step_end(
                step="planning",
                status=StepStatus.SUCCESS,
            )
            if on_event:
                on_event(event)
            yield event

            # 완료 이벤트
            # event = ExecutionEvent.execution_complete(
            #     status="success" if response.success else "failed",
            #     message=response.workflow_result.summary if response.workflow_result else "완료",
            #     files_changed=len(response.workflow_result.changes) if response.workflow_result and response.workflow_result.changes else 0,
            # )
            # if on_event:
            #     on_event(event)
            # yield event

        except NotImplementedError:
            # 구현 필요한 부분 - 명시적으로 재발생
            raise
        except ValueError as e:
            # 입력 검증 에러
            event = ExecutionEvent.error(e, traceback=traceback.format_exc())
            if on_event:
                on_event(event)
            yield event
            raise
        except Exception as e:
            # 예상치 못한 에러
            console.print(f"[red]Unexpected error: {e}[/red]")
            event = ExecutionEvent.error(e, traceback=traceback.format_exc())
            if on_event:
                on_event(event)
            yield event
            raise

    async def execute(self, instructions: str) -> AgentResponse:
        """
        Agent를 실행 (async).

        Args:
            instructions: 작업 지시사항

        Returns:
            AgentResponse: 실행 결과
        """
        task = AgentTask(
            task_id=f"test_{uuid.uuid4().hex[:8]}",
            description=instructions,
            repo_id=str(self.repo_path),
            snapshot_id="test_snapshot",
            context_files=[],
        )
        request = AgentRequest(task=task, config={})

        return await self.orchestrator.execute(request)

    async def execute_with_snapshot(
        self,
        instructions: str,
        snapshot_id: str,
        retriever_type: str = "basic",
    ) -> AgentResponse:
        """
        Agent를 스냅샷과 함께 실행 (Production-Ready with Schema Validation).

        Args:
            instructions: 작업 지시사항
            snapshot_id: 스냅샷 ID
            retriever_type: Retriever 타입

        Returns:
            AgentResponse: 실행 결과

        Raises:
            ValueError: 입력 검증 실패 시
        """
        from codegraph_engine.analysis_indexing.domain.value_objects.snapshot_id import SnapshotId

        # 1. Instructions 검증
        if not instructions or not instructions.strip():
            raise ValueError("Instructions cannot be empty")

        instructions = instructions.strip()
        if len(instructions) > 10000:
            raise ValueError(f"Instructions too long: {len(instructions)} chars (max 10000)")

        # 2. Snapshot ID 검증
        try:
            snapshot = SnapshotId.from_string(snapshot_id)
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Invalid snapshot ID format: {snapshot_id}\n"
                f"Expected: UUID format (e.g., '738bca69-b519-4b34-87b7-d36ec3915061')\n"
                f"Error: {e}"
            ) from e

        # 3. Retriever 타입 검증
        valid_retrievers = {"basic", "v3", "multi_hop", "reasoning"}
        if retriever_type not in valid_retrievers:
            raise ValueError(
                f"Invalid retriever type: '{retriever_type}'\nValid types: {', '.join(sorted(valid_retrievers))}"
            )

        # 4. Repo path 검증
        if not self.repo_path.is_absolute():
            repo_id = str(self.repo_path.absolute())
        else:
            repo_id = str(self.repo_path)

        # 5. AgentTask 생성 (모든 필드 타입 검증됨)
        task = AgentTask(
            task_id=f"cli_{uuid.uuid4().hex[:8]}",
            description=instructions,
            repo_id=repo_id,
            snapshot_id=snapshot,
            context_files=[],
        )

        # 6. AgentRequest 생성
        request = AgentRequest(task=task, config={"retriever": retriever_type})

        # 7. 실행
        return await self.orchestrator.execute(request)
