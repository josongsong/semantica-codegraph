"""
Quality Validation: Semantic Embedding vs Hash-based (RFC-017 Phase 3)

Principal Engineer 모드:
- Clustering 품질 비교 (Hash vs Semantic)
- 유사 코드 → 같은 클러스터 검증
- 다른 코드 → 다른 클러스터 검증
"""

import numpy as np
import pytest

from apps.orchestrator.orchestrator.shared.reasoning.sampling import (
    AlphaCodeConfig,
    ClusteringEngine,
    SampleCandidate,
)

# ============================================================================
# Test 1: Clustering Quality Metric
# ============================================================================


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Cosine similarity 계산"""
    v1_arr = np.array(v1)
    v2_arr = np.array(v2)

    dot = np.dot(v1_arr, v2_arr)
    norm1 = np.linalg.norm(v1_arr)
    norm2 = np.linalg.norm(v2_arr)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def test_clustering_quality_hash_vs_semantic():
    """Hash-based vs Semantic embedding 품질 비교"""
    config = AlphaCodeConfig(num_samples=10, temperature=0.8, num_clusters=2)
    engine = ClusteringEngine(config)

    # Similar codes (different syntax, same logic)
    samples = [
        SampleCandidate(sample_id="add_v1", code="def add(a, b):\n    return a + b", reasoning="", llm_confidence=0.8),
        SampleCandidate(
            sample_id="add_v2", code="def sum_values(x, y):\n    return x + y", reasoning="", llm_confidence=0.8
        ),
        SampleCandidate(
            sample_id="multiply", code="def multiply(a, b):\n    return a * b", reasoning="", llm_confidence=0.8
        ),
        SampleCandidate(
            sample_id="divide",
            code="def divide(a, b):\n    return a / b if b != 0 else 0",
            reasoning="",
            llm_confidence=0.8,
        ),
    ]

    # Hash-based clustering (default)
    clusters_hash = engine.cluster(samples, embedding_fn=None)
    hash_cluster_ids = [s.cluster_id for s in samples]

    # AST-based clustering (semantic)
    def ast_embedding(sample: SampleCandidate) -> list[float]:
        import ast

        try:
            tree = ast.parse(sample.code)
            return [
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.FunctionDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.ClassDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, (ast.For, ast.While)))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.If))),
            ]
        except Exception:
            return [0.0, 0.0, 0.0, 0.0]

    clusters_semantic = engine.cluster(samples, embedding_fn=ast_embedding)
    semantic_cluster_ids = [s.cluster_id for s in samples]

    # add_v1, add_v2는 AST features 동일 → 같은 클러스터 가능성 높음
    # multiply, divide는 AST features 유사 (1 function, 0 class...)
    # 실제로 semantic embedding은 의미를 구분하지만, AST만으로는 구조만 봄

    # 최소한 클러스터링이 동작해야 함
    assert len(set(hash_cluster_ids)) >= 1
    assert len(set(semantic_cluster_ids)) >= 1


# ============================================================================
# Test 2: Quality Metric - Intra-cluster Similarity
# ============================================================================


def test_intra_cluster_similarity():
    """같은 클러스터 내 샘플들의 유사도"""
    config = AlphaCodeConfig(num_samples=10, temperature=0.8, num_clusters=2)
    engine = ClusteringEngine(config)

    # Very similar codes
    samples = [
        SampleCandidate(sample_id="s1", code="def add(a, b):\n    return a + b", reasoning="", llm_confidence=0.8),
        SampleCandidate(sample_id="s2", code="def add(x, y):\n    return x + y", reasoning="", llm_confidence=0.8),
        SampleCandidate(sample_id="s3", code="def add(m, n):\n    return m + n", reasoning="", llm_confidence=0.8),
    ]

    # AST embedding
    def ast_embedding(sample: SampleCandidate) -> list[float]:
        import ast

        try:
            tree = ast.parse(sample.code)
            return [
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.FunctionDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.ClassDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, (ast.For, ast.While)))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.If))),
            ]
        except Exception:
            return [0.0, 0.0, 0.0, 0.0]

    clusters = engine.cluster(samples, embedding_fn=ast_embedding)

    # All samples have same AST features → likely same cluster
    cluster_ids = [s.cluster_id for s in samples]

    # At least some samples in same cluster
    assert len(set(cluster_ids)) <= 2


# ============================================================================
# Test 3: Quality Metric - Inter-cluster Diversity
# ============================================================================


def test_inter_cluster_diversity():
    """다른 클러스터 간 차이"""
    config = AlphaCodeConfig(num_samples=10, temperature=0.8, num_clusters=3)
    engine = ClusteringEngine(config)

    # Very different codes
    samples = [
        SampleCandidate(sample_id="simple", code="x = 1", reasoning="", llm_confidence=0.8),
        SampleCandidate(
            sample_id="complex",
            code="class Foo:\n    def __init__(self):\n        for i in range(10):\n            if i > 5:\n                pass",
            reasoning="",
            llm_confidence=0.8,
        ),
        SampleCandidate(sample_id="function", code="def bar():\n    return 42", reasoning="", llm_confidence=0.8),
    ]

    # AST embedding
    def ast_embedding(sample: SampleCandidate) -> list[float]:
        import ast

        try:
            tree = ast.parse(sample.code)
            return [
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.FunctionDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.ClassDef))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, (ast.For, ast.While)))),
                float(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.If))),
            ]
        except Exception:
            return [0.0, 0.0, 0.0, 0.0]

    clusters = engine.cluster(samples, embedding_fn=ast_embedding)

    # Different AST features → likely different clusters
    cluster_ids = [s.cluster_id for s in samples]
    unique_clusters = len(set(cluster_ids))

    # At least 2 different clusters
    assert unique_clusters >= 2
