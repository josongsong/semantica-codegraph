"""
Agent Orchestrator

전체 Agent workflow를 조율하는 Orchestrator.

역할:
- Port만 의존 (Adapter 몰라도 됨)
- WorkflowSteps 생성 및 실행
- 전체 흐름 관리
"""

from dataclasses import dataclass

from src.agent.domain.models import AgentTask, WorkflowResult, WorkflowState, WorkflowStepType
from src.agent.domain.real_services import (
    RealAnalyzeService,
    RealCriticService,
    RealGenerateService,
    RealHealService,
    RealPlanService,
    RealTestService,
)
from src.agent.domain.workflow_step import (
    AnalyzeStep,
    CriticStep,
    GenerateStep,
    HealStep,
    PlanStep,
    TestStep,
)
from src.ports import (
    IGuardrailValidator,
    ILLMProvider,
    ISandboxExecutor,
    IVCSApplier,
    IWorkflowEngine,
)


@dataclass
class AgentRequest:
    """Agent 실행 요청"""

    task: AgentTask
    config: dict | None = None


@dataclass
class AgentResponse:
    """Agent 실행 응답"""

    success: bool
    workflow_result: WorkflowResult
    commit_sha: str | None = None
    validation_result: dict | None = None


class AgentOrchestrator:
    """
    Agent Orchestrator.

    Port만 의존하여 Adapter 교체 가능.
    """

    def __init__(
        self,
        workflow_engine: IWorkflowEngine,
        llm_provider: ILLMProvider,
        sandbox_executor: ISandboxExecutor,
        guardrail_validator: IGuardrailValidator,
        vcs_applier: IVCSApplier,
        # 기존 시스템 통합
        retriever_service=None,  # 검색 서비스
        chunk_store=None,  # 코드 분석
        memory_system=None,  # 세션 메모리
        # Incremental Execution
        incremental_workflow=None,  # Incremental Workflow Manager
        # Human-in-the-Loop (SOTA)
        approval_manager=None,  # Approval Manager
        diff_manager=None,  # Diff Manager
        partial_committer=None,  # Partial Committer
    ):
        """
        Args:
            workflow_engine: Workflow orchestration (LangGraph, etc.)
            llm_provider: LLM provider (LiteLLM, etc.)
            sandbox_executor: Sandbox executor (E2B, Local, etc.)
            guardrail_validator: Guardrail validator (Guardrails AI, Pydantic, etc.)
            vcs_applier: VCS applier (GitPython, etc.)
            retriever_service: Retrieval/search service (optional)
            chunk_store: Chunk storage for code analysis (optional)
            memory_system: Session memory system (optional)
            incremental_workflow: Incremental workflow manager (optional)
            approval_manager: Approval manager for human-in-the-loop (optional)
            diff_manager: Diff manager for patch generation (optional)
            partial_committer: Partial committer for selective apply (optional)
        """
        # Public 속성 (검증/테스트용)
        self.workflow_engine = workflow_engine
        self.llm_provider = llm_provider
        self.sandbox_executor = sandbox_executor
        self.guardrail_validator = guardrail_validator
        self.vcs_applier = vcs_applier

        # 기존 시스템 통합
        self.retriever_service = retriever_service
        self.chunk_store = chunk_store
        self.memory_system = memory_system

        # Incremental Execution
        self.incremental_workflow = incremental_workflow

        # Human-in-the-Loop (SOTA)
        self.approval_manager = approval_manager
        self.diff_manager = diff_manager
        self.partial_committer = partial_committer

        # 내부 사용 (간결성)
        self.llm = llm_provider
        self.sandbox = sandbox_executor
        self.guardrail = guardrail_validator
        self.vcs = vcs_applier

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Agent 실행.

        Args:
            request: Agent 실행 요청

        Returns:
            Agent 실행 응답
        """
        # 1. WorkflowSteps 생성 (Port 기반 Services 주입)
        steps = await self._create_workflow_steps()

        # 2. 초기 상태
        initial_state = WorkflowState(
            task=request.task,
            current_step=WorkflowStepType.ANALYZE,
            max_iterations=request.config.get("max_iterations", 5) if request.config else 5,
        )

        # 3. Workflow 실행
        workflow_result = await self.workflow_engine.execute(steps, initial_state, request.config)

        # 4. Guardrail 검증
        validation_result = None
        if workflow_result.changes:
            validation = await self.guardrail.validate(workflow_result.changes, "code_quality")
            validation_result = {
                "valid": validation.valid,
                "errors": validation.errors,
            }

        # 5. VCS 적용 (성공 시)
        commit_sha = None
        if workflow_result.success and validation_result and validation_result["valid"]:
            commit_result = await self.vcs.apply_changes(
                repo_path=".",
                changes=workflow_result.changes,
                branch_name=f"agent/{request.task.task_id}",
            )
            commit_sha = commit_result.commit_sha

        return AgentResponse(
            success=workflow_result.success,
            workflow_result=workflow_result,
            commit_sha=commit_sha,
            validation_result=validation_result,
        )

    async def _create_workflow_steps(self) -> list:
        """
        WorkflowSteps 생성 (Port 기반 Services 주입).

        Real LLM 기반 Services 사용 + 기존 시스템 통합.
        """
        # Real Services (LLM 기반) + 기존 시스템
        analyze_service = RealAnalyzeService(
            self.llm,
            retriever_service=self.retriever_service,  # 검색 연동
            chunk_store=self.chunk_store,  # 코드 분석 연동
        )
        plan_service = RealPlanService(self.llm)
        generate_service = RealGenerateService(self.llm)
        critic_service = RealCriticService(self.llm)
        test_service = RealTestService(self.sandbox)
        heal_service = RealHealService(self.llm)

        # Steps
        steps = [
            AnalyzeStep(analyze_service),
            PlanStep(plan_service),
            GenerateStep(generate_service),
            CriticStep(critic_service),
            TestStep(test_service, self.sandbox),
            HealStep(heal_service),
        ]

        return steps
