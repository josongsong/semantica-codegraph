"""Quality Scorer - RFC-039.

Scores rule quality based on telemetry data.

Quality Score Formula:
    score = usage * (1 - fp_rate) * coverage * 100

Where:
    - usage: Number of matches (normalized)
    - fp_rate: False positive rate from user feedback
    - coverage: Pattern coverage (distinct patterns matched)

Usage:
    >>> scorer = QualityScorer()
    >>> score = scorer.score(rule_id, telemetry_events)
    >>> print(f"Quality score: {score:.1f}")
"""

import logging
from dataclasses import dataclass

from trcr.telemetry.schema import RuleMatchTelemetry, RuleStatistics

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality score for a rule."""

    rule_id: str
    atom_id: str

    # Components
    usage_score: float  # [0, 100]
    precision_score: float  # [0, 100]
    coverage_score: float  # [0, 100]

    # Final score
    final_score: float  # [0, 100]

    # Metadata
    total_matches: int
    feedback_count: int
    fp_rate: float | None

    @property
    def grade(self) -> str:
        """Get letter grade.

        A: 90+
        B: 80-89
        C: 70-79
        D: 60-69
        F: <60
        """
        if self.final_score >= 90:
            return "A"
        elif self.final_score >= 80:
            return "B"
        elif self.final_score >= 70:
            return "C"
        elif self.final_score >= 60:
            return "D"
        else:
            return "F"

    @property
    def is_high_quality(self) -> bool:
        """Check if rule is high quality (B or better)."""
        return self.final_score >= 80

    def summary(self) -> str:
        """Generate summary string."""
        return (
            f"{self.rule_id}: {self.final_score:.1f} ({self.grade}) - "
            f"usage={self.usage_score:.1f}, precision={self.precision_score:.1f}, "
            f"coverage={self.coverage_score:.1f}"
        )


class QualityScorer:
    """Scores rule quality based on telemetry.

    RFC-039: Quality scoring for rule promotion.

    Score Components:
        - Usage: How often the rule matches (normalized)
        - Precision: 1 - FP rate (from user feedback)
        - Coverage: How many distinct patterns matched

    Usage:
        >>> scorer = QualityScorer()
        >>> score = scorer.score_from_stats(rule_stats)
    """

    def __init__(
        self,
        usage_weight: float = 0.3,
        precision_weight: float = 0.5,
        coverage_weight: float = 0.2,
        usage_normalization: int = 100,  # Matches for full usage score
    ) -> None:
        """Initialize scorer.

        Args:
            usage_weight: Weight for usage component
            precision_weight: Weight for precision component
            coverage_weight: Weight for coverage component
            usage_normalization: Matches needed for full usage score
        """
        self.usage_weight = usage_weight
        self.precision_weight = precision_weight
        self.coverage_weight = coverage_weight
        self.usage_normalization = usage_normalization

        # Validate weights sum to 1.0
        total = usage_weight + precision_weight + coverage_weight
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def score_from_stats(self, stats: RuleStatistics) -> QualityScore:
        """Score a rule from its statistics.

        Args:
            stats: Rule statistics

        Returns:
            QualityScore
        """
        # Usage score (normalized to 0-100)
        usage_score = min(100.0, (stats.total_matches / self.usage_normalization) * 100)

        # Precision score (100 - FP rate * 100)
        fp_rate = stats.false_positive_rate
        if fp_rate is None:
            # No feedback, assume 80% precision
            precision_score = 80.0
        else:
            precision_score = (1.0 - fp_rate) * 100

        # Coverage score (based on patterns seen)
        # More patterns = higher coverage = more useful rule
        pattern_count = len(stats.patterns_seen)
        coverage_score = min(100.0, pattern_count * 10)  # 10 patterns = 100%

        # Final weighted score
        final_score = (
            usage_score * self.usage_weight
            + precision_score * self.precision_weight
            + coverage_score * self.coverage_weight
        )

        feedback_count = stats.suppressed_count + stats.confirmed_count

        return QualityScore(
            rule_id=stats.rule_id,
            atom_id=stats.atom_id,
            usage_score=usage_score,
            precision_score=precision_score,
            coverage_score=coverage_score,
            final_score=final_score,
            total_matches=stats.total_matches,
            feedback_count=feedback_count,
            fp_rate=fp_rate,
        )

    def score_from_events(
        self,
        rule_id: str,
        atom_id: str,
        events: list[RuleMatchTelemetry],
    ) -> QualityScore:
        """Score a rule from match events.

        Args:
            rule_id: Rule ID
            atom_id: Atom ID
            events: Match events for this rule

        Returns:
            QualityScore
        """
        # Build statistics from events
        stats = RuleStatistics(rule_id=rule_id, atom_id=atom_id)
        for event in events:
            if event.rule_id == rule_id and event.atom_id == atom_id:
                stats.add_match(event)

        return self.score_from_stats(stats)

    def rank_rules(
        self,
        all_stats: list[RuleStatistics],
    ) -> list[QualityScore]:
        """Rank all rules by quality score.

        Args:
            all_stats: Statistics for all rules

        Returns:
            List of QualityScore sorted by final_score (highest first)
        """
        scores = [self.score_from_stats(stats) for stats in all_stats]
        scores.sort(key=lambda s: s.final_score, reverse=True)
        return scores

    def get_low_quality_rules(
        self,
        all_stats: list[RuleStatistics],
        threshold: float = 60.0,
    ) -> list[QualityScore]:
        """Get rules below quality threshold.

        Args:
            all_stats: Statistics for all rules
            threshold: Quality threshold

        Returns:
            List of low-quality rules
        """
        scores = [self.score_from_stats(stats) for stats in all_stats]
        return [s for s in scores if s.final_score < threshold]

    def get_high_quality_rules(
        self,
        all_stats: list[RuleStatistics],
        threshold: float = 80.0,
    ) -> list[QualityScore]:
        """Get rules above quality threshold.

        Args:
            all_stats: Statistics for all rules
            threshold: Quality threshold

        Returns:
            List of high-quality rules
        """
        scores = [self.score_from_stats(stats) for stats in all_stats]
        return [s for s in scores if s.final_score >= threshold]
