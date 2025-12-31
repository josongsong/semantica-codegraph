"""
AlphaCode Sampling Models

대량 샘플링을 위한 데이터 모델들.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AlphaCodeConfig:
    """AlphaCode 샘플링 설정"""

    num_samples: int = 100  # 생성할 샘플 수
    temperature: float = 0.8  # 높은 온도로 다양성 확보
    top_p: float = 0.95

    # Clustering
    num_clusters: int = 10  # 클러스터 개수
    cluster_method: str = "kmeans"  # "kmeans", "dbscan"

    # Filtering
    min_compile_rate: float = 0.7  # 최소 컴파일 성공률
    max_candidates: int = 10  # 최종 후보 수


@dataclass
class SampleCandidate:
    """샘플 후보"""

    # Identity
    sample_id: str
    cluster_id: int = -1  # 클러스터 ID (-1 = 미할당)

    # Content
    code: str = ""
    reasoning: str = ""

    # Execution
    compile_success: bool = False
    test_pass_rate: float = 0.0
    execution_time: float = 0.0

    # Scores
    similarity_score: float = 0.0  # 클러스터 중심과의 유사도
    quality_score: float = 0.0
    llm_confidence: float = 0.0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def is_valid(self) -> bool:
        """유효한 후보인지"""
        return self.compile_success and self.test_pass_rate >= 0.5

    def calculate_final_score(self) -> float:
        """
        최종 점수 계산

        Returns:
            최종 점수 (0.0 ~ 1.0)
        """
        if not self.compile_success:
            return 0.0

        # 테스트 통과율 50% + 품질 30% + LLM 신뢰도 20%
        score = self.test_pass_rate * 0.5 + self.quality_score * 0.3 + self.llm_confidence * 0.2

        return min(score, 1.0)


@dataclass
class ClusterInfo:
    """클러스터 정보"""

    cluster_id: int
    size: int
    centroid: list[float]  # 임베딩 중심
    representative: SampleCandidate | None = None  # 대표 후보


@dataclass
class AlphaCodeResult:
    """AlphaCode 샘플링 결과"""

    # Best candidate
    best_candidate: SampleCandidate | None = None

    # All samples
    all_samples: list[SampleCandidate] = field(default_factory=list)

    # Clusters
    clusters: list[ClusterInfo] = field(default_factory=list)

    # Metrics
    total_samples: int = 0
    valid_samples: int = 0
    compile_rate: float = 0.0
    avg_test_pass_rate: float = 0.0

    # Timing
    sampling_time: float = 0.0
    clustering_time: float = 0.0
    evaluation_time: float = 0.0

    def get_top_k(self, k: int = 5) -> list[SampleCandidate]:
        """
        상위 k개 후보 반환

        Args:
            k: 반환할 개수

        Returns:
            상위 k개
        """
        valid = [s for s in self.all_samples if s.is_valid()]
        sorted_samples = sorted(valid, key=lambda s: s.calculate_final_score(), reverse=True)
        return sorted_samples[:k]

    def get_cluster_representatives(self) -> list[SampleCandidate]:
        """
        각 클러스터의 대표 후보 반환

        Returns:
            대표 후보 리스트
        """
        representatives = [c.representative for c in self.clusters if c.representative is not None]
        return representatives
