"""
Plan Tool Provider (RFC-041)

기존 CodeFoundationToolProvider를 대체.

핵심 변경:
- ❌ LLM이 Tool을 직접 선택
- ✅ LLM이 Plan을 선택 → 시스템이 Step Chain 실행

전체 흐름:
    User Query
     → LLM: Plan 선택 (≤10)
     → System: Plan → Step → Tool Chain 실행
     → LLM: 결과 해석 및 설명
"""

import logging
from typing import Any

from .models import AnalysisPlan, PlanResult
from .plan_executor import AutoTool, PlanExecutor
from .plan_registry import PlanRegistry
from .plan_tools import (
    PLAN_TOOLS,
    get_llm_tools_anthropic,
    get_llm_tools_openai,
    get_plan_tool_by_name,
)

logger = logging.getLogger(__name__)


class PlanToolProvider:
    """
    Plan 기반 Tool Provider (RFC-041)

    역할:
    1. LLM에 10개 Plan Tool만 노출
    2. Plan 선택 → Step Chain 실행
    3. 결정론적 실행 보장
    4. 실행 replay/검증 지원

    기존 CodeFoundationToolProvider와의 차이:
    - Tool 검색/선택 로직 제거
    - Plan 실행 로직 추가
    - LLM 노출 Tool 고정 (10개)
    """

    def __init__(
        self,
        tool_registry: Any,
        plan_registry: PlanRegistry | None = None,
        auto_tool: AutoTool | None = None,
        cache: Any | None = None,
    ):
        """
        Args:
            tool_registry: 기존 Tool Registry (Tool 실행용)
            plan_registry: Plan Registry (Plan 정의)
            auto_tool: AutoTool (파라미터 조정)
            cache: 결과 캐시
        """
        self.tool_registry = tool_registry
        self.plan_registry = plan_registry or PlanRegistry()
        self.auto_tool = auto_tool or AutoTool()
        self.cache = cache

        # Plan Executor 초기화
        self.executor = PlanExecutor(
            tool_registry=tool_registry,
            auto_tool=self.auto_tool,
            cache=cache,
        )

        # 실행 기록 (replay용)
        self._execution_history: list[dict[str, Any]] = []
        self._max_history = 100

        logger.info(f"PlanToolProvider initialized with {len(self.plan_registry.get_all_plans())} plans")

    # ================================================================
    # LLM 인터페이스 (10개 Plan Tool만 노출)
    # ================================================================

    def get_tools_for_llm(self, provider: str = "openai") -> list[dict[str, Any]]:
        """
        LLM에 노출할 Tool 목록 반환 (10개 고정)

        Args:
            provider: "openai" 또는 "anthropic"

        Returns:
            LLM provider 포맷의 Tool 목록
        """
        if provider == "anthropic":
            return get_llm_tools_anthropic()
        return get_llm_tools_openai()

    def get_tool_names(self) -> list[str]:
        """LLM에 노출되는 Tool 이름 목록"""
        return [tool.name for tool in PLAN_TOOLS]

    # ================================================================
    # Plan 실행 (핵심)
    # ================================================================

    def execute_plan(
        self,
        plan_name: str,
        target: str,
        context: dict[str, Any] | None = None,
        version: str | None = None,
    ) -> PlanResult:
        """
        Plan 실행

        LLM이 선택한 Plan을 실행하고 결과 반환.

        Args:
            plan_name: Plan 이름 (e.g., "plan_analyze_security")
            target: 분석 대상 (파일 경로, 함수명 등)
            context: 추가 컨텍스트
            version: Plan 버전 (None이면 최신)

        Returns:
            PlanResult: 실행 결과

        Raises:
            ValueError: Plan을 찾을 수 없는 경우
        """
        # 1. Plan 가져오기
        plan = self.plan_registry.get_plan(plan_name, version)
        if not plan:
            raise ValueError(f"Plan not found: {plan_name}:{version or 'latest'}")

        if plan.deprecated:
            logger.warning(
                f"Plan {plan.full_name} is deprecated. Consider using {plan.successor or 'a newer version'}."
            )

        # 2. 실행 컨텍스트 구성
        exec_context = {
            "target": target,
            "plan_name": plan_name,
            "plan_version": plan.version,
            **(context or {}),
        }

        logger.info(f"Executing plan: {plan.full_name} for target: {target}")

        # 3. Plan 실행
        result = self.executor.execute(plan, exec_context)

        # 4. 실행 기록 저장 (replay용)
        self._record_execution(plan, exec_context, result)

        return result

    async def execute_plan_async(
        self,
        plan_name: str,
        target: str,
        context: dict[str, Any] | None = None,
        version: str | None = None,
    ) -> PlanResult:
        """
        Plan 비동기 실행

        Args:
            plan_name: Plan 이름
            target: 분석 대상
            context: 추가 컨텍스트
            version: Plan 버전

        Returns:
            PlanResult: 실행 결과
        """
        plan = self.plan_registry.get_plan(plan_name, version)
        if not plan:
            raise ValueError(f"Plan not found: {plan_name}:{version or 'latest'}")

        exec_context = {
            "target": target,
            "plan_name": plan_name,
            "plan_version": plan.version,
            **(context or {}),
        }

        result = await self.executor.execute_async(plan, exec_context)
        self._record_execution(plan, exec_context, result)

        return result

    # ================================================================
    # LLM Tool Call 처리 (실제 통합 지점)
    # ================================================================

    def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        LLM Tool Call 처리

        LLM이 선택한 Plan Tool을 실행하고 결과 반환.
        V8 Orchestrator에서 호출됨.

        Args:
            tool_name: LLM이 선택한 Plan Tool 이름
            arguments: Tool 인자 (target, context 등)

        Returns:
            Tool 실행 결과 (LLM에 반환)
        """
        # 1. Plan Tool 확인
        plan_tool = get_plan_tool_by_name(tool_name)
        if not plan_tool:
            return {
                "success": False,
                "error": f"Unknown plan tool: {tool_name}",
                "available_tools": self.get_tool_names(),
            }

        # 2. 필수 인자 확인
        target = arguments.get("target")
        if not target:
            return {
                "success": False,
                "error": "Missing required argument: target",
            }

        # 3. Plan 실행
        try:
            context = arguments.get("context", {})
            if isinstance(context, str):
                context = {"user_context": context}

            result = self.execute_plan(
                plan_name=tool_name,
                target=target,
                context=context,
            )

            # 4. 결과 포맷팅 (LLM 친화적)
            return self._format_result_for_llm(result)

        except Exception as e:
            logger.exception(f"Plan execution failed: {tool_name}")
            return {
                "success": False,
                "error": str(e),
            }

    def _format_result_for_llm(self, result: PlanResult) -> dict[str, Any]:
        """
        결과를 LLM이 해석하기 좋은 형태로 포맷팅

        Args:
            result: PlanResult

        Returns:
            LLM 친화적 결과 딕셔너리
        """
        # 성공한 Step들의 데이터 수집
        step_summaries = []
        for step_result in result.step_results:
            if step_result.is_success:
                step_summaries.append(
                    {
                        "step": step_result.step_name,
                        "status": step_result.status.value,
                        "data_preview": self._preview_data(step_result.data),
                    }
                )

        return {
            "success": result.is_success,
            "plan": result.plan_name,
            "version": result.plan_version,
            "summary": result.summary,
            "final_data": result.final_data,
            "steps": step_summaries,
            "stats": {
                "completed": result.steps_completed,
                "skipped": result.steps_skipped,
                "failed": result.steps_failed,
                "execution_time_ms": result.total_execution_time_ms,
            },
        }

    def _preview_data(self, data: Any, max_length: int = 500) -> str:
        """데이터 미리보기 (너무 길면 자름)"""
        if data is None:
            return "None"

        if isinstance(data, (list, dict)):
            import json

            try:
                preview = json.dumps(data, ensure_ascii=False, default=str)
            except Exception:
                preview = str(data)
        else:
            preview = str(data)

        if len(preview) > max_length:
            return preview[:max_length] + "..."

        return preview

    # ================================================================
    # Replay / 검증 지원
    # ================================================================

    def _record_execution(
        self,
        plan: AnalysisPlan,
        context: dict[str, Any],
        result: PlanResult,
    ):
        """실행 기록 저장"""
        record = {
            "plan_name": plan.name,
            "plan_version": plan.version,
            "context": context,
            "result": result.to_dict(),
            "timestamp": __import__("time").time(),
        }

        self._execution_history.append(record)

        # 최대 크기 유지
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history :]

    def get_execution_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """최근 실행 기록 반환"""
        return self._execution_history[-limit:]

    def replay_execution(self, record_index: int) -> PlanResult | None:
        """
        과거 실행 재현 (replay)

        동일 Plan, 동일 context로 다시 실행.

        Args:
            record_index: 실행 기록 인덱스

        Returns:
            새 실행 결과 (비교용)
        """
        if record_index < 0 or record_index >= len(self._execution_history):
            logger.error(f"Invalid record index: {record_index}")
            return None

        record = self._execution_history[record_index]

        return self.execute_plan(
            plan_name=record["plan_name"],
            target=record["context"]["target"],
            context=record["context"],
            version=record["plan_version"],
        )

    # ================================================================
    # 통계 및 디버깅
    # ================================================================

    def get_statistics(self) -> dict[str, Any]:
        """통계 정보"""
        return {
            "plan_registry": self.plan_registry.get_statistics(),
            "executor": self.executor.get_statistics(),
            "execution_history_count": len(self._execution_history),
        }

    def explain_plan(self, plan_name: str, version: str | None = None) -> str:
        """
        Plan 설명 (디버깅/문서화용)

        Args:
            plan_name: Plan 이름
            version: 버전

        Returns:
            Plan 설명 문자열
        """
        plan = self.plan_registry.get_plan(plan_name, version)
        if not plan:
            return f"Plan not found: {plan_name}"

        lines = [
            f"Plan: {plan.full_name}",
            f"Description: {plan.description}",
            f"Category: {plan.category.value}",
            "",
            "Steps:",
        ]

        for i, step in enumerate(plan.steps, 1):
            deps = f" (depends: {', '.join(step.depends_on)})" if step.depends_on else ""
            lines.append(f"  {i}. {step.name} → {step.tool}{deps}")

        return "\n".join(lines)


# ================================================================
# Factory
# ================================================================


class PlanToolProviderFactory:
    """PlanToolProvider 팩토리"""

    @staticmethod
    def create(
        tool_registry: Any,
        cache: Any | None = None,
        max_cost: float = 1.0,
    ) -> PlanToolProvider:
        """
        PlanToolProvider 생성

        Args:
            tool_registry: 기존 Tool Registry
            cache: 결과 캐시
            max_cost: AutoTool 최대 비용

        Returns:
            PlanToolProvider 인스턴스
        """
        plan_registry = PlanRegistry()
        auto_tool = AutoTool(max_cost=max_cost)

        provider = PlanToolProvider(
            tool_registry=tool_registry,
            plan_registry=plan_registry,
            auto_tool=auto_tool,
            cache=cache,
        )

        logger.info("PlanToolProvider created via factory")
        return provider
