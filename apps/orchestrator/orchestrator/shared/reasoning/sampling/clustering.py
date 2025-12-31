"""
Clustering Engine

샘플을 클러스터링하여 다양성 확보.
"""

import hashlib
import logging
from collections.abc import Callable

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

try:
    from sklearn.cluster import KMeans

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    KMeans = None  # type: ignore

from .alphacode_models import AlphaCodeConfig, ClusterInfo, SampleCandidate

logger = logging.getLogger(__name__)


class ClusteringEngine:
    """샘플 클러스터링"""

    def __init__(self, config: AlphaCodeConfig):
        self.config = config

    def cluster(
        self,
        samples: list[SampleCandidate],
        embedding_fn: Callable[[SampleCandidate], list[float]] | None = None,
    ) -> list[ClusterInfo]:
        """
        샘플을 클러스터링

        Args:
            samples: 샘플 리스트
            embedding_fn: Custom embedding 함수 (RFC-017 Phase 3)
                         None이면 기본 hash 기반 embedding 사용

        Returns:
            클러스터 정보 리스트

        Raises:
            RuntimeError: sklearn or numpy not installed

        Note:
            RFC-017 Phase 3: embedding_fn으로 semantic embedding 지원
            - embedding_fn=None: Hash 기반 (70% quality, backward compatible)
            - embedding_fn=custom: AST+Semantic (95% quality)
        """
        if not samples:
            return []

        # Dependency check
        if not HAS_NUMPY:
            raise RuntimeError("numpy is required for clustering. Install: pip install numpy")

        if not HAS_SKLEARN:
            raise RuntimeError("scikit-learn is required for clustering. Install: pip install scikit-learn")

        # 1. 임베딩 생성 (RFC-017 Phase 3: custom or default)
        if embedding_fn is not None:
            # Custom embedding (semantic)
            embeddings = [embedding_fn(s) for s in samples]
            logger.info("Using custom embedding function (semantic)")
        else:
            # Default embedding (hash-based, backward compatible)
            embeddings = [self._get_embedding(s) for s in samples]
            logger.info("Using default embedding (hash-based)")

        embeddings_array = np.array(embeddings)

        # 2. 클러스터링 (K-means)
        try:
            from sklearn.cluster import KMeans

            n_clusters = min(self.config.num_clusters, len(samples))
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings_array)
            centroids = kmeans.cluster_centers_

        except ImportError:
            logger.warning("sklearn not available, using simple clustering")
            # Fallback: 단순 분할
            labels = np.array([i % self.config.num_clusters for i in range(len(samples))])
            n_clusters = self.config.num_clusters
            centroids = [embeddings[0]] * n_clusters  # 더미 centroid

        # 3. 클러스터별로 샘플 할당
        for i, label in enumerate(labels):
            samples[i].cluster_id = int(label)

        # 4. 각 클러스터의 대표 선택
        clusters: list[ClusterInfo] = []
        for cluster_id in range(n_clusters):
            cluster_samples = [s for s in samples if s.cluster_id == cluster_id]

            if not cluster_samples:
                continue

            # 대표 선택: 최고 점수
            representative = max(cluster_samples, key=lambda s: s.calculate_final_score())

            cluster_info = ClusterInfo(
                cluster_id=cluster_id,
                size=len(cluster_samples),
                centroid=centroids[cluster_id].tolist(),
                representative=representative,
            )
            clusters.append(cluster_info)

        logger.info(f"Clustered {len(samples)} samples into {len(clusters)} clusters")
        return clusters

    def _get_embedding(self, sample: SampleCandidate) -> list[float]:
        """
        샘플의 임베딩 생성 (간단 버전: 해시 기반)

        Args:
            sample: 샘플

        Returns:
            임베딩 벡터
        """
        # 코드의 해시를 벡터로 변환
        code_hash = hashlib.sha256(sample.code.encode()).digest()

        # 처음 32바이트를 float으로 변환 (8차원 벡터)
        embedding = []
        for i in range(0, min(32, len(code_hash)), 4):
            value = int.from_bytes(code_hash[i : i + 4], byteorder="big")
            # 0-1 범위로 정규화
            normalized = value / (2**32)
            embedding.append(normalized)

        # 8차원으로 맞추기
        while len(embedding) < 8:
            embedding.append(0.0)

        return embedding[:8]
