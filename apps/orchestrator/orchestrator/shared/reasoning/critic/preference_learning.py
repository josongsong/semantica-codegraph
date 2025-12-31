"""
Preference Learning

인간 피드백 기반 선호도 학습.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PreferenceLearning:
    """선호도 학습"""

    def __init__(self):
        self.comparisons: list[tuple[Any, Any, int]] = []  # (a, b, winner: 0 or 1)

    def add_comparison(self, candidate_a: Any, candidate_b: Any, winner: int) -> None:
        """
        비교 결과 추가

        Args:
            candidate_a: 후보 A
            candidate_b: 후보 B
            winner: 승자 (0=A, 1=B)
        """
        self.comparisons.append((candidate_a, candidate_b, winner))
        logger.debug(f"Added comparison: winner={winner}")

    def predict_preference(self, candidate_a: Any, candidate_b: Any) -> int:
        """
        선호도 예측

        Args:
            candidate_a: 후보 A
            candidate_b: 후보 B

        Returns:
            예측 승자 (0=A, 1=B)
        """
        # 간단한 휴리스틱: 과거 비교 기반
        if not self.comparisons:
            return 0  # 기본값

        # 유사한 비교 찾기
        similar_comparisons = [winner for _, _, winner in self.comparisons[-10:]]  # 최근 10개

        # 다수결
        a_wins = similar_comparisons.count(0)
        b_wins = similar_comparisons.count(1)

        return 0 if a_wins >= b_wins else 1

    def get_win_rate(self, candidate: Any) -> float:
        """
        후보의 승률 계산

        Args:
            candidate: 후보

        Returns:
            승률 (0.0 ~ 1.0)
        """
        if not self.comparisons:
            return 0.5

        # 간단한 근사: 전체 승률
        total_comparisons = len(self.comparisons)
        a_wins = sum(1 for _, _, winner in self.comparisons if winner == 0)

        return a_wins / total_comparisons
