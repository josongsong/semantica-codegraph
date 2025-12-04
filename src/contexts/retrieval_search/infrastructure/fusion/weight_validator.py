"""
Weight Validator

Production-grade weight validation for AutoRRF tuning.

검증 전략:
1. Intent별 분리 검증
2. Metric별 threshold
3. Master score 기반 최종 판단
"""

from dataclasses import dataclass, field
from typing import Any

from src.common.observability import get_logger

logger = get_logger(__name__)
# Metric별 기본 threshold (baseline 대비 최소 비율)
DEFAULT_METRIC_THRESHOLDS = {
    "MRR": 0.98,  # Mean Reciprocal Rank (변동 작음)
    "Recall@1": 0.95,  # Top-1 정답률
    "Recall@5": 0.95,  # Top-5 정답률
    "Recall@10": 0.90,  # Top-10 정답률 (변동 큼)
    "nDCG@5": 0.95,  # Normalized DCG
    "nDCG@10": 0.95,
    "Precision@5": 0.95,
}

# Master score 계산 시 metric별 weight
DEFAULT_MASTER_WEIGHTS = {
    "MRR": 0.3,
    "Recall@5": 0.4,
    "nDCG@10": 0.3,
}


@dataclass
class ValidationResult:
    """
    Weight validation 결과.
    """

    valid: bool
    """검증 통과 여부"""

    master_score_new: float
    """새 weight의 master score"""

    master_score_baseline: float
    """Baseline master score"""

    metrics_new: dict[str, float]
    """새 weight의 metric 값들"""

    metrics_baseline: dict[str, float]
    """Baseline metric 값들"""

    regression_metrics: list[str] = field(default_factory=list)
    """Regression 발생한 metric 리스트"""

    improvements: dict[str, float] = field(default_factory=dict)
    """개선된 metric과 개선폭"""

    details: dict[str, Any] = field(default_factory=dict)
    """상세 정보"""

    def __str__(self) -> str:
        """Human-readable 요약."""
        status = "✅ PASS" if self.valid else "❌ REJECT"
        master_diff = self.master_score_new - self.master_score_baseline

        msg = f"{status}\n"
        msg += f"Master Score: {self.master_score_baseline:.4f} → {self.master_score_new:.4f} "
        msg += f"({master_diff:+.4f})\n"

        if self.regression_metrics:
            msg += f"Regressions: {', '.join(self.regression_metrics)}\n"

        if self.improvements:
            msg += "Improvements:\n"
            for metric, improvement in self.improvements.items():
                msg += f"  - {metric}: +{improvement:.4f}\n"

        return msg


