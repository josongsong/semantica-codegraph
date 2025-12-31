"""
r1 Engine

DeepSeek r1 스타일 추론 엔진.
- o1 베이스 + RL 기반 최적화
- 보상 기반 단계 선택
"""

import logging
import time
from collections.abc import Callable

from .deep_models import (
    DeepReasoningConfig,
    DeepReasoningResult,
    ReasoningStep,
    VerificationResult,
)
from .o1_engine import O1Engine

logger = logging.getLogger(__name__)


class R1Engine(O1Engine):
    """r1 스타일 추론 엔진 (o1 확장)"""

    def __init__(self, config: DeepReasoningConfig | None = None):
        super().__init__(config)
        self.reward_history: list[float] = []

    async def reason_with_rl(
        self,
        problem: str,
        answer_fn: Callable[[str], str],
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
        reward_fn: Callable[[ReasoningStep], float],
    ) -> DeepReasoningResult:
        """
        r1 스타일 추론 실행 (RL 기반)

        Args:
            problem: 문제
            answer_fn: 답변 생성 함수
            verify_fn: 검증 함수
            refine_fn: 개선 함수
            reward_fn: 보상 함수

        Returns:
            추론 결과
        """
        start_time = time.time()
        logger.info(f"r1 reasoning started for: {problem[:100]}...")

        # 1. 기본 o1 추론 실행
        result = await self.reason(problem, answer_fn, verify_fn, refine_fn)

        # 2. 보상 기반 최적화
        logger.info("Optimizing with reward-based selection...")
        optimized_steps = self._optimize_with_rewards(result.reasoning_steps, reward_fn)

        # 3. 최종 답변 재합성
        final_answer = self._synthesize_answer(optimized_steps)
        final_code = self._extract_code(optimized_steps)

        reasoning_time = time.time() - start_time

        # 결과 업데이트
        result.reasoning_steps = optimized_steps
        result.final_answer = final_answer
        result.final_code = final_code
        result.reasoning_time = reasoning_time

        logger.info(f"r1 reasoning completed in {reasoning_time:.2f}s: {len(optimized_steps)} steps")

        return result

    def _optimize_with_rewards(
        self,
        steps: list[ReasoningStep],
        reward_fn: Callable[[ReasoningStep], float],
    ) -> list[ReasoningStep]:
        """
        보상 기반으로 단계 최적화

        Args:
            steps: 추론 단계들
            reward_fn: 보상 함수

        Returns:
            최적화된 단계들
        """
        # 각 단계에 보상 계산
        step_rewards = []
        for step in steps:
            try:
                reward = reward_fn(step)
                step_rewards.append((step, reward))
                self.reward_history.append(reward)
            except Exception as e:
                logger.warning(f"Failed to compute reward: {e}")
                step_rewards.append((step, 0.0))

        # 보상이 낮은 단계 제거 (하위 20%)
        sorted_steps = sorted(step_rewards, key=lambda x: x[1], reverse=True)
        threshold_idx = int(len(sorted_steps) * 0.8)
        optimized = [step for step, _ in sorted_steps[:threshold_idx]]

        # 원래 순서 유지
        optimized.sort(key=lambda s: s.step_number)

        logger.info(
            f"Optimized from {len(steps)} to {len(optimized)} steps "
            f"(avg reward: {sum(r for _, r in step_rewards) / len(step_rewards):.2f})"
        )

        return optimized

    def get_average_reward(self) -> float:
        """
        평균 보상 반환

        Returns:
            평균 보상
        """
        if not self.reward_history:
            return 0.0
        return sum(self.reward_history) / len(self.reward_history)

    def reason_with_rl_sync(
        self,
        problem: str,
        answer_fn: Callable[[str], str],
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
        reward_fn: Callable[[ReasoningStep], float],
    ) -> DeepReasoningResult:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.reason_with_rl(problem, answer_fn, verify_fn, refine_fn, reward_fn))
