"""
Plan Executor (RFC-041)

Plan → Step → Tool Chain 실행을 담당.

핵심 원칙:
- Step 순서 변경 불가
- Step 생략은 시스템 규칙으로만 가능 (cache hit, 빈 입력 등)
- LLM은 Step 구성에 개입 불가
"""

import asyncio
import logging
import time
from typing import Any

from .models import (
    AnalysisPlan,
    PlanResult,
    PlanStep,
    StepResult,
    StepStatus,
)
from .tools.base import StepTool

logger = logging.getLogger(__name__)


def _create_step_tool_registry() -> dict[str, StepTool]:
    """Step Tool 레지스트리 생성"""
    from .tools import (
        # Understanding
        AnalyzeUsagePatternTool,
        AnalyzeFileStructureTool,
        ResolveImportsTool,
        BuildDependencyGraphTool,
        # Trace
        TraceAliasTool,
        FindEntryPointsTool,
        # Security
        FindTypeHierarchyTool,
        AnalyzeControlFlowTool,
        ValidateSecurityGuardTool,
        # Explain
        ExtractContextTool,
        ExplainFindingTool,
        # Generate
        AnalyzeIssueTool,
        DetermineFixStrategyTool,
        GeneratePatchTool,
        ValidatePatchTool,
        # Verify
        ParsePatchTool,
        VerifySyntaxTool,
        VerifyTypeSafetyTool,
        CheckRegressionTool,
        RunTestsTool,
        # Variant
        ExtractCodePatternTool,
        SearchSimilarCodeTool,
        RankSimilarityTool,
    )

    tools: list[StepTool] = [
        # Understanding
        AnalyzeUsagePatternTool(),
        AnalyzeFileStructureTool(),
        ResolveImportsTool(),
        BuildDependencyGraphTool(),
        # Trace
        TraceAliasTool(),
        FindEntryPointsTool(),
        # Security
        FindTypeHierarchyTool(),
        AnalyzeControlFlowTool(),
        ValidateSecurityGuardTool(),
        # Explain
        ExtractContextTool(),
        ExplainFindingTool(),
        # Generate
        AnalyzeIssueTool(),
        DetermineFixStrategyTool(),
        GeneratePatchTool(),
        ValidatePatchTool(),
        # Verify
        ParsePatchTool(),
        VerifySyntaxTool(),
        VerifyTypeSafetyTool(),
        CheckRegressionTool(),
        RunTestsTool(),
        # Variant
        ExtractCodePatternTool(),
        SearchSimilarCodeTool(),
        RankSimilarityTool(),
    ]

    return {tool.name: tool for tool in tools}


class StepExecutionError(Exception):
    """Step 실행 에러"""

    def __init__(self, step_name: str, message: str, cause: Exception | None = None):
        self.step_name = step_name
        self.cause = cause
        super().__init__(f"Step '{step_name}' failed: {message}")


