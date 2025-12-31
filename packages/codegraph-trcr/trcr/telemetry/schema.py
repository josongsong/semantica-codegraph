"""Telemetry Schema - RFC-036.

Data structures for telemetry collection.

Key Concepts:
    - RuleMatchTelemetry: Individual match event
    - SessionTelemetry: Session-level aggregation
    - RuleStatistics: Per-rule statistics

Usage:
    >>> event = RuleMatchTelemetry(
    ...     rule_id="sql_injection_sink",
    ...     atom_id="sqlite_cursor_execute",
    ...     session_id="session_123",
    ...     base_type="sqlite3.Cursor",
    ...     call="execute",
    ...     confidence=0.9,
    ...     tier="tier1",
    ...     reported=True,
    ... )
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4


@dataclass
class RuleMatchTelemetry:
    """Individual match event telemetry.

    RFC-036: Collected for analysis and self-improvement.

    Collected when:
        - Tier3 rules match
        - Low-confidence matches (< 0.7)
        - User provides feedback

    Attributes:
        rule_id: Rule that matched
        atom_id: Specific atom that matched
        session_id: Session identifier
        base_type: Entity base type
        call: Entity call name
        confidence: Match confidence
        tier: Rule tier
        reported: Whether match was reported
        user_action: User feedback (if any)
        timestamp: When match occurred
    """

    # Identity
    rule_id: str
    atom_id: str
    session_id: str

    # Match context
    base_type: str
    call: str | None

    # Match quality
    confidence: float
    tier: Literal["tier1", "tier2", "tier3"]

    # Reporting
    reported: bool

    # Optional fields (with defaults)
    read: str | None = None

    # User feedback (optional)
    user_action: Literal["suppress", "confirm", "ignore"] | None = None

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Unique event ID
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate telemetry event."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")

        if self.tier not in ("tier1", "tier2", "tier3"):
            raise ValueError(f"Invalid tier: {self.tier}")


@dataclass
class SessionTelemetry:
    """Session-level telemetry aggregation.

    Aggregates events for a single analysis session.
    """

    session_id: str
    start_time: datetime
    end_time: datetime | None = None

    # Counts
    total_matches: int = 0
    reported_matches: int = 0
    suppressed_matches: int = 0
    confirmed_matches: int = 0

    # By tier
    tier1_matches: int = 0
    tier2_matches: int = 0
    tier3_matches: int = 0

    # Events
    events: list[RuleMatchTelemetry] = field(default_factory=list)

    def add_event(self, event: RuleMatchTelemetry) -> None:
        """Add event to session.

        Args:
            event: Match event
        """
        self.events.append(event)
        self.total_matches += 1

        if event.reported:
            self.reported_matches += 1

        if event.user_action == "suppress":
            self.suppressed_matches += 1
        elif event.user_action == "confirm":
            self.confirmed_matches += 1

        if event.tier == "tier1":
            self.tier1_matches += 1
        elif event.tier == "tier2":
            self.tier2_matches += 1
        else:
            self.tier3_matches += 1

    def close(self) -> None:
        """Close session."""
        self.end_time = datetime.now(UTC)

    @property
    def duration_seconds(self) -> float | None:
        """Get session duration in seconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class RuleStatistics:
    """Per-rule statistics from telemetry.

    Aggregated from multiple sessions.
    """

    rule_id: str
    atom_id: str

    # Match counts
    total_matches: int = 0
    reported_matches: int = 0

    # User feedback
    suppressed_count: int = 0
    confirmed_count: int = 0
    ignored_count: int = 0

    # Confidence stats
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0

    # Patterns matched
    patterns_seen: set[str] = field(default_factory=set)

    def add_match(self, event: RuleMatchTelemetry) -> None:
        """Add match event to statistics.

        Args:
            event: Match event
        """
        self.total_matches += 1

        if event.reported:
            self.reported_matches += 1

        if event.user_action == "suppress":
            self.suppressed_count += 1
        elif event.user_action == "confirm":
            self.confirmed_count += 1
        elif event.user_action == "ignore":
            self.ignored_count += 1

        # Update confidence stats
        self.min_confidence = min(self.min_confidence, event.confidence)
        self.max_confidence = max(self.max_confidence, event.confidence)

        # Rolling average
        n = self.total_matches
        self.avg_confidence = (self.avg_confidence * (n - 1) + event.confidence) / n

        # Track patterns
        pattern = f"{event.base_type}.{event.call or event.read or '*'}"
        self.patterns_seen.add(pattern)

    @property
    def false_positive_rate(self) -> float | None:
        """Estimate false positive rate.

        FP rate = suppressed / (suppressed + confirmed)

        Returns:
            FP rate [0, 1] or None if no feedback
        """
        total_feedback = self.suppressed_count + self.confirmed_count
        if total_feedback == 0:
            return None
        return self.suppressed_count / total_feedback

    @property
    def is_healthy(self) -> bool:
        """Check if rule is healthy.

        Healthy if:
            - FP rate < 50% OR
            - Not enough data (< 10 feedback events)
        """
        fp_rate = self.false_positive_rate
        if fp_rate is None:
            return True  # No data, assume healthy
        return fp_rate < 0.5


@dataclass
class PatternStats:
    """Statistics for a specific pattern.

    Used by FrequencyAnalyzer.
    """

    pattern: str
    count: int
    avg_confidence: float
    suppressed: int = 0
    confirmed: int = 0

    @property
    def false_positive_rate(self) -> float | None:
        """Estimate FP rate for this pattern."""
        total = self.suppressed + self.confirmed
        if total == 0:
            return None
        return self.suppressed / total
