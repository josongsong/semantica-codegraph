"""
Consensus Builder

토론 포지션들로부터 합의를 도출.
"""

import logging

from .debate_models import DebateConfig, Position

logger = logging.getLogger(__name__)


class ConsensusBuilder:
    """합의 구축기"""

    def __init__(self, config: DebateConfig):
        self.config = config

    def build_consensus(self, positions: list[Position]) -> tuple[bool, float, str]:
        """
        합의 구축

        Args:
            positions: 포지션 리스트

        Returns:
            (합의 도달 여부, 합의 점수, 합의 내용)
        """
        if not positions:
            return False, 0.0, ""

        # 1. 합의 점수 계산
        agreement_score = self._calculate_agreement_score(positions)

        # 2. 합의 도달 여부
        consensus_reached = agreement_score >= self.config.consensus_threshold

        # 3. 합의 내용 생성
        if consensus_reached:
            consensus_content = self._synthesize_consensus(positions)
        else:
            consensus_content = ""

        logger.info(f"Consensus: reached={consensus_reached}, score={agreement_score:.2f}")

        return consensus_reached, agreement_score, consensus_content

    def _calculate_agreement_score(self, positions: list[Position]) -> float:
        """
        합의 점수 계산

        Args:
            positions: 포지션 리스트

        Returns:
            합의 점수 (0.0 ~ 1.0)
        """
        if len(positions) < 2:
            return 1.0  # 포지션이 하나면 자동 합의

        # 간단한 합의 측정: 평균 신뢰도
        avg_confidence = sum(p.confidence for p in positions) / len(positions)

        # 반대 의견 수 확인
        total_opposing = sum(len(p.opposing_points) for p in positions)
        opposing_penalty = min(total_opposing * 0.1, 0.5)

        score = avg_confidence - opposing_penalty
        return max(0.0, min(score, 1.0))

    def _synthesize_consensus(self, positions: list[Position]) -> str:
        """
        합의 내용 합성

        Args:
            positions: 포지션 리스트

        Returns:
            합의 내용
        """
        # 가장 높은 신뢰도의 포지션 선택
        best_position = max(positions, key=lambda p: p.confidence)
        return best_position.content
