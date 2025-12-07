"""
LangGraph Workflow Adapter

IWorkflowEngine 포트 구현.

원칙:
- ❌ Node에 business logic 직접 작성 금지
- ✅ Node는 WorkflowStep.execute만 호출 (orchestration only)
- ✅ Domain Model ↔ DTO 변환만 담당
"""

import time
from typing import Any

from langgraph.graph import END, StateGraph

from src.agent.domain.models import WorkflowResult, WorkflowState
from src.agent.domain.workflow_step import WorkflowStep
from src.agent.dto.workflow_dto import (
    WorkflowStateDTO,
    dto_to_workflow_state,
    workflow_state_to_dto,
)
from src.ports import IWorkflowEngine


class LangGraphWorkflowAdapter(IWorkflowEngine):
    """
    LangGraph → IWorkflowEngine Adapter.

    LangGraph의 StateGraph를 사용하여 workflow orchestration 제공.
    Business logic은 WorkflowStep에 있고, 여기서는 orchestration만.
    """

    def __init__(self):
        """초기화"""
        self.graph: StateGraph | None = None
        self.steps: dict[str, WorkflowStep] = {}
        self.compiled_graph: Any = None

    def add_step(self, step: WorkflowStep, name: str) -> None:
        """
        WorkflowStep 등록.

        Args:
            step: WorkflowStep 인스턴스
            name: Step 이름 (node ID)
        """
        self.steps[name] = step

    async def execute(
        self,
        steps: list[WorkflowStep],
        initial_state: WorkflowState,
        config: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """
        Workflow 실행.

        Args:
            steps: WorkflowStep 리스트
            initial_state: 초기 상태 (Domain Model)
            config: 실행 설정 (max_iterations, early_exit 등)

        Returns:
            WorkflowResult (Domain Model)
        """
        config = config or {}
        start_time = time.time()

        # 1. Steps 등록
        for step in steps:
            self.add_step(step, step.name)

        # 2. StateGraph 생성
        self.graph = StateGraph(WorkflowStateDTO)
        self._build_graph()
        self.compiled_graph = self.graph.compile()

        # 3. Domain Model → DTO 변환
        initial_dto = workflow_state_to_dto(initial_state)

        # 4. LangGraph 실행
        try:
            final_dto = await self.compiled_graph.ainvoke(initial_dto)
        except Exception as e:
            # 실행 실패
            return WorkflowResult(
                success=False,
                final_state=initial_state,
                total_iterations=initial_state.iteration,
                total_time_seconds=time.time() - start_time,
                changes=[],
                test_results=[],
                errors=[str(e)],
            )

        # 5. DTO → Domain Model 변환
        final_state = dto_to_workflow_state(final_dto)

        # 6. WorkflowResult 생성
        success = final_state.should_exit_early() or len(final_state.errors) == 0

        return WorkflowResult(
            success=success,
            final_state=final_state,
            total_iterations=final_state.iteration,
            total_time_seconds=time.time() - start_time,
            changes=final_state.changes,
            test_results=final_state.test_results,
            errors=final_state.errors,
        )

    def _build_graph(self) -> None:
        """
        LangGraph StateGraph 구성.

        Workflow: Analyze → Plan → Generate → Critic → Test → Heal
        """
        assert self.graph is not None

        # Node 추가 (각 node는 WorkflowStep.execute만 호출)
        for name, step in self.steps.items():
            self.graph.add_node(name, self._create_node_wrapper(step))

        # Entry point
        self.graph.set_entry_point("analyze")

        # Edges 정의 (linear flow + conditional branching)
        self.graph.add_edge("analyze", "plan")
        self.graph.add_edge("plan", "generate")
        self.graph.add_edge("generate", "critic")

        # Conditional edges: critic → test/generate/END
        self.graph.add_conditional_edges(
            "critic",
            self._should_test,
            {
                "test": "test",
                "regenerate": "generate",
                "done": END,
            },
        )

        # Conditional edges: test → heal/plan/END
        self.graph.add_conditional_edges(
            "test",
            self._handle_test_result,
            {
                "heal": "heal",
                "replan": "plan",
                "done": END,
            },
        )

        # heal → generate (재시도)
        self.graph.add_edge("heal", "generate")

    def _create_node_wrapper(self, step: WorkflowStep):
        """
        Node wrapper 함수 생성.

        ❌ Business logic 직접 작성 금지
        ✅ WorkflowStep.execute만 호출

        Args:
            step: WorkflowStep 인스턴스

        Returns:
            LangGraph node 함수
        """

        async def node_func(state_dto: WorkflowStateDTO) -> WorkflowStateDTO:
            """
            LangGraph node 함수.

            역할:
            1. DTO → Domain Model 변환
            2. WorkflowStep.execute 호출 (여기가 진짜 비즈니스 로직)
            3. Domain Model → DTO 변환
            """
            # DTO → Domain Model
            state = dto_to_workflow_state(state_dto)

            # WorkflowStep 실행 (비즈니스 로직)
            updated_state = await step.execute(state)

            # Domain Model → DTO
            return workflow_state_to_dto(updated_state)

        return node_func

    def _should_test(self, state_dto: WorkflowStateDTO) -> str:
        """
        Critic 후 분기 결정.

        Returns:
            "test" | "regenerate" | "done"
        """
        # DTO → Domain Model
        state = dto_to_workflow_state(state_dto)

        # max_iterations 초과 → 강제 종료
        if state.iteration >= state.max_iterations:
            return "done"

        # 에러 있으면 재생성
        if state.errors:
            return "regenerate"

        # 코드 변경 없으면 종료
        if not state.changes:
            return "done"

        # 테스트로 진행
        return "test"

    def _handle_test_result(self, state_dto: WorkflowStateDTO) -> str:
        """
        Test 후 분기 결정.

        Returns:
            "heal" | "replan" | "done"
        """
        # DTO → Domain Model
        state = dto_to_workflow_state(state_dto)

        # max_iterations 초과 → 강제 종료
        if state.iteration >= state.max_iterations:
            return "done"

        # 테스트 성공
        if all(r.is_success() for r in state.test_results):
            return "done"

        # 재계획 필요
        if state.should_replan():
            return "replan"

        # 자가 치유
        return "heal"
