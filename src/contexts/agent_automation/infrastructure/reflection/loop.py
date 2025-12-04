"""
Improvement Loop - Reflection 기반 재시도 루프

결과가 품질 기준을 만족할 때까지 Reflection → Improve를 반복합니다.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.contexts.agent_automation.infrastructure.reflection.engine import ReflectionEngine
from src.contexts.agent_automation.infrastructure.types import ModeContext, Result, Task
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler

logger = get_logger(__name__)


class ImprovementLoop:
    """
    Improvement Loop - Reflection 기반 개선 반복.

    Agent가 품질 기준을 만족할 때까지 자동으로 재시도합니다.
    """

    def __init__(
        self,
        reflection_engine: ReflectionEngine,
        max_iterations: int = 3,
        enable_loop: bool = True,
    ):
        """
        Args:
            reflection_engine: Reflection 엔진
            max_iterations: 최대 반복 횟수
            enable_loop: Loop 활성화 여부 (비활성화 시 1회만 실행)
        """
        self.reflection_engine = reflection_engine
        self.max_iterations = max_iterations
        self.enable_loop = enable_loop

    async def run(
        self,
        task: Task,
        context: ModeContext,
        executor: Callable[[Task, ModeContext], Result],
    ) -> Result:
        """
        Improvement loop 실행.

        Args:
            task: 실행할 태스크
            context: 실행 컨텍스트
            executor: 실제 실행 함수 (mode handler의 execute)

        Returns:
            최종 개선된 Result
        """
        if not self.enable_loop:
            # Loop 비활성화 시 1회만 실행
            return await executor(task, context)

        iterations = 0
        current_result = None

        while iterations < self.max_iterations:
            iterations += 1
            logger.info(f"Improvement loop iteration {iterations}/{self.max_iterations}")

            # 1. 실행
            current_result = await executor(task, context)

            # 2. Reflection
            reflection = await self.reflection_engine.reflect(
                result=current_result,
                task=task,
                context=context,
            )

            # 3. 품질 기준 만족 시 종료
            if not reflection.needs_improvement:
                logger.info(
                    f"Quality threshold met (score: {reflection.quality_score:.2f}), "
                    f"stopping loop after {iterations} iterations"
                )
                break

            # 4. 개선 필요 시 피드백 추가하여 재시도
            if iterations < self.max_iterations:
                logger.info(f"Quality below threshold (score: {reflection.quality_score:.2f}), retrying with feedback")
                # Task에 피드백 추가
                task.context["reflection_feedback"] = {
                    "iteration": iterations,
                    "issues": reflection.issues,
                    "suggestions": reflection.suggestions,
                    "previous_score": reflection.quality_score,
                }
            else:
                logger.warning(
                    f"Max iterations ({self.max_iterations}) reached, final score: {reflection.quality_score:.2f}"
                )

        # 최종 결과에 메타데이터 추가
        if current_result:
            current_result.metadata["improvement_loop"] = {
                "iterations": iterations,
                "final_enabled": self.enable_loop,
            }

        return current_result or Result(
            mode=context.mode_history[-1] if context.mode_history else None,
            data={},
            trigger="error",
            explanation="Improvement loop failed to produce result",
        )

    async def run_with_handler(
        self,
        task: Task,
        context: ModeContext,
        handler: "BaseModeHandler",
    ) -> Result:
        """
        Mode handler를 사용한 improvement loop.

        Args:
            task: 실행할 태스크
            context: 실행 컨텍스트
            handler: Mode handler 인스턴스

        Returns:
            최종 개선된 Result
        """

        async def executor(t: Task, c: ModeContext) -> Result:
            return await handler.execute(t, c)

        return await self.run(task, context, executor)
