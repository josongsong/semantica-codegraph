"""
Critic Model

독립 평가 모델의 메인 클래스.
"""

import logging
from typing import Any

from .critic_models import CriticConfig, CriticFeedback, CriticResult
from .preference_learning import PreferenceLearning
from .reward_model import RewardModel

logger = logging.getLogger(__name__)


class CriticModel:
    """Critic 평가 모델"""

    def __init__(self, config: CriticConfig | None = None):
        self.config = config or CriticConfig()
        self.reward_model = RewardModel()
        self.preference_learning = PreferenceLearning()

    def evaluate(self, candidate: Any) -> CriticResult:
        """
        후보 평가

        Args:
            candidate: 평가할 후보

        Returns:
            평가 결과
        """
        # 1. 보상 계산
        reward = 0.0
        if self.config.use_reward_model:
            reward = self.reward_model.calculate_reward(candidate)

        # 2. 품질 계산
        quality = self._calculate_quality(candidate)

        # 3. 전체 점수
        overall_score = reward * self.config.reward_weight + quality * self.config.quality_weight

        # 4. 상세 피드백 생성
        strengths, weaknesses, suggestions = self._generate_detailed_feedback(candidate, reward, quality)

        feedback = CriticFeedback(
            overall_score=overall_score,
            reward=reward,
            quality=quality,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            confidence=0.8,  # 기본값
        )

        # 5. 결과 생성
        result = CriticResult(
            candidate_id=getattr(candidate, "candidate_id", "unknown"),
            candidate_content=str(candidate)[:200],
            feedback=feedback,
        )

        logger.debug(f"Evaluated candidate: score={overall_score:.2f}, reward={reward:.2f}, quality={quality:.2f}")

        return result

    def evaluate_batch(self, candidates: list[Any]) -> list[CriticResult]:
        """
        여러 후보 평가 및 랭킹

        Args:
            candidates: 후보 리스트

        Returns:
            평가 결과 리스트 (랭킹 순)
        """
        results = [self.evaluate(c) for c in candidates]

        # 점수로 정렬
        results.sort(key=lambda r: r.feedback.overall_score, reverse=True)

        # 순위 부여
        for rank, result in enumerate(results, start=1):
            result.rank = rank

        logger.info(f"Evaluated {len(candidates)} candidates, best_score={results[0].feedback.overall_score:.2f}")

        return results

    def _calculate_quality(self, candidate: Any) -> float:
        """품질 계산"""
        quality = 0.5  # 기본값

        if hasattr(candidate, "quality_score"):
            quality = candidate.quality_score
        elif hasattr(candidate, "test_pass_rate"):
            quality = candidate.test_pass_rate

        return quality

    def _generate_detailed_feedback(
        self, candidate: Any, reward: float, quality: float
    ) -> tuple[list[str], list[str], list[str]]:
        """상세 피드백 생성"""
        strengths = []
        weaknesses = []
        suggestions = []

        # 강점
        if reward > 0.7:
            strengths.append("High reward score")
        if quality > 0.7:
            strengths.append("Good quality")

        # 약점
        if reward < 0.5:
            weaknesses.append("Low reward score")
        if quality < 0.5:
            weaknesses.append("Quality needs improvement")

        # 제안
        if reward < 0.7:
            suggestions.append("Consider improving test coverage")
        if quality < 0.7:
            suggestions.append("Refactor for better code quality")

        return strengths, weaknesses, suggestions
