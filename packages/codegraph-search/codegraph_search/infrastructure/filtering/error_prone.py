"""
Error-Prone Code Detection

Predicts bug-prone code using proxy metrics (no bug database required).

Based on:
- Nagappan et al. (2006): Code churn and complexity predict defects
- Hassan (2009): Code changes predict faults
- Kim et al. (2007): Bug cache algorithm
- D'Ambros et al. (2010): Bug prediction through history metrics

Proxy Metrics:
1. Churn (change frequency) - HIGH CORRELATION
2. Author count (coordination) - MEDIUM CORRELATION
3. Test coverage - HIGH CORRELATION (inverse)
4. Cyclomatic complexity - MEDIUM CORRELATION
5. Recent activity - MEDIUM CORRELATION
"""

from codegraph_shared.common.observability import get_logger

from .models import ErrorProneMetrics, ErrorProneReason

logger = get_logger(__name__)


class ErrorProneScorer:
    """
    SOTA error-prone detection using proxy metrics.

    No bug database required - uses proven correlates.

    Usage:
        scorer = ErrorProneScorer()
        metrics = scorer.calculate(chunk, git_metrics, coverage, complexity)

        if metrics.error_prone_score > 0.7:
            print(f"High risk code: {metrics.risk_level}")
    """

    # Weights for each risk factor (tuned from research)
    WEIGHT_CHURN = 0.30  # Strongest predictor
    WEIGHT_AUTHORS = 0.20  # Coordination overhead
    WEIGHT_COVERAGE = 0.25  # Inverse correlation (low coverage = high risk)
    WEIGHT_COMPLEXITY = 0.15  # Secondary factor
    WEIGHT_RECENCY = 0.10  # Recent hotspots

    # Thresholds (calibrated)
    CHURN_HIGH_THRESHOLD = 0.7  # Hotspot threshold
    AUTHOR_MANY_THRESHOLD = 5  # Many contributors
    COVERAGE_LOW_THRESHOLD = 0.3  # Poor coverage
    COMPLEXITY_HIGH_THRESHOLD = 15  # High cyclomatic complexity
    RECENCY_DAYS_THRESHOLD = 30  # Recent activity window

    def __init__(self, enable_ml: bool = False):
        """
        Initialize scorer.

        Args:
            enable_ml: Enable ML-based prediction (future)
        """
        self.enable_ml = enable_ml

    def calculate(
        self,
        chunk_id: str,
        git_metrics: dict | None = None,
        coverage_metrics: dict | None = None,
        complexity_metrics: dict | None = None,
    ) -> ErrorProneMetrics:
        """
        Calculate error-prone score for a chunk.

        Args:
            chunk_id: Chunk identifier
            git_metrics: Git history metrics (churn, authors, hotspot)
            coverage_metrics: Test coverage metrics
            complexity_metrics: Complexity metrics (cyclomatic, etc.)

        Returns:
            Error-prone metrics with risk classification
        """
        git_metrics = git_metrics or {}
        coverage_metrics = coverage_metrics or {}
        complexity_metrics = complexity_metrics or {}

        # Calculate individual risk factors
        churn_risk = self._calculate_churn_risk(git_metrics)
        author_risk = self._calculate_author_risk(git_metrics)
        coverage_risk = self._calculate_coverage_risk(coverage_metrics)
        complexity_risk = self._calculate_complexity_risk(complexity_metrics)
        recency_risk = self._calculate_recency_risk(git_metrics)

        # Weighted combination
        error_prone_score = (
            churn_risk * self.WEIGHT_CHURN
            + author_risk * self.WEIGHT_AUTHORS
            + coverage_risk * self.WEIGHT_COVERAGE
            + complexity_risk * self.WEIGHT_COMPLEXITY
            + recency_risk * self.WEIGHT_RECENCY
        )

        # Clamp to [0, 1]
        error_prone_score = max(0.0, min(1.0, error_prone_score))

        # Determine primary reason
        primary_reason = self._determine_primary_reason(
            churn_risk, author_risk, coverage_risk, complexity_risk, recency_risk
        )

        metrics = ErrorProneMetrics(
            chunk_id=chunk_id,
            error_prone_score=error_prone_score,
            churn_risk=churn_risk,
            author_risk=author_risk,
            coverage_risk=coverage_risk,
            complexity_risk=complexity_risk,
            recency_risk=recency_risk,
            primary_reason=primary_reason,
        )

        logger.debug(
            f"Error-prone score for {chunk_id[:8]}: {error_prone_score:.2f} "
            f"(churn={churn_risk:.2f}, authors={author_risk:.2f}, "
            f"coverage={coverage_risk:.2f}, complexity={complexity_risk:.2f})"
        )

        return metrics

    def _calculate_churn_risk(self, git_metrics: dict) -> float:
        """
        Calculate risk from code churn.

        High churn = high risk (Nagappan et al., 2006)

        Args:
            git_metrics: Dict with 'is_hotspot', 'churn_score', 'hotspot_reason'

        Returns:
            Risk score 0.0-1.0
        """
        # Check if marked as hotspot
        if git_metrics.get("is_hotspot"):
            # Critical if hotspot
            return 0.9

        # Use churn score directly (0-1 scale)
        churn_score = git_metrics.get("churn_score", 0.0)

        if churn_score >= self.CHURN_HIGH_THRESHOLD:
            return 0.8
        elif churn_score >= 0.5:
            return 0.6
        elif churn_score >= 0.3:
            return 0.4
        else:
            return churn_score * 0.5  # Scale down low churn

    def _calculate_author_risk(self, git_metrics: dict) -> float:
        """
        Calculate risk from author count.

        Many authors = coordination overhead = higher risk
        (Bird et al., 2011: "Don't Touch My Code!")

        Args:
            git_metrics: Dict with 'author_count'

        Returns:
            Risk score 0.0-1.0
        """
        author_count = git_metrics.get("author_count", 1)

        if author_count >= 10:
            return 1.0  # Very high risk
        elif author_count >= self.AUTHOR_MANY_THRESHOLD:
            return 0.7  # High risk
        elif author_count >= 3:
            return 0.4  # Medium risk
        elif author_count == 2:
            return 0.2  # Low risk
        else:
            return 0.0  # Single author (lowest risk)

    def _calculate_coverage_risk(self, coverage_metrics: dict) -> float:
        """
        Calculate risk from test coverage.

        Low coverage = high risk (INVERSE correlation)
        (Nagappan et al., 2005: Test coverage correlates with quality)

        Args:
            coverage_metrics: Dict with 'line_coverage', 'has_tests'

        Returns:
            Risk score 0.0-1.0
        """
        if not coverage_metrics.get("has_tests", False):
            return 1.0  # No tests = maximum risk

        line_coverage = coverage_metrics.get("line_coverage", 0.0)

        # Inverse: low coverage = high risk
        if line_coverage < 0.1:
            return 0.9
        elif line_coverage < self.COVERAGE_LOW_THRESHOLD:
            return 0.7
        elif line_coverage < 0.5:
            return 0.5
        elif line_coverage < 0.8:
            return 0.3
        else:
            return 0.1  # High coverage = low risk

    def _calculate_complexity_risk(self, complexity_metrics: dict) -> float:
        """
        Calculate risk from cyclomatic complexity.

        High complexity = harder to maintain = higher risk
        (McCabe, 1976; Basili et al., 1996)

        Args:
            complexity_metrics: Dict with 'cyclomatic'

        Returns:
            Risk score 0.0-1.0
        """
        cyclomatic = complexity_metrics.get("cyclomatic", 0)

        # McCabe threshold: >10 is complex, >15 is very complex
        if cyclomatic > 30:
            return 1.0  # Extremely complex
        elif cyclomatic > 20:
            return 0.8
        elif cyclomatic > self.COMPLEXITY_HIGH_THRESHOLD:
            return 0.6
        elif cyclomatic > 10:
            return 0.4
        elif cyclomatic > 5:
            return 0.2
        else:
            return 0.0  # Low complexity

    def _calculate_recency_risk(self, git_metrics: dict) -> float:
        """
        Calculate risk from recent activity.

        Recent hotspot = active development = higher short-term risk
        (Hassan, 2009: Recent changes predict faults)

        Args:
            git_metrics: Dict with 'hotspot_reason', 'days_since_last_change'

        Returns:
            Risk score 0.0-1.0
        """
        hotspot_reason = git_metrics.get("hotspot_reason")

        if hotspot_reason == "recent_activity":
            return 0.8  # Recently very active

        days_since = git_metrics.get("days_since_last_change", 999)

        if days_since <= 7:
            return 0.6  # Very recent
        elif days_since <= self.RECENCY_DAYS_THRESHOLD:
            return 0.4  # Recent
        elif days_since <= 90:
            return 0.2  # Somewhat recent
        else:
            return 0.0  # Stable

    def _determine_primary_reason(
        self,
        churn_risk: float,
        author_risk: float,
        coverage_risk: float,
        complexity_risk: float,
        recency_risk: float,
    ) -> ErrorProneReason:
        """
        Determine primary reason for error-prone classification.

        Args:
            Individual risk scores

        Returns:
            Primary reason enum
        """
        risks = {
            ErrorProneReason.HIGH_CHURN: churn_risk,
            ErrorProneReason.MANY_AUTHORS: author_risk,
            ErrorProneReason.LOW_COVERAGE: coverage_risk,
            ErrorProneReason.HIGH_COMPLEXITY: complexity_risk,
            ErrorProneReason.RECENT_HOTSPOT: recency_risk,
        }

        # Find dominant factor
        max(risks.values())
        primary = max(risks.items(), key=lambda x: x[1])[0]

        # Check if multiple high factors
        high_factors = sum(1 for risk in risks.values() if risk >= 0.6)
        if high_factors >= 2:
            return ErrorProneReason.MULTIPLE_FACTORS

        return primary

    def batch_calculate(
        self,
        chunks_data: list[dict],
    ) -> dict[str, ErrorProneMetrics]:
        """
        Batch calculate error-prone scores.

        Args:
            chunks_data: List of dicts with chunk_id, git_metrics, coverage, complexity

        Returns:
            Dict mapping chunk_id to ErrorProneMetrics
        """
        results = {}

        for data in chunks_data:
            chunk_id = data["chunk_id"]
            metrics = self.calculate(
                chunk_id=chunk_id,
                git_metrics=data.get("git_metrics"),
                coverage_metrics=data.get("coverage_metrics"),
                complexity_metrics=data.get("complexity_metrics"),
            )
            results[chunk_id] = metrics

        return results