class WeightValidator:
    """
    Production-grade weight validator.

    특징:
    - Intent별 분리 검증
    - Metric별 threshold
    - Master score 기반 최종 판단
    """

    def __init__(
        self,
        metric_thresholds: dict[str, float] | None = None,
        master_weights: dict[str, float] | None = None,
        enable_master_score: bool = True,
    ):
        """
        Initialize validator.

        Args:
            metric_thresholds: Metric별 regression threshold
            master_weights: Master score 계산 시 metric weights
            enable_master_score: Master score 검증 활성화
        """
        self.metric_thresholds = metric_thresholds or DEFAULT_METRIC_THRESHOLDS
        self.master_weights = master_weights or DEFAULT_MASTER_WEIGHTS
        self.enable_master_score = enable_master_score

    def validate(
        self,
        metrics_new: dict[str, float],
        metrics_baseline: dict[str, float],
    ) -> ValidationResult:
        """
        새 weight를 baseline과 비교 검증.

        검증 단계:
        1. Master score 비교 (전체 성능)
        2. Metric별 regression guard

        Args:
            metrics_new: 새 weight로 측정한 metric 값들
            metrics_baseline: Baseline metric 값들

        Returns:
            ValidationResult
        """
        # 1. Master score 계산
        master_new = self._compute_master_score(metrics_new)
        master_baseline = self._compute_master_score(metrics_baseline)

        # 2. Metric별 regression 체크
        regressions = []
        improvements = {}

        for metric, new_value in metrics_new.items():
            baseline_value = metrics_baseline.get(metric, 0.0)

            # Threshold 가져오기
            threshold = self.metric_thresholds.get(metric, 0.95)
            min_acceptable = baseline_value * threshold

            # Regression 체크
            if new_value < min_acceptable:
                regressions.append(metric)
                logger.warning(
                    f"Regression in {metric}: {baseline_value:.4f} → {new_value:.4f} (threshold: {min_acceptable:.4f})"
                )

            # Improvement 체크
            if new_value > baseline_value * 1.01:  # 1% 이상 개선
                improvement = new_value - baseline_value
                improvements[metric] = improvement

        # 3. 최종 판단
        valid = True

        # Master score 체크
        if self.enable_master_score and master_new < master_baseline:
            logger.warning(f"Master score decreased: {master_baseline:.4f} → {master_new:.4f}")
            valid = False

        # Regression 체크
        if regressions:
            logger.warning(f"Regressions found: {regressions}")
            valid = False

        # 결과 생성
        result = ValidationResult(
            valid=valid,
            master_score_new=master_new,
            master_score_baseline=master_baseline,
            metrics_new=metrics_new,
            metrics_baseline=metrics_baseline,
            regression_metrics=regressions,
            improvements=improvements,
            details={
                "metric_thresholds": self.metric_thresholds,
                "master_weights": self.master_weights,
            },
        )

        return result

    def validate_per_intent(
        self,
        metrics_by_intent_new: dict[str, dict[str, float]],
        metrics_by_intent_baseline: dict[str, dict[str, float]],
    ) -> dict[str, ValidationResult]:
        """
        Intent별 분리 검증.

        각 intent마다 독립적으로 validation 수행.

        Args:
            metrics_by_intent_new: {intent: {metric: value}}
            metrics_by_intent_baseline: {intent: {metric: value}}

        Returns:
            {intent: ValidationResult}
        """
        results = {}

        for intent in metrics_by_intent_new.keys():
            if intent not in metrics_by_intent_baseline:
                logger.warning(f"No baseline for intent {intent}, skipping")
                continue

            result = self.validate(
                metrics_new=metrics_by_intent_new[intent],
                metrics_baseline=metrics_by_intent_baseline[intent],
            )

            results[intent] = result

            logger.info(
                f"Intent {intent}: {'PASS' if result.valid else 'REJECT'} "
                f"(master: {result.master_score_baseline:.4f} → "
                f"{result.master_score_new:.4f})"
            )

        return results

    def _compute_master_score(self, metrics: dict[str, float]) -> float:
        """
        Master score 계산 (weighted combination).

        Master score = weighted sum of key metrics

        Args:
            metrics: Metric 값들

        Returns:
            Master score (0.0 - 1.0)
        """
        if not self.enable_master_score:
            return 0.0

        total_score = 0.0
        total_weight = 0.0

        for metric, weight in self.master_weights.items():
            if metric in metrics:
                total_score += metrics[metric] * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return total_score / total_weight

    def check_minimum_logs(
        self,
        intent: str,
        log_count: int,
    ) -> bool:
        """
        Intent별 최소 로그 수 체크 (콜드 스타트 방지).

        데이터 부족 시 튜닝하면 과적합 위험.

        Args:
            intent: Intent
            log_count: 로그 개수

        Returns:
            True if 충분함
        """
        MIN_LOGS_FOR_TUNING = {
            "IDENTIFIER": 100,
            "NATURAL_QUESTION": 200,
            "ERROR_LOG": 50,
            "CALLER_USAGE": 100,
            "DEFINITION": 80,
            "IMPLEMENTATION": 150,
        }

        min_required = MIN_LOGS_FOR_TUNING.get(intent, 100)

        if log_count < min_required:
            logger.warning(f"Insufficient logs for {intent}: {log_count} < {min_required}")
            return False

        return True


class FeedbackQuality:
    """피드백 품질 레벨."""

    HIGH = "high"  # 명확한 클릭 + 해결됨 + dwell > 10s
    MEDIUM = "medium"  # 클릭 + (해결됨 OR dwell > 5s)
    LOW = "low"  # 클릭만 OR 타임아웃

    @staticmethod
    def classify(
        clicked: bool,
        resolved: bool | None,
        dwell_time_ms: int | None,
    ) -> str:
        """피드백 품질 분류."""
        if not clicked:
            return FeedbackQuality.LOW

        dwell_sec = (dwell_time_ms / 1000.0) if dwell_time_ms else 0.0

        if resolved and dwell_sec > 10:
            return FeedbackQuality.HIGH

        if resolved or dwell_sec > 5:
            return FeedbackQuality.MEDIUM

        return FeedbackQuality.LOW


def filter_logs_by_quality(
    logs: list,
    min_quality: str = FeedbackQuality.MEDIUM,
) -> list:
    """
    품질 기준으로 로그 필터링.

    튜닝에는 HIGH/MEDIUM만 사용 권장.

    Args:
        logs: SearchLog 리스트
        min_quality: 최소 품질

    Returns:
        필터링된 로그
    """
    quality_order = [FeedbackQuality.LOW, FeedbackQuality.MEDIUM, FeedbackQuality.HIGH]
    min_idx = quality_order.index(min_quality)

    filtered = []
    for log in logs:
        quality = FeedbackQuality.classify(
            clicked=log.clicked_hit_id is not None,
            resolved=log.resolved,
            dwell_time_ms=log.dwell_time_ms,
        )

        quality_idx = quality_order.index(quality)

        if quality_idx >= min_idx:
            filtered.append(log)

    return filtered
