"""
LTR A/B Test

Learning to Rank weight set A/B 테스트.
Phase 2 Day 16-17: 주간 자동 실행으로 최적 weight 발견
"""

from dataclasses import dataclass
from datetime import datetime

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class WeightSet:
    """Weight set for LTR."""

    name: str
    weights: dict[str, float]  # {"lexical": 0.3, "vector": 0.4, "symbol": 0.3}
    description: str = ""


@dataclass
class ABTestResult:
    """A/B test result."""

    baseline_name: str
    candidate_name: str

    # Baseline metrics
    baseline_precision: float
    baseline_recall: float
    baseline_mrr: float

    # Candidate metrics
    candidate_precision: float
    candidate_recall: float
    candidate_mrr: float

    # Improvements
    precision_improvement_pct: float
    recall_improvement_pct: float
    mrr_improvement_pct: float

    # Winner
    is_winner: bool
    winner_name: str

    # Metadata
    query_count: int
    tested_at: str

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "baseline": {
                "name": self.baseline_name,
                "precision": self.baseline_precision,
                "recall": self.baseline_recall,
                "mrr": self.baseline_mrr,
            },
            "candidate": {
                "name": self.candidate_name,
                "precision": self.candidate_precision,
                "recall": self.candidate_recall,
                "mrr": self.candidate_mrr,
            },
            "improvements": {
                "precision_pct": self.precision_improvement_pct,
                "recall_pct": self.recall_improvement_pct,
                "mrr_pct": self.mrr_improvement_pct,
            },
            "winner": self.winner_name,
            "is_significant": self.is_winner,
            "query_count": self.query_count,
            "tested_at": self.tested_at,
        }


class LTRABTest:
    """
    LTR A/B 테스트 실행기.

    기능:
    - Baseline vs Candidate weight set 비교
    - Golden set 기반 평가
    - Precision/Recall/MRR 개선율 계산
    - 통계적 유의성 판단 (임계치 기반)
    """

    def __init__(
        self,
        improvement_threshold_pct: float = 2.0,  # 2% 이상 개선 시 승자
        min_query_count: int = 10,  # 최소 쿼리 수
    ):
        """
        Initialize A/B test runner.

        Args:
            improvement_threshold_pct: Improvement threshold (%)
            min_query_count: Minimum number of queries for valid test
        """
        self.improvement_threshold = improvement_threshold_pct
        self.min_query_count = min_query_count

    async def compare_weight_sets(
        self,
        baseline: WeightSet,
        candidate: WeightSet,
        golden_set_queries: list[dict],
        retriever_fn,
    ) -> ABTestResult:
        """
        Compare two weight sets using golden set.

        Args:
            baseline: Baseline weight set
            candidate: Candidate weight set
            golden_set_queries: List of golden set queries
            retriever_fn: async function(query, weights) -> retrieved_chunk_ids

        Returns:
            ABTestResult
        """
        if len(golden_set_queries) < self.min_query_count:
            raise ValueError(f"Need at least {self.min_query_count} queries for valid A/B test")

        logger.info(
            "ltr_ab_test_started",
            baseline=baseline.name,
            candidate=candidate.name,
            queries=len(golden_set_queries),
        )

        # Evaluate baseline
        baseline_results = await self._evaluate_weight_set(
            baseline,
            golden_set_queries,
            retriever_fn,
        )

        # Evaluate candidate
        candidate_results = await self._evaluate_weight_set(
            candidate,
            golden_set_queries,
            retriever_fn,
        )

        # Calculate improvements
        precision_improvement = (
            (candidate_results["precision"] - baseline_results["precision"]) / baseline_results["precision"] * 100
            if baseline_results["precision"] > 0
            else 0.0
        )

        recall_improvement = (
            (candidate_results["recall"] - baseline_results["recall"]) / baseline_results["recall"] * 100
            if baseline_results["recall"] > 0
            else 0.0
        )

        mrr_improvement = (
            (candidate_results["mrr"] - baseline_results["mrr"]) / baseline_results["mrr"] * 100
            if baseline_results["mrr"] > 0
            else 0.0
        )

        # Determine winner (based on average improvement)
        avg_improvement = (precision_improvement + recall_improvement + mrr_improvement) / 3
        is_winner = avg_improvement >= self.improvement_threshold

        winner_name = candidate.name if is_winner else baseline.name

        result = ABTestResult(
            baseline_name=baseline.name,
            candidate_name=candidate.name,
            baseline_precision=baseline_results["precision"],
            baseline_recall=baseline_results["recall"],
            baseline_mrr=baseline_results["mrr"],
            candidate_precision=candidate_results["precision"],
            candidate_recall=candidate_results["recall"],
            candidate_mrr=candidate_results["mrr"],
            precision_improvement_pct=precision_improvement,
            recall_improvement_pct=recall_improvement,
            mrr_improvement_pct=mrr_improvement,
            is_winner=is_winner,
            winner_name=winner_name,
            query_count=len(golden_set_queries),
            tested_at=datetime.now().isoformat(),
        )

        logger.info(
            "ltr_ab_test_completed",
            winner=winner_name,
            avg_improvement_pct=avg_improvement,
            is_significant=is_winner,
        )

        return result

    async def _evaluate_weight_set(
        self,
        weight_set: WeightSet,
        golden_set_queries: list[dict],
        retriever_fn,
    ) -> dict[str, float]:
        """
        Evaluate a single weight set.

        Args:
            weight_set: Weight set to evaluate
            golden_set_queries: Golden set queries
            retriever_fn: Retriever function

        Returns:
            Dict with precision, recall, mrr
        """
        from src.contexts.retrieval_search.infrastructure.evaluation.metrics_legacy import (
            mean_precision_at_k,
            mean_recall_at_k,
            mean_reciprocal_rank,
        )

        results = []

        for query_item in golden_set_queries:
            query = query_item["query"]
            gold_ids = set(query_item["gold_ids"])

            # Retrieve with this weight set
            try:
                retrieved_ids = await retriever_fn(query, weight_set.weights)
            except Exception as e:
                logger.warning(
                    "retrieval_failed_in_ab_test",
                    query=query,
                    error=str(e),
                )
                retrieved_ids = []

            results.append((retrieved_ids, gold_ids))

        # Calculate metrics
        precision = mean_precision_at_k(results, k=5)
        recall = mean_recall_at_k(results, k=10)
        mrr = mean_reciprocal_rank(results)

        logger.debug(
            "weight_set_evaluated",
            name=weight_set.name,
            precision=precision,
            recall=recall,
            mrr=mrr,
        )

        return {
            "precision": precision,
            "recall": recall,
            "mrr": mrr,
        }

    def save_result(self, result: ABTestResult, output_path: str) -> None:
        """Save A/B test result to JSON file."""
        import json
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info("ab_test_result_saved", path=output_path)
