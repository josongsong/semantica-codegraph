"""Agent Orchestrator

전체 Agent 파이프라인 조율 (ADR-001)

Flow:
1. Router: Intent 분류 + Confidence
2. TaskGraph: Task 분해
3. Workflow: Task 실행
4. Result: 최종 결과 반환
"""

import time
from typing import Any

from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.router.router import Router
from src.agent.task_graph.planner import TaskGraphPlanner
from src.agent.workflow.models import WorkflowState, WorkflowStep
from src.agent.workflow.state_machine import WorkflowStateMachine
from src.common.observability import get_logger

from .models import (
    AgentResult,
    ExecutionStatus,
    OrchestratorConfig,
)

logger = get_logger(__name__)


class AgentOrchestrator:
    """
    Agent Orchestrator (ADR-001)

    책임:
    1. 전체 파이프라인 실행 조율
    2. 컴포넌트 간 데이터 흐름 관리
    3. 에러 핸들링 및 복구
    4. 실행 상태 추적

    Phase 0: 기본 파이프라인
    Phase 1: Retry, Fallback, Streaming
    """

    def __init__(
        self,
        router: Router,
        task_planner: TaskGraphPlanner,
        workflow: WorkflowStateMachine,
        context_adapter: ContextAdapter,
        config: OrchestratorConfig | None = None,
    ):
        """
        Args:
            router: Intent 분류기
            task_planner: Task 분해기
            workflow: Workflow 실행기
            context_adapter: Context 검색 Facade
            config: 설정 (None이면 기본값)
        """
        self.router = router
        self.task_planner = task_planner
        self.workflow = workflow
        self.context = context_adapter
        self.config = config or OrchestratorConfig()

        logger.info("AgentOrchestrator initialized")

    async def execute(
        self,
        user_request: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """
        메인 실행 파이프라인

        Args:
            user_request: 사용자 요청
            context: 실행 컨텍스트 (repo_id 등)

        Returns:
            AgentResult: 실행 결과
        """
        start_time = time.time()
        context = context or {}

        logger.info(f"Orchestrator.execute: {user_request[:50]}...")

        try:
            # Step 1: Router - Intent 분류
            logger.info("Step 1: Router - Intent Classification")
            intent_result = await self._route(user_request, context)

            # Low confidence 처리 (Phase 0: 그냥 진행, Phase 1: 사용자 확인)
            if intent_result.context.get("should_ask_user") and self.config.ask_user_on_low_confidence:
                return self._ask_user_clarification(intent_result, start_time)

            # Step 2: TaskGraph - Task 분해
            logger.info(f"Step 2: TaskGraph - Decomposition (intent={intent_result.intent.value})")
            task_graph = self._plan(intent_result)

            # Step 3: Workflow - 실행
            logger.info(f"Step 3: Workflow - Execution ({len(task_graph.tasks)} tasks)")
            final_state = self._execute_workflow(intent_result, task_graph)

            # Step 4: Result - 결과 포맷팅
            execution_time = (time.time() - start_time) * 1000  # ms
            result = self._format_result(
                intent_result=intent_result,
                task_graph=task_graph,
                final_state=final_state,
                execution_time_ms=execution_time,
            )

            logger.info(f"Orchestrator.execute completed: {result.status.value} ({execution_time:.0f}ms)")
            return result

        except Exception as e:
            logger.exception(f"Orchestrator.execute failed: {e}")
            execution_time = (time.time() - start_time) * 1000

            return AgentResult(
                intent=context.get("intent", "unknown"),
                confidence=0.0,
                status=ExecutionStatus.FAILED,
                result=None,
                error=str(e),
                error_details={"exception_type": type(e).__name__},
                execution_time_ms=execution_time,
            )

    async def execute_with_retry(
        self,
        user_request: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """
        재시도 로직 포함 실행 (Phase 1)

        Phase 0: execute()와 동일 (재시도 없음)
        Phase 1: max_retries만큼 재시도
        """
        # Phase 0: 재시도 없이 1번만 실행
        return await self.execute(user_request, context)

        # Phase 1 구현:
        # for attempt in range(self.config.max_retries):
        #     try:
        #         return await self.execute(user_request, context)
        #     except Exception as e:
        #         if attempt == self.config.max_retries - 1:
        #             raise
        #         await asyncio.sleep(self.config.retry_delay_seconds)

    async def _route(self, user_request: str, context: dict[str, Any]):
        """Step 1: Intent 분류 (Unified Router 사용)"""
        from src.agent.router.unified_router import UnifiedRouter

        unified_router = UnifiedRouter()
        budget_ms = context.get("max_latency_ms", 5000)

        plan = unified_router.route(user_request, budget_ms=budget_ms, context=context)

        # Context 업데이트
        context.update(
            {
                "routing_plan": plan,
                "intent": plan.intent,
                "complexity": plan.complexity,
                "adaptive_k": plan.adaptive_k,
                "strategy_path": plan.strategy_path,
                "use_hyde": plan.use_hyde,
                "use_cross_encoder": plan.use_cross_encoder,
                "use_multi_query": plan.use_multi_query,
                "workflow_mode": plan.workflow_mode,
            }
        )

        # 기존 IntentResult 형식으로 변환 (호환성)
        from src.agent.router.models import Intent, IntentResult

        try:
            intent_enum = Intent(plan.intent.lower())
        except ValueError:
            intent_enum = Intent.UNKNOWN

        return IntentResult(
            intent=intent_enum,
            confidence=1.0,  # Rule 기반이므로 항상 높음
            reasoning=f"Unified Router: {plan.intent} (complexity={plan.complexity}, budget={plan.budget_ms}ms)",
            context=context,
        )

    def _plan(self, intent_result):
        """Step 2: Task 분해"""
        return self.task_planner.plan(
            user_intent=intent_result.intent.value,
            context=intent_result.context,
        )

    def _execute_workflow(self, intent_result, task_graph):
        """Step 3: Workflow 실행"""
        workflow_state = WorkflowState(
            current_step=WorkflowStep.ANALYZE,
            iteration=0,
            context={
                **intent_result.context,
                "task_graph": task_graph,
                "context_adapter": self.context,
            },
        )

        return self.workflow.run(workflow_state)

    def _format_result(
        self,
        intent_result,
        task_graph,
        final_state,
        execution_time_ms: float,
    ) -> AgentResult:
        """Step 4: 결과 포맷팅"""
        return AgentResult(
            intent=intent_result.intent,
            confidence=intent_result.context.get("final_confidence", intent_result.confidence),
            status=ExecutionStatus.COMPLETED
            if final_state.current_step == WorkflowStep.COMPLETED
            else ExecutionStatus.PARTIAL,
            result=final_state.result,
            tasks_completed=list(task_graph.tasks.keys()),
            metadata={
                "intent_reasoning": intent_result.reasoning,
                "confidence_level": intent_result.context.get("confidence_level", "unknown"),
                "workflow_iterations": final_state.iteration,
                "task_count": len(task_graph.tasks),
                "parallel_groups": len(task_graph.parallel_groups) if task_graph.parallel_groups else 0,
            },
            execution_time_ms=execution_time_ms,
            tokens_used=0,  # Phase 1: 실제 측정
            cost_usd=0.0,  # Phase 1: 실제 계산
        )

    def _ask_user_clarification(self, intent_result, start_time: float) -> AgentResult:
        """Low confidence 처리 (Phase 1)"""
        execution_time = (time.time() - start_time) * 1000

        logger.warning(f"Low confidence detected: {intent_result.confidence:.2f}")

        return AgentResult(
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            status=ExecutionStatus.PENDING,
            result=None,
            metadata={
                "reason": "low_confidence",
                "message": "User clarification needed",
                "confidence": intent_result.confidence,
                "threshold": intent_result.context.get("threshold", 0.7),
            },
            execution_time_ms=execution_time,
        )

    def get_status(self) -> dict[str, Any]:
        """현재 상태 조회 (Phase 1: 실제 상태 추적)"""
        return {
            "orchestrator": "active",
            "config": {
                "max_retries": self.config.max_retries,
                "enable_fallback": self.config.enable_fallback,
                "enable_full_workflow": self.config.enable_full_workflow,
            },
            "components": {
                "router": "initialized",
                "task_planner": "initialized",
                "workflow": "initialized",
                "context_adapter": "initialized",
            },
        }
