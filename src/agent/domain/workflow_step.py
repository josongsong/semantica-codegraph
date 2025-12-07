"""
WorkflowStep 추상화

❌ LangGraph node에 business logic 직접 작성 금지
✅ WorkflowStep에 business logic 집중
✅ LangGraph node는 WorkflowStep.execute만 호출 (orchestration only)
"""

from abc import ABC, abstractmethod

from src.agent.domain.models import WorkflowState, WorkflowStepType


class WorkflowStep(ABC):
    """
    Workflow 단계 추상 클래스.

    각 단계(Analyze, Plan, Generate, Critic, Test, Heal)는 이 클래스를 상속.
    Business logic은 여기에 집중하고, LangGraph는 orchestration만 담당.
    """

    def __init__(self, name: str):
        """
        Args:
            name: Step 이름 (예: "analyze", "plan", "generate")
        """
        self.name = name

    @abstractmethod
    async def execute(self, state: WorkflowState) -> WorkflowState:
        """
        단계 실행 (비즈니스 로직).

        Args:
            state: 현재 workflow 상태

        Returns:
            업데이트된 workflow 상태

        Raises:
            WorkflowStepError: 실행 실패 시
        """
        ...

    def can_execute(self, state: WorkflowState) -> bool:
        """
        실행 가능 여부 판단 (사전 조건).

        Args:
            state: 현재 상태

        Returns:
            True면 실행 가능
        """
        # 기본 조건: max iteration 체크
        if state.iteration >= state.max_iterations:
            return False

        return True

    def get_next_step_name(self, state: WorkflowState) -> str | None:
        """
        다음 단계 결정 (조건부 전이).

        Args:
            state: 실행 후 상태

        Returns:
            다음 step 이름 또는 None (종료)
        """
        # 기본: linear flow
        return None


class AnalyzeStep(WorkflowStep):
    """
    1단계: Analyze (Task 분석).

    역할:
    - Task 이해
    - 복잡도 추정
    - Context 선택
    - 명확화 필요 여부 판단
    """

    def __init__(self, analyze_service: "AnalyzeService"):  # type: ignore
        """
        Args:
            analyze_service: 분석 Domain Service
        """
        super().__init__("analyze")
        self.analyze_service = analyze_service

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """Task 분석 실행"""
        # Domain Service 호출 (비즈니스 로직)
        analysis = await self.analyze_service.analyze_task(state.task)

        # 상태 업데이트
        state.metadata["analysis"] = analysis
        state.current_step = WorkflowStepType.PLAN

        return state

    def can_execute(self, state: WorkflowState) -> bool:
        """Analyze는 항상 실행 가능"""
        return super().can_execute(state)


class PlanStep(WorkflowStep):
    """
    2단계: Plan (실행 계획 수립).

    역할:
    - 변경 대상 파일 선정
    - 실행 순서 결정
    - 리스크 평가
    """

    def __init__(self, plan_service: "PlanService"):  # type: ignore
        super().__init__("plan")
        self.plan_service = plan_service

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """계획 수립"""
        plan = await self.plan_service.create_plan(
            task=state.task,
            analysis=state.metadata.get("analysis"),
        )

        state.metadata["plan"] = plan
        state.current_step = WorkflowStepType.GENERATE  # type: ignore

        return state


class GenerateStep(WorkflowStep):
    """
    3단계: Generate (코드 생성).

    역할:
    - LLM 기반 코드 생성
    - Diff 생성
    - 변경사항 구조화
    """

    def __init__(self, generate_service: "GenerateService"):  # type: ignore
        super().__init__("generate")
        self.generate_service = generate_service

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """코드 생성"""
        changes = await self.generate_service.generate_code(
            task=state.task,
            plan=state.metadata.get("plan"),
        )

        state.changes = changes
        state.current_step = WorkflowStepType.CRITIC  # type: ignore
        state.iteration += 1

        return state


class CriticStep(WorkflowStep):
    """
    4단계: Critic (코드 품질 검토).

    역할:
    - 코드 품질 체크
    - 에러 분류 (syntax, logic, style)
    - 재생성 vs 테스트 진행 결정
    """

    def __init__(self, critic_service: "CriticService"):  # type: ignore
        super().__init__("critic")
        self.critic_service = critic_service

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """코드 검토"""
        critique = await self.critic_service.review_code(
            changes=state.changes,
        )

        state.metadata["critique"] = critique

        # 에러 발견 (critique는 list[str]이므로 직접 사용)
        if critique:
            state.errors.extend(critique)
            # 재생성 필요
            state.current_step = WorkflowStepType.GENERATE
        else:
            # 테스트로 진행
            state.current_step = WorkflowStepType.TEST

        return state

    def get_next_step_name(self, state: WorkflowState) -> str | None:
        """에러 있으면 generate, 없으면 test"""
        if state.errors:
            return "generate"
        return "test"


class TestStep(WorkflowStep):
    """
    5단계: Test (테스트 실행).

    역할:
    - Sandbox에서 테스트 실행
    - 실패 시 에러 분류
    - 재계획 vs 치유 결정
    """

    def __init__(
        self,
        test_service: "TestService",  # type: ignore
        sandbox_executor: "ISandboxExecutor",  # type: ignore
    ):
        super().__init__("test")
        self.test_service = test_service
        self.sandbox_executor = sandbox_executor

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """테스트 실행"""
        # Sandbox 생성
        sandbox = await self.sandbox_executor.create_sandbox({"template": "python"})

        # 테스트 실행
        results = await self.test_service.run_tests(
            changes=state.changes,
            sandbox=sandbox,
        )

        state.test_results = results

        # Sandbox 정리
        await self.sandbox_executor.destroy_sandbox(sandbox)

        # 테스트 실패
        if any(r.exit_code != 0 for r in results):
            # 재계획 필요?
            if state.should_replan():
                state.current_step = WorkflowStepType.PLAN
            else:
                state.current_step = WorkflowStepType.HEAL
        else:
            # 성공 - 종료
            state.current_step = WorkflowStepType.TEST  # Done

        return state

    def get_next_step_name(self, state: WorkflowState) -> str | None:
        """테스트 결과에 따라 분기"""
        # 성공
        if all(r.exit_code == 0 for r in state.test_results):
            return None  # 종료

        # 실패 - 재계획 필요?
        if state.should_replan():
            return "plan"

        return "heal"


class HealStep(WorkflowStep):
    """
    6단계: Heal (자가 치유).

    역할:
    - 테스트 실패 원인 분석
    - 자동 수정 시도
    - Generate로 재시도
    """

    def __init__(self, heal_service: "HealService"):  # type: ignore
        super().__init__("heal")
        self.heal_service = heal_service

    async def execute(self, state: WorkflowState) -> WorkflowState:
        """자가 치유"""
        fix = await self.heal_service.auto_fix(
            changes=state.changes,
            test_results=state.test_results,
        )

        state.metadata["fix_suggestion"] = fix
        state.current_step = WorkflowStepType.GENERATE  # type: ignore

        return state

    def get_next_step_name(self, state: WorkflowState) -> str | None:
        """항상 generate로 복귀"""
        return "generate"


# ============================================================
# Exceptions
# ============================================================


class WorkflowStepError(Exception):
    """Workflow 단계 실행 에러"""

    def __init__(self, step_name: str, message: str, cause: Exception | None = None):
        self.step_name = step_name
        self.message = message
        self.cause = cause
        super().__init__(f"[{step_name}] {message}")
