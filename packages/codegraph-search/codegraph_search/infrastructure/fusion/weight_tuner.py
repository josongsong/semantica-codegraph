"""
AutoRRF Weight Tuning Pipeline

오프라인 weight 최적화:
- Grid Search (간단, 안정적)
- Bayesian Optimization (고급, 효율적)

Intent별 최적 weight 탐색.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from codegraph_search.infrastructure.fusion.weight_validator import WeightValidator

if TYPE_CHECKING:
    from codegraph_search.infrastructure.fusion.golden_set import GoldenSet
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class WeightTuner:
    """
    Intent별 RRF weight 튜닝.

    전략:
    - Grid Search: 전역 탐색 (느리지만 안정)
    - Random Search: 빠른 근사
    - Bayesian: 효율적 탐색 (고급)
    """

    def __init__(
        self,
        evaluator: Callable,
        validator: WeightValidator | None = None,
    ):
        """
        Initialize tuner.

        Args:
            evaluator: 평가 함수 (golden_set, weights) -> metrics
            validator: Weight validator
        """
        self.evaluator = evaluator
        self.validator = validator or WeightValidator()

    def grid_search(
        self,
        golden_set: "GoldenSet",
        intent: str,
        baseline_metrics: dict[str, float],
        grid_size: int = 5,
    ) -> dict[str, Any]:
        """
        Grid Search로 최적 weight 탐색.

        5개 인덱스 (lexical, vector, symbol, fuzzy, domain)의
        weight 조합을 grid로 탐색.

        Args:
            golden_set: 골든셋
            intent: Target intent
            baseline_metrics: Baseline 성능
            grid_size: Grid 크기 (각 차원당)

        Returns:
            {
                "best_weights": {...},
                "best_metrics": {...},
                "best_score": float,
                "candidates_tested": int,
            }
        """
        logger.info(f"Grid search started for {intent} (grid_size={grid_size})")

        # Intent별 골든셋 필터링
        items = golden_set.get_by_intent(intent)
        if not items:
            logger.warning(f"No golden set items for {intent}")
            return {}

        # Weight 후보 생성 (5D grid)
        # 간단화: 2개만 0이 아닌 값 (나머지 0)
        # 실용적인 조합만 탐색
        candidates = self._generate_practical_candidates(grid_size)

        best_weights = None
        best_metrics = None
        best_master_score = 0.0
        valid_count = 0

        # 각 후보 평가
        for i, weights in enumerate(candidates):
            if i % 10 == 0:
                logger.info(f"Testing candidate {i + 1}/{len(candidates)}")

            try:
                # 평가
                metrics = self.evaluator(items, weights)

                # Validation
                result = self.validator.validate(metrics, baseline_metrics)

                if result.valid:
                    valid_count += 1

                    if result.master_score_new > best_master_score:
                        best_master_score = result.master_score_new
                        best_weights = weights
                        best_metrics = metrics

            except Exception as e:
                logger.error(f"Evaluation failed for candidate {i}: {e}")
                continue

        logger.info(f"Grid search completed: {valid_count}/{len(candidates)} valid candidates")

        return {
            "best_weights": best_weights,
            "best_metrics": best_metrics,
            "best_master_score": best_master_score,
            "candidates_tested": len(candidates),
            "valid_candidates": valid_count,
        }

    def random_search(
        self,
        golden_set: "GoldenSet",
        intent: str,
        baseline_metrics: dict[str, float],
        n_iterations: int = 50,
    ) -> dict[str, Any]:
        """
        Random Search로 weight 탐색.

        Grid보다 빠르고 Bayesian보다 단순.

        Args:
            golden_set: 골든셋
            intent: Target intent
            baseline_metrics: Baseline 성능
            n_iterations: 시도 횟수

        Returns:
            최적 weight 결과
        """
        logger.info(f"Random search started for {intent} (iterations={n_iterations})")

        items = golden_set.get_by_intent(intent)
        if not items:
            return {}

        best_weights = None
        best_metrics = None
        best_master_score = 0.0
        valid_count = 0

        for i in range(n_iterations):
            # 랜덤 weight 생성
            weights = self._generate_random_weights()

            try:
                metrics = self.evaluator(items, weights)
                result = self.validator.validate(metrics, baseline_metrics)

                if result.valid:
                    valid_count += 1

                    if result.master_score_new > best_master_score:
                        best_master_score = result.master_score_new
                        best_weights = weights
                        best_metrics = metrics

            except Exception as e:
                logger.error(f"Iteration {i} failed: {e}")
                continue

        logger.info(f"Random search completed: {valid_count}/{n_iterations} valid")

        return {
            "best_weights": best_weights,
            "best_metrics": best_metrics,
            "best_master_score": best_master_score,
            "iterations": n_iterations,
            "valid_candidates": valid_count,
        }

    def bayesian_optimize(
        self,
        golden_set: "GoldenSet",
        intent: str,
        baseline_metrics: dict[str, float],
        n_iterations: int = 30,
    ) -> dict[str, Any]:
        """
        Bayesian Optimization으로 효율적 탐색.

        최소한의 시도로 최적 weight 찾기.

        Args:
            golden_set: 골든셋
            intent: Target intent
            baseline_metrics: Baseline 성능
            n_iterations: 최대 시도 횟수

        Returns:
            최적 weight 결과
        """
        try:
            from skopt import gp_minimize
            from skopt.space import Real
        except ImportError:
            logger.error("scikit-optimize not installed, fallback to random search")
            return self.random_search(golden_set, intent, baseline_metrics, n_iterations)

        logger.info(f"Bayesian optimization started for {intent} (max_iterations={n_iterations})")

        items = golden_set.get_by_intent(intent)
        if not items:
            return {}

        # Search space: 5개 weight (0-1)
        # 합이 1이 되도록 정규화는 objective 내부에서 처리
        search_space = [Real(0.0, 1.0, name=f"w{i}") for i in range(5)]

        best_result = {"master_score": 0.0}

        def objective(weight_raw: list[float]) -> float:
            """최소화할 목적 함수 (음수 master score)."""
            # 정규화
            total = sum(weight_raw)
            if total == 0:
                return 999.0  # Invalid

            weights_normalized = {
                "lexical": weight_raw[0] / total,
                "vector": weight_raw[1] / total,
                "symbol": weight_raw[2] / total,
                "fuzzy": weight_raw[3] / total,
                "domain": weight_raw[4] / total,
            }

            try:
                # 평가
                metrics = self.evaluator(items, weights_normalized)

                # Validation
                result = self.validator.validate(metrics, baseline_metrics)

                if result.valid:
                    # 개선됨 - 기록
                    if result.master_score_new > best_result["master_score"]:
                        best_result["weights"] = weights_normalized
                        best_result["metrics"] = metrics
                        best_result["master_score"] = result.master_score_new

                    # 음수로 반환 (최소화 → 최대화)
                    return -result.master_score_new
                else:
                    # Invalid - 페널티
                    return 999.0

            except Exception as e:
                logger.error(f"Evaluation failed: {e}")
                return 999.0

        # Bayesian optimization 실행
        result = gp_minimize(
            objective,
            search_space,
            n_calls=n_iterations,
            random_state=42,
            verbose=False,
        )

        logger.info(f"Bayesian optimization completed: best score = {-result.fun:.4f}")

        return {
            "best_weights": best_result.get("weights"),
            "best_metrics": best_result.get("metrics"),
            "best_master_score": best_result.get("master_score", 0.0),
            "iterations": n_iterations,
            "convergence": result,
        }

    def _generate_practical_candidates(self, grid_size: int) -> list[dict[str, float]]:
        """
        실용적인 weight 후보 생성.

        전략: 2-3개 인덱스만 활성화 (나머지 0)
        """
        candidates = []

        sources = ["lexical", "vector", "symbol", "fuzzy", "domain"]

        # 1. Single source (각 100%)
        for source in sources:
            candidates.append({s: (1.0 if s == source else 0.0) for s in sources})

        # 2. Two sources (grid)
        for i, s1 in enumerate(sources):
            for j, s2 in enumerate(sources):
                if i >= j:
                    continue

                for w1 in np.linspace(0.1, 0.9, grid_size):
                    w2 = 1.0 - w1
                    weights = dict.fromkeys(sources, 0.0)
                    weights[s1] = w1
                    weights[s2] = w2
                    candidates.append(weights)

        # 3. Three sources (sparse grid)
        # 너무 많으므로 일부만 샘플링

        logger.info(f"Generated {len(candidates)} practical candidates")
        return candidates

    def _generate_random_weights(self) -> dict[str, float]:
        """랜덤 weight 생성 (정규화됨)."""
        raw = np.random.random(5)
        total = raw.sum()

        if total == 0:
            total = 1.0

        normalized = raw / total

        return {
            "lexical": float(normalized[0]),
            "vector": float(normalized[1]),
            "symbol": float(normalized[2]),
            "fuzzy": float(normalized[3]),
            "domain": float(normalized[4]),
        }
