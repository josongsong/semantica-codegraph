"""
Beam Search Models

Beam search를 위한 데이터 모델들.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BeamConfig:
    """Beam Search 설정"""

    beam_width: int = 5  # 각 단계에서 유지할 후보 수
    max_depth: int = 3  # 최대 탐색 깊이
    temperature: float = 0.7  # 샘플링 온도
    diversity_penalty: float = 0.1  # 다양성 페널티


@dataclass
class BeamCandidate:
    """Beam Search 후보"""

    # Identity
    candidate_id: str
    depth: int  # 현재 깊이
    parent_id: str | None = None

    # Content
    code_diff: str = ""
    reasoning: str = ""

    # Scores
    score: float = 0.0  # 누적 점수
    log_prob: float = 0.0  # 로그 확률
    quality_score: float = 0.0  # 품질 점수

    # Execution
    compile_success: bool = False
    test_pass_rate: float = 0.0
    lint_errors: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def calculate_final_score(self, diversity_penalty: float = 0.0) -> float:
        """
        최종 점수 계산

        Args:
            diversity_penalty: 다양성 페널티 (중복 후보 방지)

        Returns:
            최종 점수
        """
        if not self.compile_success:
            return 0.0

        # 기본 점수 = 로그 확률 + 품질 점수
        base_score = (self.log_prob * 0.3) + (self.quality_score * 0.7)

        # 다양성 페널티 적용
        final_score = base_score - diversity_penalty

        return max(final_score, 0.0)

    def is_valid(self) -> bool:
        """유효한 후보인지 확인"""
        return self.compile_success and self.test_pass_rate >= 0.5


@dataclass
class BeamSearchResult:
    """Beam Search 결과"""

    # Best candidate
    best_candidate: BeamCandidate | None = None

    # All candidates explored
    all_candidates: list[BeamCandidate] = field(default_factory=list)

    # Metrics
    total_candidates: int = 0
    valid_candidates: int = 0
    search_time: float = 0.0

    # Beam statistics
    avg_beam_size: float = 0.0
    max_depth_reached: int = 0

    def get_top_k(self, k: int = 3) -> list[BeamCandidate]:
        """
        상위 k개 후보 반환

        Args:
            k: 반환할 후보 수

        Returns:
            상위 k개 후보
        """
        valid = [c for c in self.all_candidates if c.is_valid()]
        sorted_candidates = sorted(valid, key=lambda c: c.score, reverse=True)
        return sorted_candidates[:k]

    def get_diversity_score(self) -> float:
        """
        다양성 점수 계산

        Returns:
            다양성 점수 (0.0 ~ 1.0)
        """
        if not self.all_candidates:
            return 0.0

        # 간단한 다양성 측정: 고유한 reasoning 개수 / 전체 개수
        unique_reasonings = len({c.reasoning for c in self.all_candidates})
        return unique_reasonings / len(self.all_candidates)
