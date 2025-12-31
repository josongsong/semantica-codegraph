"""Telemetry Analyzer - RFC-036.

Analyzes telemetry data for rule quality insights.

Key Components:
    - FrequencyAnalyzer: Identifies common patterns
    - FPTPEstimator: Estimates false positive/true positive rates
    - RuleHealthChecker: Identifies unhealthy rules

Usage:
    >>> analyzer = FrequencyAnalyzer()
    >>> top_patterns = analyzer.top_patterns(events, threshold=10)
    >>>
    >>> estimator = FPTPEstimator()
    >>> fp_rate = estimator.estimate_fp_rate(events)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from trcr.telemetry.schema import PatternStats, RuleMatchTelemetry, RuleStatistics

logger = logging.getLogger(__name__)


class FrequencyAnalyzer:
    """Analyzes pattern frequency in telemetry.

    RFC-036: Identifies most common patterns.

    Usage:
        >>> analyzer = FrequencyAnalyzer()
        >>> patterns = analyzer.top_patterns(events, threshold=10)
        >>> for p in patterns:
        ...     print(f"{p.pattern}: {p.count} matches")
    """

    def top_patterns(
        self,
        events: list[RuleMatchTelemetry],
        threshold: int = 10,
        limit: int = 20,
    ) -> list[PatternStats]:
        """Get most common patterns.

        Args:
            events: Match events
            threshold: Minimum count to include
            limit: Maximum patterns to return

        Returns:
            List of PatternStats sorted by count
        """
        pattern_data: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"count": 0, "total_confidence": 0.0, "suppressed": 0, "confirmed": 0}
        )

        for event in events:
            pattern = f"{event.base_type}.{event.call or event.read or '*'}"
            pattern_data[pattern]["count"] += 1
            pattern_data[pattern]["total_confidence"] += event.confidence

            if event.user_action == "suppress":
                pattern_data[pattern]["suppressed"] += 1
            elif event.user_action == "confirm":
                pattern_data[pattern]["confirmed"] += 1

        # Convert to PatternStats
        results = []
        for pattern, data in pattern_data.items():
            count = int(data["count"])
            if count >= threshold:
                results.append(
                    PatternStats(
                        pattern=pattern,
                        count=count,
                        avg_confidence=data["total_confidence"] / count,
                        suppressed=int(data["suppressed"]),
                        confirmed=int(data["confirmed"]),
                    )
                )

        # Sort by count (descending)
        results.sort(key=lambda x: x.count, reverse=True)

        return results[:limit]

    def by_rule(
        self,
        events: list[RuleMatchTelemetry],
    ) -> dict[str, list[PatternStats]]:
        """Group patterns by rule.

        Args:
            events: Match events

        Returns:
            Dict mapping rule_id to pattern stats
        """
        by_rule: dict[str, list[RuleMatchTelemetry]] = defaultdict(list)

        for event in events:
            by_rule[event.rule_id].append(event)

        result = {}
        for rule_id, rule_events in by_rule.items():
            result[rule_id] = self.top_patterns(rule_events, threshold=1)

        return result


class FPTPEstimator:
    """Estimates false positive/true positive rates.

    RFC-036: Uses user feedback to estimate accuracy.

    Definitions:
        - False Positive (FP): User suppressed the match
        - True Positive (TP): User confirmed the match
        - FP Rate: FP / (FP + TP)
        - Precision: TP / (TP + FP)

    Usage:
        >>> estimator = FPTPEstimator()
        >>> fp_rate = estimator.estimate_fp_rate(events)
        >>> print(f"FP Rate: {fp_rate:.1%}")
    """

    def estimate_fp_rate(
        self,
        events: list[RuleMatchTelemetry],
    ) -> float | None:
        """Estimate false positive rate.

        Args:
            events: Match events

        Returns:
            FP rate [0, 1] or None if no feedback
        """
        suppressed = 0
        confirmed = 0

        for event in events:
            if event.user_action == "suppress":
                suppressed += 1
            elif event.user_action == "confirm":
                confirmed += 1

        total = suppressed + confirmed
        if total == 0:
            return None

        return suppressed / total

    def estimate_precision(
        self,
        events: list[RuleMatchTelemetry],
    ) -> float | None:
        """Estimate precision (1 - FP rate).

        Args:
            events: Match events

        Returns:
            Precision [0, 1] or None if no feedback
        """
        fp_rate = self.estimate_fp_rate(events)
        if fp_rate is None:
            return None
        return 1.0 - fp_rate

    def by_tier(
        self,
        events: list[RuleMatchTelemetry],
    ) -> dict[str, float | None]:
        """Estimate FP rate by tier.

        Args:
            events: Match events

        Returns:
            Dict mapping tier to FP rate
        """
        by_tier: dict[str, list[RuleMatchTelemetry]] = defaultdict(list)

        for event in events:
            by_tier[event.tier].append(event)

        return {tier: self.estimate_fp_rate(tier_events) for tier, tier_events in by_tier.items()}

    def by_rule(
        self,
        events: list[RuleMatchTelemetry],
    ) -> dict[str, float | None]:
        """Estimate FP rate by rule.

        Args:
            events: Match events

        Returns:
            Dict mapping rule_id to FP rate
        """
        by_rule: dict[str, list[RuleMatchTelemetry]] = defaultdict(list)

        for event in events:
            by_rule[event.rule_id].append(event)

        return {rule_id: self.estimate_fp_rate(rule_events) for rule_id, rule_events in by_rule.items()}


@dataclass
class RuleHealthReport:
    """Health report for a rule."""

    rule_id: str
    atom_id: str
    is_healthy: bool
    fp_rate: float | None
    total_matches: int
    feedback_count: int
    recommendation: str


class RuleHealthChecker:
    """Checks rule health based on telemetry.

    RFC-036: Identifies problematic rules.

    Unhealthy indicators:
        - FP rate > 50%
        - Very low match count (potentially dead rule)
        - Confidence drift

    Usage:
        >>> checker = RuleHealthChecker()
        >>> reports = checker.check_all(rule_stats)
        >>> for r in reports:
        ...     if not r.is_healthy:
        ...         print(f"Unhealthy: {r.rule_id} - {r.recommendation}")
    """

    def __init__(
        self,
        fp_threshold: float = 0.5,
        min_feedback_for_judgment: int = 5,
    ) -> None:
        """Initialize checker.

        Args:
            fp_threshold: FP rate above this is unhealthy
            min_feedback_for_judgment: Minimum feedback events for judgment
        """
        self.fp_threshold = fp_threshold
        self.min_feedback_for_judgment = min_feedback_for_judgment

    def check(self, stats: RuleStatistics) -> RuleHealthReport:
        """Check health of a single rule.

        Args:
            stats: Rule statistics

        Returns:
            Health report
        """
        fp_rate = stats.false_positive_rate
        feedback_count = stats.suppressed_count + stats.confirmed_count

        # Determine health
        is_healthy = True
        recommendation = "Rule is healthy"

        if feedback_count < self.min_feedback_for_judgment:
            recommendation = "Insufficient feedback data for judgment"
        elif fp_rate is not None and fp_rate > self.fp_threshold:
            is_healthy = False
            recommendation = (
                f"High false positive rate ({fp_rate:.1%}). Consider refining pattern or increasing specificity."
            )
        elif stats.total_matches == 0:
            recommendation = "Rule has no matches. May be dead code."

        return RuleHealthReport(
            rule_id=stats.rule_id,
            atom_id=stats.atom_id,
            is_healthy=is_healthy,
            fp_rate=fp_rate,
            total_matches=stats.total_matches,
            feedback_count=feedback_count,
            recommendation=recommendation,
        )

    def check_all(
        self,
        all_stats: list[RuleStatistics],
    ) -> list[RuleHealthReport]:
        """Check health of all rules.

        Args:
            all_stats: All rule statistics

        Returns:
            List of health reports
        """
        return [self.check(stats) for stats in all_stats]

    def get_unhealthy(
        self,
        all_stats: list[RuleStatistics],
    ) -> list[RuleHealthReport]:
        """Get only unhealthy rules.

        Args:
            all_stats: All rule statistics

        Returns:
            List of unhealthy rule reports
        """
        return [report for report in self.check_all(all_stats) if not report.is_healthy]


@dataclass
class TelemetryAnalysisReport:
    """Complete telemetry analysis report."""

    # Summary
    total_events: int
    total_rules: int
    overall_fp_rate: float | None

    # By tier
    fp_rate_by_tier: dict[str, float | None]

    # Top patterns
    top_patterns: list[PatternStats]

    # Unhealthy rules
    unhealthy_rules: list[RuleHealthReport]

    # Recommendations
    recommendations: list[str] = field(default_factory=list)


def analyze_telemetry(
    events: list[RuleMatchTelemetry],
    rule_stats: list[RuleStatistics],
) -> TelemetryAnalysisReport:
    """Perform complete telemetry analysis.

    Args:
        events: Match events
        rule_stats: Rule statistics

    Returns:
        Complete analysis report
    """
    freq_analyzer = FrequencyAnalyzer()
    fptp_estimator = FPTPEstimator()
    health_checker = RuleHealthChecker()

    # Analyze
    top_patterns = freq_analyzer.top_patterns(events)
    overall_fp = fptp_estimator.estimate_fp_rate(events)
    fp_by_tier = fptp_estimator.by_tier(events)
    unhealthy = health_checker.get_unhealthy(rule_stats)

    # Generate recommendations
    recommendations = []

    if overall_fp is not None and overall_fp > 0.3:
        recommendations.append(f"Overall FP rate is {overall_fp:.1%}. Consider reviewing tier3 rules.")

    if len(unhealthy) > 0:
        recommendations.append(f"{len(unhealthy)} unhealthy rules found. Review and refine these rules.")

    tier3_fp = fp_by_tier.get("tier3")
    if tier3_fp is not None and tier3_fp > 0.5:
        recommendations.append(f"Tier3 FP rate is {tier3_fp:.1%}. Consider promoting accurate tier3 rules to tier2.")

    return TelemetryAnalysisReport(
        total_events=len(events),
        total_rules=len(rule_stats),
        overall_fp_rate=overall_fp,
        fp_rate_by_tier=fp_by_tier,
        top_patterns=top_patterns,
        unhealthy_rules=unhealthy,
        recommendations=recommendations,
    )
