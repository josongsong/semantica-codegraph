"""
Budget Optimizer

예산 사용을 최적화하는 로직.
"""

import logging

from .ttc_models import ComputeBudget, TTCResult

logger = logging.getLogger(__name__)


class BudgetOptimizer:
    """예산 최적화기"""

    def __init__(self):
        self.history: list[TTCResult] = []

    def record_result(self, result: TTCResult) -> None:
        """
        결과 기록

        Args:
            result: TTC 결과
        """
        self.history.append(result)

    def optimize_budget(self, current_budget: ComputeBudget) -> ComputeBudget:
        """
        과거 결과를 바탕으로 예산 최적화

        Args:
            current_budget: 현재 예산

        Returns:
            최적화된 예산
        """
        if not self.history:
            return current_budget

        # 최근 10개 결과 분석
        recent = self.history[-10:]

        # 평균 사용량 계산
        avg_samples = sum(r.actual_samples for r in recent) / len(recent)
        avg_steps = sum(r.actual_reasoning_steps for r in recent) / len(recent)
        sum(r.actual_tokens for r in recent) / len(recent)

        # 성공률 계산
        success_rate = sum(1 for r in recent if r.success) / len(recent)

        logger.info(
            f"Budget optimization: success_rate={success_rate:.2%}, "
            f"avg_samples={avg_samples:.1f}, avg_steps={avg_steps:.1f}"
        )

        # 최적화 로직
        optimized = ComputeBudget(
            num_samples=current_budget.num_samples,
            temperature=current_budget.temperature,
            max_reasoning_steps=current_budget.max_reasoning_steps,
            max_verification_attempts=current_budget.max_verification_attempts,
            max_tokens=current_budget.max_tokens,
            max_time_seconds=current_budget.max_time_seconds,
        )

        # 성공률이 높으면 예산 감소
        if success_rate > 0.9:
            optimized.num_samples = max(1, int(avg_samples * 1.2))
            optimized.max_reasoning_steps = max(1, int(avg_steps * 1.2))
            logger.info("High success rate, reducing budget")

        # 성공률이 낮으면 예산 증가
        elif success_rate < 0.5:
            optimized.num_samples = int(current_budget.num_samples * 1.5)
            optimized.max_reasoning_steps = int(current_budget.max_reasoning_steps * 1.3)
            logger.info("Low success rate, increasing budget")

        return optimized

    def get_average_efficiency(self) -> float:
        """
        평균 효율성 반환

        Returns:
            평균 효율성
        """
        if not self.history:
            return 0.0

        efficiencies = [r.calculate_efficiency() for r in self.history]
        return sum(efficiencies) / len(efficiencies)
