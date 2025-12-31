"""
Critic Models

독립 평가를 위한 데이터 모델.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CriticConfig:
    """Critic 설정"""

    # Scoring
    use_reward_model: bool = True
    reward_weight: float = 0.6  # 보상 가중치
    quality_weight: float = 0.4  # 품질 가중치

    # Preference learning
    use_preference_learning: bool = False
    min_comparisons: int = 10  # 최소 비교 수


@dataclass
class CriticFeedback:
    """Critic 피드백"""

    # Scores
    overall_score: float  # 전체 점수 (0.0 ~ 1.0)
    reward: float  # 보상 점수
    quality: float  # 품질 점수

    # Detailed feedback
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    # Metadata
    confidence: float = 0.0  # 피드백 신뢰도


@dataclass
class CriticResult:
    """Critic 평가 결과"""

    # Candidate info
    candidate_id: str
    candidate_content: str

    # Feedback
    feedback: CriticFeedback

    # Ranking
    rank: int = 0  # 순위 (1-based)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def is_acceptable(self, threshold: float = 0.7) -> bool:
        """
        허용 가능한 품질인지

        Args:
            threshold: 임계값

        Returns:
            허용 여부
        """
        return self.feedback.overall_score >= threshold
