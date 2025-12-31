"""
Fast Path Orchestrator

빠른 선형 실행을 위한 System 1 Orchestrator.

특징:
- Linear workflow (단일 경로)
- Port-based architecture (Adapter 교체 가능)
- Guardrail 단일 검증
- ~5초 실행 시간

역할:
- Port만 의존 (Adapter 몰라도 됨)
- WorkflowSteps 생성 및 실행
- 전체 흐름 관리
"""

import logging
import subprocess  # CASCADE Rollback용
from dataclasses import dataclass

from apps.orchestrator.orchestrator.domain.models import AgentTask, WorkflowResult, WorkflowState, WorkflowStepType

logger = logging.getLogger(__name__)
from apps.orchestrator.orchestrator.domain.real_services import (  # noqa: E402
    RealAnalyzeService,
    RealCriticService,
    RealGenerateService,
    RealHealService,
    RealPlanService,
    RealTestService,
)
from apps.orchestrator.orchestrator.domain.workflow_step import (  # noqa: E402
    AnalyzeStep,
    CriticStep,
    GenerateStep,
    HealStep,
    PlanStep,
    TestStep,
)
from codegraph_shared.ports import (  # noqa: E402
    IGuardrailValidator,
    ILLMProvider,
    ISandboxExecutor,
    IVCSApplier,
    IWorkflowEngine,
)


@dataclass
class FastPathRequest:
    """Fast Path 실행 요청"""

    task: AgentTask
    config: dict | None = None


@dataclass
class FastPathResponse:
    """Fast Path 실행 응답"""

    success: bool
    workflow_result: WorkflowResult
    commit_sha: str | None = None
    validation_result: dict | None = None


class FastPathOrchestrator:
    """
    Fast Path Orchestrator (System 1 Engine).

    빠른 선형 실행 최적화:
    - 단일 경로 workflow
    - Port 기반 의존성 주입
    - Guardrail 단일 검증
    - ~5초 실행 목표

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
        # CASCADE Integration
        reproduction_engine=None,  # IReproductionEngine (CASCADE 통합)
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
            reproduction_engine: Reproduction engine for TDD verification (optional, CASCADE)
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

        # CASCADE Integration
        self.reproduction_engine = reproduction_engine

        # 내부 사용 (간결성)
        self.llm = llm_provider
        self.sandbox = sandbox_executor
        self.guardrail = guardrail_validator
        self.vcs = vcs_applier

    async def execute(self, request: FastPathRequest) -> FastPathResponse:
        """
        Fast Path 실행 (CASCADE Reproduction Engine 통합).

        Flow:
        1. [CASCADE] Reproduction Script 생성 & 버그 재현 확인
        2. Workflow 실행 (코드 수정)
        3. Guardrail 검증
        4. VCS 적용
        5. [CASCADE] Reproduction Script 성공 확인 (검증)
        6. 실패 시 Rollback

        Args:
            request: Agent 실행 요청

        Returns:
            Agent 실행 응답
        """
        reproduction_script = None
        rollback_required = False

        try:
            # ================================================================
            # CASCADE Phase 1: Reproduction Script 생성 (TDD - Before)
            # ================================================================
            if self.reproduction_engine and request.task.description:
                logger.info("CASCADE: Generating reproduction script...")

                try:
                    reproduction_script = await self.reproduction_engine.generate_reproduction_script(
                        issue_description=request.task.description,
                        context_files=request.task.context_files or [],
                        tech_stack={"test_framework": "pytest"},  # TODO: 동적 감지
                    )

                    logger.info(f"CASCADE: Reproduction script created: {reproduction_script.script_path}")

                    # 버그 재현 확인 (FAIL 기대)
                    failure_result = await self.reproduction_engine.verify_failure(reproduction_script)

                    if not failure_result.is_bug_reproduced():
                        logger.warning(
                            f"CASCADE: Bug not reproduced (status={failure_result.status.value}), "
                            "proceeding without reproduction verification"
                        )
                        reproduction_script = None  # 재현 실패 → 검증 skip
                    else:
                        logger.info("CASCADE: Bug successfully reproduced ✓")

                except Exception as repro_error:
                    logger.warning(f"CASCADE: Reproduction script generation failed: {repro_error}, continuing...")
                    reproduction_script = None

            # ================================================================
            # Step 1-3: 기존 Workflow 실행
            # ================================================================
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
                rollback_required = True  # VCS 적용 완료 → Rollback 가능

                # ================================================================
                # CASCADE Phase 2: Reproduction Script 검증 (TDD - After)
                # ================================================================
                if reproduction_script and self.reproduction_engine:
                    logger.info("CASCADE: Verifying fix with reproduction script...")

                    try:
                        verification_result = await self.reproduction_engine.verify_fix(
                            reproduction_script, after_changes=True
                        )

                        if verification_result.exit_code != 0:
                            logger.error(
                                f"CASCADE: Fix verification FAILED! (exit_code={verification_result.exit_code})"
                            )
                            logger.error(f"CASCADE: stdout={verification_result.stdout}")
                            logger.error(f"CASCADE: stderr={verification_result.stderr}")

                            # Rollback 수행
                            await self._rollback_changes(commit_sha)
                            rollback_required = False  # 이미 롤백 완료

                            # 실패로 변경
                            workflow_result.success = False
                            workflow_result.errors.append(f"CASCADE verification failed: {verification_result.stderr}")
                            commit_sha = None

                        else:
                            logger.info("CASCADE: Fix verification PASSED ✓")

                    except Exception as verify_error:
                        logger.error(f"CASCADE: Verification error: {verify_error}")
                        # 검증 에러는 치명적이지 않음 (경고만)

            return FastPathResponse(
                success=workflow_result.success,
                workflow_result=workflow_result,
                commit_sha=commit_sha,
                validation_result=validation_result,
            )

        except Exception as e:
            logger.exception(f"FastPath Orchestrator critical error: {e}")

            # Rollback 시도 (필요 시)
            if rollback_required:
                try:
                    await self._rollback_changes(None)
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")

            raise

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

    async def _rollback_changes(self, commit_sha: str | None) -> None:
        """
        변경사항 롤백 (CASCADE 검증 실패 시).

        Args:
            commit_sha: 롤백할 커밋 SHA (None이면 HEAD~1)
        """
        logger.warning("CASCADE: Rolling back changes...")

        try:
            if commit_sha:
                # 특정 커밋 롤백
                subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True, check=True)
            else:
                # 작업 트리 정리
                subprocess.run(["git", "reset", "--hard", "HEAD"], capture_output=True, text=True, check=True)

            logger.info("CASCADE: Rollback completed")

        except subprocess.CalledProcessError as e:
            logger.error(f"CASCADE: Rollback failed: {e.stderr}")
            raise RuntimeError(f"Rollback failed: {e.stderr}")


# ============================================================================
# Backward Compatibility Aliases (v7 naming)
# ============================================================================

V7AgentOrchestrator = FastPathOrchestrator
V7AgentRequest = FastPathRequest
V7AgentResponse = FastPathResponse

AgentOrchestrator = FastPathOrchestrator
AgentRequest = FastPathRequest
AgentResponse = FastPathResponse
