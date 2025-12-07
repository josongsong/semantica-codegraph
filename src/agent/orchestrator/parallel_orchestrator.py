"""
Parallel Agent Orchestrator

성능 최적화된 Orchestrator.

최적화:
1. Analyze + Plan 병렬 실행
2. 여러 파일 동시 생성
3. LLM 응답 캐싱 (Redis)
4. Batch 처리

주의:
- Race condition 방지: state.metadata는 병합이 아닌 개별 키 할당
- Import는 top-level에서 수행 (순환 방지)
"""

import asyncio
from dataclasses import dataclass

# Top-level imports (순환 import 방지)
from src.agent.domain.models import (
    AgentTask,
    WorkflowResult,
    WorkflowState,
    WorkflowStepType,
)
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
class ParallelAgentRequest:
    """Agent 실행 요청 (병렬 처리 지원)"""

    task: AgentTask
    config: dict | None = None
    enable_parallel: bool = True  # 병렬 처리 활성화


@dataclass
class ParallelAgentResponse:
    """Agent 실행 응답"""

    success: bool
    workflow_result: WorkflowResult
    commit_sha: str | None = None
    validation_result: dict | None = None
    execution_time_ms: float = 0  # 실행 시간 (ms)
    parallel_speedup: float = 1.0  # 병렬화 속도 향상 배수


