"""
Execute LATS + Test Use Case (P0-2 RFC-B001)

LATS (Language Agent Tree Search) 기반
Tree Search + MCTS
Test 검증 루프
ShadowFS 격리 실행 통합
"""

import logging
import time
from pathlib import Path

from apps.orchestrator.orchestrator.adapters.codegen_adapter import CodeGenAdapter
from apps.orchestrator.orchestrator.adapters.sandbox.stub_sandbox import LocalSandboxAdapter
from apps.orchestrator.orchestrator.shared.reasoning.lats.lats_search import LATSSearchEngine
from apps.orchestrator.orchestrator.shared.reasoning.tot.tot_models import ToTWithTestResult

logger = logging.getLogger(__name__)


class ExecuteLATSWithTestUseCase:
    """
    LATS + Test 검증 루프 (RFC-B001 P0-2)

    Flow:
    1. LATS Tree Search로 전략들 생성 (MCTS)
    2. 점수순 정렬 (get_top_k)
    3. Top 전략부터 순차 시도
    4. Sandbox에서 테스트 실행
    5. 성공 시 종료, 실패 시 다음 전략
    """

    def __init__(
        self,
        search_engine: LATSSearchEngine,
        sandbox: LocalSandboxAdapter,
        max_attempts: int = 3,
        codegen_adapter: CodeGenAdapter | None = None,
        workspace_root: Path | None = None,
    ):
        """
        Args:
            search_engine: LATS Search Engine (Domain Service)
            sandbox: Sandbox 실행기
            max_attempts: 최대 시도 횟수
            codegen_adapter: CodeGen 어댑터 (ShadowFS 사용)
            workspace_root: 작업 디렉토리
        """
        self.search_engine = search_engine
        self.sandbox = sandbox
        self.max_attempts = max_attempts
        self.codegen_adapter = codegen_adapter or CodeGenAdapter(workspace_root=workspace_root or Path.cwd())

    async def execute(
        self,
        problem: str,
        context: dict,
        test_command: str = "pytest -v",
    ) -> ToTWithTestResult:
        """
        LATS + Test 실행

        Args:
            problem: 문제 설명
            context: 코드 컨텍스트
            test_command: 테스트 명령어

        Returns:
            ToTWithTestResult
        """
        start_time = time.time()
        generation_start = time.time()

        try:
            # 1. LATS Search로 전략들 생성 (MCTS)
            tot_result = await self.search_engine.search(
                problem=problem,
                context=context,
            )

            generation_time = time.time() - generation_start

            if not tot_result.all_strategies:
                return ToTWithTestResult(
                    success=False,
                    total_strategies=0,
                    error="No strategies generated",
                    generation_time=generation_time,
                    total_time=time.time() - start_time,
                )

            # 2. 점수순 정렬 (Top K)
            top_strategies = tot_result.get_top_k(k=self.max_attempts)

            logger.info(f"Generated {tot_result.total_generated} strategies, trying top {len(top_strategies)}")

            # 3. 검증 루프
            test_start = time.time()
            for attempt, (strategy_id, score) in enumerate(top_strategies, 1):
                # 전략 찾기
                strategy = next(
                    (s for s in tot_result.all_strategies if s.strategy_id == strategy_id),
                    None,
                )

                if not strategy:
                    logger.warning(f"Strategy {strategy_id} not found")
                    continue

                logger.info(
                    f"Attempt {attempt}/{len(top_strategies)}: {strategy.strategy_id} (score={score.confidence:.2f})"
                )

                # 3.1 파일 변경 (ShadowFS에서 격리 실행)
                try:
                    if strategy.file_changes:
                        codegen_result = await self.codegen_adapter.apply_changes_isolated(
                            file_changes=strategy.file_changes,
                        )
                        if not codegen_result.success:
                            logger.warning(f"Failed to apply changes via ShadowFS: {codegen_result.error}")
                            continue
                except (ValueError, RuntimeError) as e:
                    logger.warning(f"Failed to apply changes: {e}")
                    continue

                # 3.2 테스트 실행
                test_result = await self._run_tests(test_command)

                # 3.3 결과 확인
                if test_result["exit_code"] == 0:
                    # 성공

                    test_time = time.time() - test_start

                    return ToTWithTestResult(
                        success=True,
                        selected_strategy=strategy,
                        selected_score=score.confidence,
                        attempts=attempt,
                        total_strategies=tot_result.total_generated,
                        test_output=test_result["stdout"],
                        test_exit_code=0,
                        generation_time=generation_time,
                        test_time=test_time,
                        total_time=time.time() - start_time,
                    )

                # 실패 → 다음 시도
                logger.warning(f"Test failed (exit={test_result['exit_code']}): {test_result['stderr'][:200]}")

            # 모든 시도 실패
            test_time = time.time() - test_start

            return ToTWithTestResult(
                success=False,
                attempts=len(top_strategies),
                total_strategies=tot_result.total_generated,
                error="All strategies failed tests",
                generation_time=generation_time,
                test_time=test_time,
                total_time=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"LATS+Test execution failed: {e}", exc_info=True)

            return ToTWithTestResult(
                success=False,
                total_strategies=0,
                error=str(e),
                total_time=time.time() - start_time,
            )

    async def _run_tests(self, test_command: str) -> dict:
        """
        테스트 실행

        Args:
            test_command: 테스트 명령어

        Returns:
            {"stdout": str, "stderr": str, "exit_code": int}
        """
        sandbox_id = await self.sandbox.create_sandbox()

        try:
            # Python subprocess로 테스트 실행
            import shlex

            python_code = f"""
import subprocess
import sys

result = subprocess.run(
    {repr(shlex.split(test_command))},
    capture_output=True,
    text=True,
)

print(result.stdout, end='')
print(result.stderr, end='', file=sys.stderr)
sys.exit(result.returncode)
"""
            result = await self.sandbox.execute_code(
                sandbox_id,
                python_code,
                language="python",
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
            }

        finally:
            await self.sandbox.destroy_sandbox(sandbox_id)
