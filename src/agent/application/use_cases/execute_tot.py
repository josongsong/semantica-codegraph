"""
Execute Tree-of-Thought UseCase

Application Layer - ToT Orchestration
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from src.agent.domain.reasoning.tot_models import ToTResult

if TYPE_CHECKING:
    from src.agent.domain.reasoning.tot_scorer import ToTScoringEngine
    from src.agent.ports.reasoning import IToTExecutor

logger = logging.getLogger(__name__)


class ExecuteToTUseCase:
    """
    Tree-of-Thought 실행 UseCase (Application Layer)

    책임:
    1. 전략 생성 (Executor)
    2. 병렬 실행
    3. 점수 계산 (Scorer)
    4. Top-K 선택

    헥사고날:
    User → UseCase (App) → Scorer (Domain) + Executor (Adapter)
    """

    def __init__(
        self,
        tot_executor: "IToTExecutor",
        tot_scorer: "ToTScoringEngine",
    ):
        """
        Args:
            tot_executor: ToT Executor (Adapter)
            tot_scorer: ToT Scorer (Domain Service)
        """
        self._executor = tot_executor
        self._scorer = tot_scorer

        logger.info("ExecuteToTUseCase initialized")

    async def execute(
        self,
        problem: str,
        context: dict,
        strategy_count: int = 3,
        top_k: int = 1,
    ) -> ToTResult:
        """
        Tree-of-Thought 실행 (Full Pipeline)

        Steps:
        1. Generate N strategies (LLM)
        2. Execute strategies (Parallel)
        3. Score strategies (Multi-Criteria)
        4. Rank & Return Top-K

        Args:
            problem: 문제 설명
            context: 컨텍스트 (파일, 코드 등)
            strategy_count: 생성할 전략 수
            top_k: 반환할 상위 전략 수

        Returns:
            ToTResult
        """
        logger.info(f"Executing ToT: problem='{problem[:50]}...', strategies={strategy_count}, top_k={top_k}")

        start_time = time.time()

        # Step 1: Generate Strategies
        gen_start = time.time()
        strategies = await self._executor.generate_strategies(problem, context, count=strategy_count)
        gen_time = time.time() - gen_start

        logger.info(f"Generated {len(strategies)} strategies in {gen_time:.2f}s")

        # Step 2: Execute Strategies (Parallel)
        exec_start = time.time()
        execution_results = await self._execute_strategies_parallel(strategies)
        exec_time = time.time() - exec_start

        logger.info(f"Executed {len(execution_results)} strategies in {exec_time:.2f}s")

        # Step 3: Score & Rank
        tot_result = self._scorer.rank_strategies(strategies, execution_results)

        # Add timing
        tot_result.generation_time = gen_time
        tot_result.execution_time = exec_time
        tot_result.total_time = time.time() - start_time

        # Log Top-K
        top_strategies = tot_result.get_top_k(top_k)
        logger.info(f"Top {len(top_strategies)} strategies:")
        for i, (sid, score) in enumerate(top_strategies, 1):
            logger.info(f"  {i}. {sid}: {score.total_score:.2f} ({score.recommendation})")

        return tot_result

    async def _execute_strategies_parallel(self, strategies: list) -> dict:
        """
        전략들 병렬 실행

        Returns:
            {strategy_id: ExecutionResult}
        """
        tasks = [self._executor.execute_strategy(strategy) for strategy in strategies]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Dict로 변환
        results = {}
        for strategy, result in zip(strategies, results_list):
            if isinstance(result, Exception):
                logger.error(f"Strategy {strategy.strategy_id} failed: {result}")
                continue
            results[strategy.strategy_id] = result

        return results
