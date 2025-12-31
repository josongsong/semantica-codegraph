"""Promotion Manager - RFC-039.

Manages rule promotion workflow.

Promotion Stages:
    - Experimental: New rules, 4 weeks minimum
    - Verified: Stable rules, 12 weeks minimum
    - Core: Production-ready rules

Promotion Criteria:
    - Experimental → Verified: 4 weeks, no critical issues, FP rate < 30%
    - Verified → Core: 12 weeks, widely used, FP rate < 10%

Usage:
    >>> manager = PromotionManager()
    >>> status = manager.check_promotion("sql_injection_sink", stats)
    >>> if status.can_promote:
    ...     print(f"Ready for promotion to {status.next_stage}")
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from trcr.telemetry.schema import RuleStatistics

logger = logging.getLogger(__name__)


class RuleStage(Enum):
    """Rule lifecycle stages.

    RFC-039: Progression from experimental to core.
    """

    EXPERIMENTAL = "experimental"
    VERIFIED = "verified"
    CORE = "core"

    def __str__(self) -> str:
        return self.value


@dataclass
class StageRequirements:
    """Requirements for a promotion stage.

    Attributes:
        min_age_weeks: Minimum weeks at current stage
        max_fp_rate: Maximum false positive rate
        min_matches: Minimum total matches
        min_feedback: Minimum feedback events
    """

    min_age_weeks: int
    max_fp_rate: float
    min_matches: int
    min_feedback: int


@dataclass
class PromotionStatus:
    """Status of rule promotion eligibility.

    Attributes:
        rule_id: Rule identifier
        current_stage: Current lifecycle stage
        next_stage: Next stage if promoted
        can_promote: Whether promotion is possible
        blockers: List of blocking issues
        metrics: Relevant metrics
        recommendation: Human-readable recommendation
    """

    rule_id: str
    current_stage: RuleStage
    next_stage: RuleStage | None
    can_promote: bool
    blockers: list[str]
    metrics: dict[str, float | int | str]
    recommendation: str

    def summary(self) -> str:
        """Generate summary string."""
        status = "✓ Ready" if self.can_promote else "✗ Blocked"
        next_str = f" → {self.next_stage}" if self.next_stage else ""
        return f"{self.rule_id}: {self.current_stage}{next_str} [{status}]"


@dataclass
class RuleMetadata:
    """Metadata for tracking rule lifecycle.

    Attributes:
        rule_id: Rule identifier
        stage: Current lifecycle stage
        created_at: When rule was created
        stage_entered_at: When current stage was entered
        promotion_history: History of promotions
    """

    rule_id: str
    stage: RuleStage = RuleStage.EXPERIMENTAL
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    stage_entered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    promotion_history: list[tuple[RuleStage, datetime]] = field(default_factory=list)

    def promote_to(self, new_stage: RuleStage) -> None:
        """Promote rule to new stage.

        Args:
            new_stage: Target stage
        """
        now = datetime.now(UTC)
        self.promotion_history.append((self.stage, now))
        self.stage = new_stage
        self.stage_entered_at = now

    @property
    def age_at_stage_weeks(self) -> float:
        """Get weeks at current stage."""
        delta = datetime.now(UTC) - self.stage_entered_at
        return delta.days / 7.0

    @property
    def total_age_weeks(self) -> float:
        """Get total age in weeks."""
        delta = datetime.now(UTC) - self.created_at
        return delta.days / 7.0


class PromotionManager:
    """Manages rule promotion workflow.

    RFC-039: Automated promotion based on telemetry.

    Promotion Paths:
        Experimental → Verified → Core

    Usage:
        >>> manager = PromotionManager()
        >>> status = manager.check_promotion("rule_id", stats, metadata)
        >>> if status.can_promote:
        ...     manager.promote(metadata)
    """

    # Default requirements for each stage transition
    DEFAULT_REQUIREMENTS = {
        RuleStage.EXPERIMENTAL: StageRequirements(
            min_age_weeks=4,
            max_fp_rate=0.30,
            min_matches=50,
            min_feedback=10,
        ),
        RuleStage.VERIFIED: StageRequirements(
            min_age_weeks=12,
            max_fp_rate=0.10,
            min_matches=500,
            min_feedback=50,
        ),
    }

    def __init__(
        self,
        requirements: dict[RuleStage, StageRequirements] | None = None,
    ) -> None:
        """Initialize promotion manager.

        Args:
            requirements: Custom requirements per stage (optional)
        """
        self.requirements = requirements or self.DEFAULT_REQUIREMENTS
        self._metadata_store: dict[str, RuleMetadata] = {}

        logger.debug("PromotionManager initialized")

    def register_rule(
        self,
        rule_id: str,
        stage: RuleStage = RuleStage.EXPERIMENTAL,
        created_at: datetime | None = None,
    ) -> RuleMetadata:
        """Register a rule for tracking.

        Args:
            rule_id: Rule identifier
            stage: Initial stage
            created_at: Creation time (optional)

        Returns:
            RuleMetadata
        """
        now = created_at or datetime.now(UTC)
        metadata = RuleMetadata(
            rule_id=rule_id,
            stage=stage,
            created_at=now,
            stage_entered_at=now,
        )
        self._metadata_store[rule_id] = metadata

        logger.info(f"Registered rule {rule_id} at stage {stage}")
        return metadata

    def get_metadata(self, rule_id: str) -> RuleMetadata | None:
        """Get metadata for a rule.

        Args:
            rule_id: Rule identifier

        Returns:
            RuleMetadata or None
        """
        return self._metadata_store.get(rule_id)

    def check_promotion(
        self,
        rule_id: str,
        stats: RuleStatistics,
        metadata: RuleMetadata | None = None,
    ) -> PromotionStatus:
        """Check if a rule is eligible for promotion.

        Args:
            rule_id: Rule identifier
            stats: Rule statistics from telemetry
            metadata: Rule metadata (optional, uses stored if not provided)

        Returns:
            PromotionStatus
        """
        # Get or create metadata
        if metadata is None:
            metadata = self._metadata_store.get(rule_id)
            if metadata is None:
                metadata = self.register_rule(rule_id)

        current_stage = metadata.stage
        next_stage = self._get_next_stage(current_stage)

        # Core rules cannot be promoted further
        if next_stage is None:
            return PromotionStatus(
                rule_id=rule_id,
                current_stage=current_stage,
                next_stage=None,
                can_promote=False,
                blockers=["Already at highest stage (core)"],
                metrics=self._build_metrics(metadata, stats),
                recommendation="Rule is at core stage. No further promotion needed.",
            )

        # Check requirements
        requirements = self.requirements.get(current_stage)
        if requirements is None:
            return PromotionStatus(
                rule_id=rule_id,
                current_stage=current_stage,
                next_stage=next_stage,
                can_promote=False,
                blockers=["No requirements defined for current stage"],
                metrics=self._build_metrics(metadata, stats),
                recommendation="Configure requirements for this stage.",
            )

        blockers = self._check_blockers(metadata, stats, requirements)

        can_promote = len(blockers) == 0
        recommendation = self._generate_recommendation(current_stage, next_stage, blockers, stats)

        return PromotionStatus(
            rule_id=rule_id,
            current_stage=current_stage,
            next_stage=next_stage,
            can_promote=can_promote,
            blockers=blockers,
            metrics=self._build_metrics(metadata, stats),
            recommendation=recommendation,
        )

    def promote(
        self,
        metadata: RuleMetadata,
    ) -> bool:
        """Promote a rule to the next stage.

        Args:
            metadata: Rule metadata

        Returns:
            True if promoted, False if at max stage
        """
        next_stage = self._get_next_stage(metadata.stage)
        if next_stage is None:
            return False

        old_stage = metadata.stage
        metadata.promote_to(next_stage)

        # Update store
        self._metadata_store[metadata.rule_id] = metadata

        logger.info(f"Promoted {metadata.rule_id}: {old_stage} → {next_stage}")
        return True

    def get_promotion_candidates(
        self,
        all_stats: list[RuleStatistics],
    ) -> list[PromotionStatus]:
        """Get all rules eligible for promotion.

        Args:
            all_stats: Statistics for all rules

        Returns:
            List of rules ready for promotion
        """
        candidates = []

        for stats in all_stats:
            status = self.check_promotion(stats.rule_id, stats)
            if status.can_promote:
                candidates.append(status)

        return candidates

    def get_blocked_rules(
        self,
        all_stats: list[RuleStatistics],
    ) -> list[PromotionStatus]:
        """Get all rules blocked from promotion.

        Args:
            all_stats: Statistics for all rules

        Returns:
            List of blocked rules with reasons
        """
        blocked = []

        for stats in all_stats:
            status = self.check_promotion(stats.rule_id, stats)
            if not status.can_promote and status.next_stage is not None:
                blocked.append(status)

        return blocked

    def _get_next_stage(self, current: RuleStage) -> RuleStage | None:
        """Get the next stage after current.

        Args:
            current: Current stage

        Returns:
            Next stage or None if at max
        """
        if current == RuleStage.EXPERIMENTAL:
            return RuleStage.VERIFIED
        elif current == RuleStage.VERIFIED:
            return RuleStage.CORE
        else:
            return None

    def _check_blockers(
        self,
        metadata: RuleMetadata,
        stats: RuleStatistics,
        requirements: StageRequirements,
    ) -> list[str]:
        """Check promotion blockers.

        Args:
            metadata: Rule metadata
            stats: Rule statistics
            requirements: Stage requirements

        Returns:
            List of blocker messages
        """
        blockers = []

        # Check age
        age_weeks = metadata.age_at_stage_weeks
        if age_weeks < requirements.min_age_weeks:
            remaining = requirements.min_age_weeks - age_weeks
            blockers.append(
                f"Insufficient time at stage: {age_weeks:.1f} weeks "
                f"(need {requirements.min_age_weeks}, {remaining:.1f} more)"
            )

        # Check FP rate
        fp_rate = stats.false_positive_rate
        if fp_rate is not None and fp_rate > requirements.max_fp_rate:
            blockers.append(f"FP rate too high: {fp_rate:.1%} (max {requirements.max_fp_rate:.1%})")

        # Check match count
        if stats.total_matches < requirements.min_matches:
            blockers.append(f"Insufficient matches: {stats.total_matches} (need {requirements.min_matches})")

        # Check feedback count
        feedback_count = stats.suppressed_count + stats.confirmed_count
        if feedback_count < requirements.min_feedback:
            blockers.append(f"Insufficient feedback: {feedback_count} (need {requirements.min_feedback})")

        return blockers

    def _build_metrics(
        self,
        metadata: RuleMetadata,
        stats: RuleStatistics,
    ) -> dict[str, float | int | str]:
        """Build metrics dictionary.

        Args:
            metadata: Rule metadata
            stats: Rule statistics

        Returns:
            Metrics dict
        """
        fp_rate = stats.false_positive_rate
        return {
            "age_weeks": round(metadata.age_at_stage_weeks, 1),
            "total_age_weeks": round(metadata.total_age_weeks, 1),
            "total_matches": stats.total_matches,
            "feedback_count": stats.suppressed_count + stats.confirmed_count,
            "fp_rate": f"{fp_rate:.1%}" if fp_rate is not None else "N/A",
            "avg_confidence": round(stats.avg_confidence, 2),
        }

    def _generate_recommendation(
        self,
        current_stage: RuleStage,
        next_stage: RuleStage,
        blockers: list[str],
        stats: RuleStatistics,
    ) -> str:
        """Generate human-readable recommendation.

        Args:
            current_stage: Current stage
            next_stage: Target stage
            blockers: List of blockers
            stats: Rule statistics

        Returns:
            Recommendation string
        """
        if not blockers:
            return f"Rule is ready for promotion from {current_stage} to {next_stage}. All requirements met."

        # Prioritize recommendations
        if any("FP rate" in b for b in blockers):
            return "Reduce false positive rate before promotion. Consider refining patterns or adding guards."

        if any("time" in b.lower() for b in blockers):
            return f"Rule needs more time at {current_stage} stage. Continue monitoring quality metrics."

        if any("matches" in b.lower() for b in blockers):
            return "Rule needs more usage data. May indicate low coverage or overly specific patterns."

        if any("feedback" in b.lower() for b in blockers):
            return "Need more user feedback to assess quality. Encourage users to confirm or suppress matches."

        return f"Address blockers before promotion: {', '.join(blockers)}"
