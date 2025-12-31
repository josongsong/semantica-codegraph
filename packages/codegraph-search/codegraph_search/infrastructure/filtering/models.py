"""
Filtering Models

Models for smart filtering and error-prone detection.
"""

from dataclasses import dataclass
from enum import Enum

from codegraph_engine.shared_kernel.contracts.levels import QualityLevel, RiskLevel
from codegraph_engine.shared_kernel.contracts.thresholds import RISK


class ErrorProneReason(str, Enum):
    """Reasons for marking code as error-prone."""

    HIGH_CHURN = "high_churn"  # Frequently modified
    MANY_AUTHORS = "many_authors"  # Many contributors (coordination overhead)
    LOW_COVERAGE = "low_coverage"  # Insufficient test coverage
    HIGH_COMPLEXITY = "high_complexity"  # Complex code
    RECENT_HOTSPOT = "recent_hotspot"  # Recently very active
    MULTIPLE_FACTORS = "multiple_factors"  # Combined risk factors


@dataclass
class ErrorProneMetrics:
    """
    Error-prone detection metrics.

    Based on empirical research:
    - Nagappan et al. (2006): "Mining Metrics to Predict Component Failures"
    - Hassan (2009): "Predicting Faults Using the Complexity of Code Changes"
    - Kim et al. (2007): "Predicting Faults from Cached History"
    """

    chunk_id: str

    # Overall score (0.0-1.0, higher = more error-prone)
    error_prone_score: float = 0.0

    # Contributing factors (0.0-1.0 each)
    churn_risk: float = 0.0  # Based on change frequency
    author_risk: float = 0.0  # Based on number of authors
    coverage_risk: float = 0.0  # Based on test coverage
    complexity_risk: float = 0.0  # Based on cyclomatic complexity
    recency_risk: float = 0.0  # Based on recent activity

    # Classification
    risk_level: RiskLevel = RiskLevel.LOW
    primary_reason: ErrorProneReason | None = None

    # Recommendations
    suggested_actions: list[str] | None = None

    def __post_init__(self):
        """Compute risk level and recommendations."""
        if self.error_prone_score >= RISK.CRITICAL:
            self.risk_level = RiskLevel.CRITICAL
            self.suggested_actions = [
                "Add comprehensive tests",
                "Refactor to reduce complexity",
                "Code review by senior developer",
            ]
        elif self.error_prone_score >= RISK.HIGH:
            self.risk_level = RiskLevel.HIGH
            self.suggested_actions = [
                "Increase test coverage",
                "Add documentation",
                "Monitor closely",
            ]
        elif self.error_prone_score >= RISK.MEDIUM:
            self.risk_level = RiskLevel.MEDIUM
            self.suggested_actions = [
                "Consider adding tests",
                "Review complexity",
            ]
        else:
            self.risk_level = RiskLevel.LOW
            self.suggested_actions = []


@dataclass
class FilterConfig:
    """Configuration for smart filtering."""

    # Coverage filtering
    min_coverage: float = 0.0  # Minimum test coverage (0.0-1.0)
    require_tests: bool = False  # Require any test coverage

    # Error-prone filtering
    exclude_error_prone: bool = False  # Exclude high-risk code
    max_error_prone_score: float = 0.8  # Maximum acceptable risk

    # Recency filtering
    prefer_recent: bool = False  # Boost recently modified code
    recency_weight: float = 0.1  # Weight for recency boost

    # Complexity filtering
    max_complexity: int | None = None  # Maximum cyclomatic complexity

    # Quality filtering
    min_quality_level: QualityLevel = QualityLevel.NONE