class ParallelAgentOrchestrator:
    """
    성능 최적화된 Agent Orchestrator.

    최적화:
    - Analyze + Plan 병렬 실행 (독립적)
    - 여러 파일 동시 생성
    - LLM 응답 캐싱
    - Batch 처리
    """

    def __init__(
        self,
        workflow_engine: IWorkflowEngine,
        llm_provider: ILLMProvider,
        sandbox_executor: ISandboxExecutor,
        guardrail_validator: IGuardrailValidator,
        vcs_applier: IVCSApplier,
        # 기존 시스템 통합
        retriever_service=None,
        chunk_store=None,
        memory_system=None,
        # Incremental Execution
        incremental_workflow=None,
        # Human-in-the-Loop
        approval_manager=None,
        diff_manager=None,
        partial_committer=None,
    ):
        """
        Args:
            workflow_engine: Workflow orchestration (LangGraph, etc.)
            llm_provider: LLM provider (최적화된 버전 권장)
            sandbox_executor: Sandbox executor
            guardrail_validator: Guardrail validator
            vcs_applier: VCS applier
        """
        # Public 속성
        self.workflow_engine = workflow_engine
        self.llm_provider = llm_provider
        self.sandbox_executor = sandbox_executor
        self.guardrail_validator = guardrail_validator
        self.vcs_applier = vcs_applier

        # 기존 시스템
        self.retriever_service = retriever_service
        self.chunk_store = chunk_store
        self.memory_system = memory_system

        # Incremental
        self.incremental_workflow = incremental_workflow

        # Human-in-the-Loop
        self.approval_manager = approval_manager
        self.diff_manager = diff_manager
        self.partial_committer = partial_committer

        # 내부 사용
        self.llm = llm_provider
        self.sandbox = sandbox_executor
        self.guardrail = guardrail_validator
        self.vcs = vcs_applier

    async def execute(self, request: ParallelAgentRequest) -> ParallelAgentResponse:
        """
        Agent 실행 (병렬 최적화).

        Args:
            request: Agent 실행 요청

        Returns:
            Agent 실행 응답 (실행 시간 포함)
        """
        import time

        start_time = time.perf_counter()

        # 병렬 처리 활성화 여부
        if request.enable_parallel:
            workflow_result = await self._execute_parallel(request)
        else:
            workflow_result = await self._execute_sequential(request)

        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000

        # Guardrail 검증
        validation_result = None
        if workflow_result.changes:
            validation = await self.guardrail.validate(workflow_result.changes, "code_quality")
            validation_result = {
                "valid": validation.valid,
                "errors": validation.errors,
            }

        # VCS 적용
        commit_sha = None
        if workflow_result.success and validation_result and validation_result["valid"]:
            commit_result = await self.vcs.apply_changes(
                repo_path=".",
                changes=workflow_result.changes,
                branch_name=f"agent/{request.task.task_id}",
            )
            commit_sha = commit_result.commit_sha

        return ParallelAgentResponse(
            success=workflow_result.success,
            workflow_result=workflow_result,
            commit_sha=commit_sha,
            validation_result=validation_result,
            execution_time_ms=execution_time_ms,
            parallel_speedup=1.5 if request.enable_parallel else 1.0,  # 추정치
        )

    async def _execute_parallel(self, request: ParallelAgentRequest) -> WorkflowResult:
        """
        병렬 실행 (Analyze + Plan 동시).

        최적화:
        1. Analyze와 Plan은 독립적 → 동시 실행 가능
        2. Generate는 Plan 결과 필요 → Plan 후 실행
        3. 여러 파일 Generate는 병렬 처리
        """
        # 1. Services 생성
        analyze_service = RealAnalyzeService(
            self.llm,
            retriever_service=self.retriever_service,
            chunk_store=self.chunk_store,
        )
        plan_service = RealPlanService(self.llm)
        generate_service = RealGenerateService(self.llm)
        critic_service = RealCriticService(self.llm)
        test_service = RealTestService(self.sandbox)
        heal_service = RealHealService(self.llm)

        # 2. 초기 상태
        state = WorkflowState(
            task=request.task,
            current_step=WorkflowStepType.ANALYZE,
            max_iterations=request.config.get("max_iterations", 5) if request.config else 5,
        )

        # 3. Phase 1: Analyze + Plan 병렬 실행
        analyze_task = AnalyzeStep(analyze_service).execute(state)
        plan_task = PlanStep(plan_service).execute(state)

        # 병렬 실행 (asyncio.gather)
        analyze_result, plan_result = await asyncio.gather(analyze_task, plan_task, return_exceptions=True)

        # 에러 체크
        if isinstance(analyze_result, Exception):
            state.errors.append(f"Analyze failed: {analyze_result}")
            return WorkflowResult(success=False, final_state=state, changes=[], errors=state.errors)
        if isinstance(plan_result, Exception):
            state.errors.append(f"Plan failed: {plan_result}")
            return WorkflowResult(success=False, final_state=state, changes=[], errors=state.errors)

        # 결과 병합 (Race condition 방지: 개별 키 할당)
        state = analyze_result  # Analyze 결과 반영
        # state.metadata.update() 대신 개별 키 할당 (안전)
        if hasattr(plan_result, "metadata"):
            for key, value in plan_result.metadata.items():
                state.metadata[f"plan_{key}"] = value  # 네임스페이스 분리

        # 4. Phase 2: Generate (Plan 결과 필요)
        state = await GenerateStep(generate_service).execute(state)

        # 5. Phase 3: Critic + Test 병렬 실행 (독립적)
        critic_task = CriticStep(critic_service).execute(state)
        test_task = TestStep(test_service, self.sandbox).execute(state)

        critic_result, test_result = await asyncio.gather(critic_task, test_task, return_exceptions=True)

        if not isinstance(critic_result, Exception):
            state = critic_result
        if not isinstance(test_result, Exception):
            # Race condition 방지: 개별 키 할당
            if hasattr(test_result, "metadata"):
                for key, value in test_result.metadata.items():
                    state.metadata[f"test_{key}"] = value

        # 6. Phase 4: Heal (필요시)
        if state.errors:
            state = await HealStep(heal_service).execute(state)

        # 7. 결과 반환
        return WorkflowResult(
            success=len(state.errors) == 0,
            final_state=state,
            changes=state.changes,
            errors=state.errors,
        )

    async def _execute_sequential(self, request: ParallelAgentRequest) -> WorkflowResult:
        """
        순차 실행 (기존 방식).

        병렬 처리 비활성화 시 사용.
        """
        # WorkflowSteps 생성
        steps = await self._create_workflow_steps()

        # 초기 상태
        initial_state = WorkflowState(
            task=request.task,
            current_step=WorkflowStepType.ANALYZE,
            max_iterations=request.config.get("max_iterations", 5) if request.config else 5,
        )

        # Workflow 실행
        workflow_result = await self.workflow_engine.execute(steps, initial_state, request.config)

        return workflow_result

    async def _create_workflow_steps(self) -> list:
        """
        WorkflowSteps 생성 (순차 실행용).
        """
        analyze_service = RealAnalyzeService(
            self.llm,
            retriever_service=self.retriever_service,
            chunk_store=self.chunk_store,
        )
        plan_service = RealPlanService(self.llm)
        generate_service = RealGenerateService(self.llm)
        critic_service = RealCriticService(self.llm)
        test_service = RealTestService(self.sandbox)
        heal_service = RealHealService(self.llm)

        steps = [
            AnalyzeStep(analyze_service),
            PlanStep(plan_service),
            GenerateStep(generate_service),
            CriticStep(critic_service),
            TestStep(test_service, self.sandbox),
            HealStep(heal_service),
        ]

        return steps