class PlanExecutor:
    """
    Plan 실행자

    역할:
    1. Plan의 Step들을 순서대로 실행
    2. Step 간 데이터 전달
    3. 조건부 Skip 처리 (cache, 빈 입력 등)
    4. Fallback 처리
    5. 실행 시간 추적

    AutoTool의 역할:
    - Tool 파라미터 자동 조정 (depth, timeout 등)
    - 비용 초과 시 fallback 전환
    - cache hit 시 step skip
    """

    def __init__(
        self,
        tool_registry: Any | None = None,
        auto_tool: Any | None = None,
        cache: Any | None = None,
    ):
        """
        Args:
            tool_registry: 기존 ToolRegistry (Foundation Tool 실행용)
            auto_tool: AutoTool 인스턴스 (파라미터 조정용)
            cache: 캐시 (결과 재사용)
        """
        self.tool_registry = tool_registry
        self.auto_tool = auto_tool
        self.cache = cache

        # Step Tool 레지스트리 (RFC-041에서 새로 구현된 Tool들)
        self._step_tools = _create_step_tool_registry()

        # 실행 통계
        self._execution_count = 0
        self._total_steps_executed = 0
        self._total_steps_skipped = 0

        logger.info(f"PlanExecutor initialized with {len(self._step_tools)} step tools")

    def execute(self, plan: AnalysisPlan, context: dict[str, Any]) -> PlanResult:
        """
        Plan 실행 (동기)

        Args:
            plan: 실행할 Plan
            context: 실행 컨텍스트 (target, 파라미터 등)

        Returns:
            PlanResult: 실행 결과
        """
        start_time = time.time()
        self._execution_count += 1

        logger.info(f"Executing plan: {plan.full_name} ({len(plan.steps)} steps)")

        step_results: list[StepResult] = []
        step_outputs: dict[str, Any] = {}  # Step 이름 → 결과 데이터
        has_failure = False

        for step in plan.steps:
            # 의존성 체크
            if not self._check_dependencies(step, step_outputs):
                result = StepResult(
                    step_name=step.name,
                    status=StepStatus.SKIPPED,
                    error="Dependencies not satisfied",
                )
                step_results.append(result)
                continue

            # Step 실행
            try:
                result = self._execute_step(step, context, step_outputs)
                step_results.append(result)

                if result.status == StepStatus.COMPLETED:
                    step_outputs[step.name] = result.data
                    self._total_steps_executed += 1
                elif result.status == StepStatus.SKIPPED:
                    self._total_steps_skipped += 1
                elif result.status == StepStatus.FAILED:
                    has_failure = True
                    # 실패해도 계속 진행 (soft failure)
                    logger.warning(f"Step '{step.name}' failed: {result.error}")

            except Exception as e:
                logger.exception(f"Step '{step.name}' raised exception")
                result = StepResult(
                    step_name=step.name,
                    status=StepStatus.FAILED,
                    error=str(e),
                )
                step_results.append(result)
                has_failure = True

        # 최종 결과 구성
        total_time = (time.time() - start_time) * 1000

        # 마지막 성공한 Step의 데이터를 final_data로
        final_data = None
        for result in reversed(step_results):
            if result.status == StepStatus.COMPLETED and result.data:
                final_data = result.data
                break

        plan_result = PlanResult(
            plan_name=plan.name,
            plan_version=plan.version,
            success=not has_failure,
            step_results=step_results,
            final_data=final_data,
            total_execution_time_ms=total_time,
        )

        logger.info(
            f"Plan {plan.full_name} completed: "
            f"{plan_result.steps_completed} completed, "
            f"{plan_result.steps_skipped} skipped, "
            f"{plan_result.steps_failed} failed "
            f"({total_time:.1f}ms)"
        )

        return plan_result

    async def execute_async(self, plan: AnalysisPlan, context: dict[str, Any]) -> PlanResult:
        """
        Plan 실행 (비동기)

        Args:
            plan: 실행할 Plan
            context: 실행 컨텍스트

        Returns:
            PlanResult: 실행 결과
        """
        # 동기 버전을 executor에서 실행
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.execute, plan, context)

    def _execute_step(
        self,
        step: PlanStep,
        context: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> StepResult:
        """
        단일 Step 실행

        Args:
            step: 실행할 Step
            context: 실행 컨텍스트
            previous_outputs: 이전 Step들의 출력

        Returns:
            StepResult: 실행 결과
        """
        start_time = time.time()

        # 1. 캐시 체크
        if step.config.skip_if_cached and self.cache:
            cache_key = self._make_cache_key(step, context, previous_outputs)
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Step '{step.name}' cache hit")
                return StepResult(
                    step_name=step.name,
                    status=StepStatus.COMPLETED,
                    data=cached,
                    was_cached=True,
                    execution_time_ms=0,
                )

        # 2. 입력 준비
        step_input = self._prepare_step_input(step, context, previous_outputs)

        # 3. 빈 입력 체크
        if step.config.skip_if_empty_input and self._is_empty_input(step_input):
            logger.debug(f"Step '{step.name}' skipped (empty input)")
            return StepResult(
                step_name=step.name,
                status=StepStatus.SKIPPED,
                error="Empty input",
            )

        # 4. AutoTool 파라미터 조정
        adjusted_config = step.config
        if self.auto_tool:
            adjusted_config = self.auto_tool.adjust_config(step.config, context)

        # 5. Tool 실행
        try:
            tool = self._get_tool(step.tool)
            if tool is None:
                # Fallback 시도
                if step.config.fallback_tool:
                    tool = self._get_tool(step.config.fallback_tool)
                    if tool:
                        logger.info(f"Step '{step.name}' using fallback: {step.config.fallback_tool}")

                if tool is None:
                    return StepResult(
                        step_name=step.name,
                        status=StepStatus.FAILED,
                        error=f"Tool '{step.tool}' not found",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )

            # Tool 실행
            result = tool.execute(
                **step_input,
                depth=adjusted_config.depth,
                max_results=adjusted_config.max_results,
                timeout_ms=adjusted_config.timeout_ms,
            )

            execution_time = (time.time() - start_time) * 1000

            if result.success:
                # 캐시 저장
                if self.cache and step.config.skip_if_cached:
                    cache_key = self._make_cache_key(step, context, previous_outputs)
                    self.cache.set(cache_key, result.data)

                return StepResult(
                    step_name=step.name,
                    status=StepStatus.COMPLETED,
                    data=result.data,
                    tool_used=step.tool,
                    execution_time_ms=execution_time,
                )
            else:
                return StepResult(
                    step_name=step.name,
                    status=StepStatus.FAILED,
                    error=result.error,
                    tool_used=step.tool,
                    execution_time_ms=execution_time,
                )

        except TimeoutError:
            execution_time = (time.time() - start_time) * 1000

            # Timeout fallback
            if step.config.fallback_on_timeout and step.config.fallback_tool:
                logger.warning(f"Step '{step.name}' timeout, trying fallback")
                fallback_tool = self._get_tool(step.config.fallback_tool)
                if fallback_tool:
                    try:
                        result = fallback_tool.execute(**step_input)
                        return StepResult(
                            step_name=step.name,
                            status=StepStatus.COMPLETED,
                            data=result.data,
                            tool_used=step.config.fallback_tool,
                            was_fallback=True,
                            execution_time_ms=(time.time() - start_time) * 1000,
                        )
                    except Exception as e:
                        logger.error(f"Fallback also failed: {e}")

            return StepResult(
                step_name=step.name,
                status=StepStatus.FAILED,
                error=f"Timeout ({step.config.timeout_ms}ms)",
                execution_time_ms=execution_time,
            )

        except Exception as e:
            return StepResult(
                step_name=step.name,
                status=StepStatus.FAILED,
                error=str(e),
                tool_used=step.tool,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _check_dependencies(self, step: PlanStep, previous_outputs: dict[str, Any]) -> bool:
        """
        Step 의존성 체크

        Args:
            step: 체크할 Step
            previous_outputs: 이전 Step 출력들

        Returns:
            True if all dependencies satisfied
        """
        for dep in step.depends_on:
            if dep not in previous_outputs:
                logger.debug(f"Step '{step.name}' missing dependency: {dep}")
                return False
        return True

    def _prepare_step_input(
        self,
        step: PlanStep,
        context: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Step 입력 데이터 준비

        Args:
            step: Step
            context: 전역 컨텍스트
            previous_outputs: 이전 Step 출력

        Returns:
            Tool에 전달할 입력 딕셔너리
        """
        # 기본: context 복사
        step_input = dict(context)

        # 의존성 데이터 추가
        for dep in step.depends_on:
            if dep in previous_outputs:
                step_input[f"from_{dep}"] = previous_outputs[dep]

        # 마지막 Step 출력 (편의성)
        if previous_outputs:
            last_key = list(previous_outputs.keys())[-1]
            step_input["previous_result"] = previous_outputs[last_key]

        return step_input

    def _get_tool(self, tool_name: str) -> Any:
        """Tool 가져오기 (Step Tool → Foundation Tool 순서로 검색)"""
        # 1. Step Tool 레지스트리에서 먼저 검색
        if tool_name in self._step_tools:
            return self._step_tools[tool_name]

        # 2. Foundation Tool 레지스트리에서 검색
        if self.tool_registry and hasattr(self.tool_registry, "get"):
            return self.tool_registry.get(tool_name)

        return None

    def _make_cache_key(
        self,
        step: PlanStep,
        context: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> str:
        """캐시 키 생성"""
        import hashlib
        import json

        key_data = {
            "step": step.name,
            "tool": step.tool,
            "context": context.get("target", ""),
            "deps": [previous_outputs.get(d, "") for d in step.depends_on],
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _is_empty_input(self, step_input: dict[str, Any]) -> bool:
        """입력이 비어있는지 체크"""
        # target이 없거나 비어있으면 빈 입력
        target = step_input.get("target")
        if not target:
            return True

        # previous_result가 빈 리스트면 빈 입력
        prev = step_input.get("previous_result")
        if isinstance(prev, list) and len(prev) == 0:
            return True

        return False

    def get_statistics(self) -> dict[str, Any]:
        """실행 통계"""
        return {
            "total_executions": self._execution_count,
            "total_steps_executed": self._total_steps_executed,
            "total_steps_skipped": self._total_steps_skipped,
        }


class AutoTool:
    """
    AutoTool - 파라미터 자동 조정

    RFC-041에서 정의된 역할:
    - Tool 파라미터 자동 조정 (depth, cost, timeout)
    - slice 범위 축소
    - cache hit 시 step skip
    - 비용 초과 시 fallback 전환

    AutoTool은 Tool 선택을 하지 않음!
    """

    def __init__(self, max_cost: float = 1.0, cost_model: Any | None = None):
        """
        Args:
            max_cost: 최대 허용 비용 (0-1 정규화)
            cost_model: 비용 추정 모델
        """
        self.max_cost = max_cost
        self.cost_model = cost_model

    def adjust_config(self, config: Any, context: dict[str, Any]) -> Any:
        """
        Step config 조정

        Args:
            config: 원본 StepConfig
            context: 실행 컨텍스트

        Returns:
            조정된 config
        """
        from .models import StepConfig

        # 비용 추정
        estimated_cost = self._estimate_cost(config, context)

        if estimated_cost > self.max_cost:
            # 비용 초과: depth 축소
            new_depth = max(1, config.depth - 1)
            logger.info(f"AutoTool: Reducing depth {config.depth} → {new_depth} (cost: {estimated_cost:.2f})")

            return StepConfig(
                depth=new_depth,
                max_results=min(config.max_results, 50),  # 결과 수도 축소
                timeout_ms=config.timeout_ms,
                skip_if_cached=config.skip_if_cached,
                skip_if_empty_input=config.skip_if_empty_input,
                fallback_tool=config.fallback_tool,
                fallback_on_timeout=config.fallback_on_timeout,
            )

        return config

    def _estimate_cost(self, config: Any, context: dict[str, Any]) -> float:
        """비용 추정 (0-1)"""
        if self.cost_model:
            return self.cost_model.estimate(config, context)

        # 간단한 휴리스틱
        depth_cost = config.depth / 10  # depth 10이면 1.0
        return min(1.0, depth_cost)
