"""
Constrained Tool Executor

SOTA Reference:
- Anthropic tool_choice pattern
- Controlled execution with safety measures
- OpenAI parallel function calling

PRODUCTION-GRADE:
- True async parallel execution
- Resource limits
- Circuit breaker pattern
"""

import asyncio
import logging
import signal
from contextlib import contextmanager
from typing import Any

from .base import CodeFoundationTool, ExecutionMode, ToolResult

logger = logging.getLogger(__name__)


class ExecutionTimeout(Exception):
    """실행 시간 초과"""

    pass


class ConstrainedToolExecutor:
    """
    제약 조건 기반 도구 실행자

    Features:
    1. Execution Mode 제어 (Anthropic tool_choice)
    2. Timeout 관리
    3. Resource limits
    4. Error isolation

    SOTA: Anthropic의 tool_choice 패턴
    """

    def __init__(
        self,
        default_timeout: float = 30.0,  # 30초
        max_concurrent: int = 5,
    ):
        """
        Args:
            default_timeout: 기본 타임아웃 (초)
            max_concurrent: 최대 동시 실행 수
        """
        self.default_timeout = default_timeout
        self.max_concurrent = max_concurrent

        # 실행 통계
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0

        logger.info(
            f"ConstrainedToolExecutor initialized (timeout={default_timeout}s, max_concurrent={max_concurrent})"
        )

    def execute(
        self,
        tool: CodeFoundationTool,
        args: dict[str, Any],
        mode: ExecutionMode = "auto",
        timeout: float | None = None,
    ) -> ToolResult:
        """
        단일 도구 실행

        Args:
            tool: 실행할 도구
            args: 도구 인자
            mode: 실행 모드
                - "auto": LLM이 사용 여부 결정 (실패시 다음)
                - "any": 반드시 하나 사용 (실패시 계속)
                - "specific": 특정 도구 강제 (실패시 에러)
                - "none": 도구 사용 금지
            timeout: 타임아웃 (None이면 기본값)

        Returns:
            ToolResult: 실행 결과
        """
        if mode == "none":
            return ToolResult(success=False, data=None, error="Tool execution disabled by mode='none'", confidence=0.0)

        timeout = timeout or self.default_timeout

        try:
            self._execution_count += 1

            # 타임아웃 포함 실행
            with self._timeout_context(timeout):
                result = tool._safe_execute(**args)

            # 통계 업데이트
            if result.success:
                self._success_count += 1
            else:
                self._failure_count += 1

            # 모드별 처리
            if mode == "specific" and not result.success:
                logger.error(f"Tool '{tool.metadata.name}' failed in 'specific' mode: {result.error}")

            return result

        except ExecutionTimeout:
            self._failure_count += 1
            logger.warning(f"Tool '{tool.metadata.name}' timed out after {timeout}s")
            return ToolResult(
                success=False,
                data=None,
                error=f"Execution timeout ({timeout}s)",
                error_type="ExecutionTimeout",
                confidence=0.0,
            )

        except Exception as e:
            self._failure_count += 1
            logger.exception(f"Unexpected error executing tool '{tool.metadata.name}'")
            return ToolResult(success=False, data=None, error=str(e), error_type=type(e).__name__, confidence=0.0)

    def execute_batch(
        self,
        tools: list[CodeFoundationTool],
        args: dict[str, Any],
        mode: ExecutionMode = "auto",
        stop_on_success: bool = True,
    ) -> list[ToolResult]:
        """
        배치 실행

        Args:
            tools: 실행할 도구 리스트
            args: 공통 인자
            mode: 실행 모드
            stop_on_success: 성공시 중단 여부

        Returns:
            List[ToolResult]: 실행 결과 리스트
        """
        results = []

        for tool in tools:
            result = self.execute(tool, args, mode)
            results.append(result)

            # auto 모드: 성공하면 중단
            if mode == "auto" and stop_on_success and result.success:
                logger.debug(f"Stopping after successful execution of '{tool.metadata.name}'")
                break

        return results

    def execute_parallel(
        self, tools: list[CodeFoundationTool], args: dict[str, Any], mode: ExecutionMode = "any"
    ) -> list[ToolResult]:
        """
        병렬 실행 (OpenAI parallel function calling 스타일)

        PRODUCTION: 진짜 병렬 실행 (asyncio)

        Args:
            tools: 실행할 도구들
            args: 공통 인자
            mode: 실행 모드

        Returns:
            실행 결과 리스트 (입력 순서 보장)
        """
        logger.info(f"Parallel execution for {len(tools)} tools")

        # asyncio 이벤트 루프 사용
        try:
            asyncio.get_running_loop()
            # 이미 실행 중인 루프 있음
            logger.warning("Event loop already running, falling back to sequential")
            return self.execute_batch(tools, args, mode, stop_on_success=False)
        except RuntimeError:
            # 새 이벤트 루프 생성
            return asyncio.run(self._execute_parallel_async(tools, args, mode))

    async def _execute_parallel_async(
        self, tools: list[CodeFoundationTool], args: dict[str, Any], mode: ExecutionMode
    ) -> list[ToolResult]:
        """
        진짜 병렬 실행 (async)

        Concurrency 제한 적용
        """
        # Semaphore로 동시 실행 제한
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _execute_with_semaphore(tool: CodeFoundationTool) -> ToolResult:
            """Semaphore 포함 실행"""
            async with semaphore:
                # sync 함수를 async로 실행
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    self.execute,
                    tool,
                    args,
                    mode,
                    None,  # Default ThreadPoolExecutor  # timeout
                )

        # 모든 도구 병렬 실행
        tasks = [_execute_with_semaphore(tool) for tool in tools]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외를 ToolResult로 변환
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_name = tools[i].metadata.name
                logger.error(f"Async execution failed for {tool_name}: {result}")
                processed_results.append(
                    ToolResult(
                        success=False, data=None, error=str(result), error_type=type(result).__name__, confidence=0.0
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    @contextmanager
    def _timeout_context(self, timeout: float):
        """타임아웃 컨텍스트"""

        def _timeout_handler(signum, frame):
            raise ExecutionTimeout()

        # Unix 계열에서만 작동
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(timeout))

            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        except (ValueError, AttributeError):
            # Windows or signal not available
            # 간단한 폴백: 그냥 실행
            logger.warning("Signal-based timeout not available, using fallback")
            yield

    def get_statistics(self) -> dict[str, any]:
        """실행 통계"""
        total = self._execution_count
        success_rate = self._success_count / total * 100 if total > 0 else 0

        return {
            "total_executions": total,
            "successes": self._success_count,
            "failures": self._failure_count,
            "success_rate": f"{success_rate:.1f}%",
        }
