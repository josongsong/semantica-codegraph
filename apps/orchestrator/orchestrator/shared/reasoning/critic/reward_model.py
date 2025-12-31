"""
Reward Model

RL 기반 보상 모델.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RewardModel:
    """보상 모델"""

    def __init__(self):
        self.reward_history: list[float] = []

    def calculate_reward(self, candidate: Any) -> float:
        """
        후보의 보상 계산

        Args:
            candidate: 평가할 후보

        Returns:
            보상 점수 (0.0 ~ 1.0)
        """
        # 간단한 휴리스틱 기반 보상
        reward = 0.0

        # 1. 컴파일 성공 여부
        if hasattr(candidate, "compile_success") and candidate.compile_success:
            reward += 0.3

        # 2. 테스트 통과율
        if hasattr(candidate, "test_pass_rate"):
            reward += candidate.test_pass_rate * 0.4

        # 3. 코드 품질
        if hasattr(candidate, "quality_score"):
            reward += candidate.quality_score * 0.3

        # 정규화
        reward = max(0.0, min(reward, 1.0))

        self.reward_history.append(reward)
        logger.debug(f"Calculated reward: {reward:.2f}")

        return reward

    def get_average_reward(self) -> float:
        """
        평균 보상 반환

        Returns:
            평균 보상
        """
        if not self.reward_history:
            return 0.0
        return sum(self.reward_history) / len(self.reward_history)
