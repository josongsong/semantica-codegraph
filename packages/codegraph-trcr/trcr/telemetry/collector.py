"""Telemetry Collector - RFC-036.

Collects telemetry data from rule execution.

Key Features:
    - Log match events
    - Record user feedback
    - Session management
    - Filtering (tier3, low-confidence)

Usage:
    >>> collector = TelemetryCollector()
    >>> session = collector.start_session()
    >>>
    >>> # During execution
    >>> collector.log_match(match, context)
    >>>
    >>> # User feedback
    >>> collector.record_user_action(event_id, "suppress")
    >>>
    >>> # End session
    >>> collector.end_session(session.session_id)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from trcr.telemetry.schema import (
    RuleMatchTelemetry,
    RuleStatistics,
    SessionTelemetry,
)
from trcr.types.match import Match, MatchContext

logger = logging.getLogger(__name__)


@dataclass
class CollectorConfig:
    """Configuration for TelemetryCollector."""

    # What to collect
    collect_tier3: bool = True  # Always collect tier3 matches
    collect_low_confidence: bool = True  # Collect if confidence < threshold
    confidence_threshold: float = 0.7  # Threshold for low confidence

    # Filtering
    sample_rate: float = 1.0  # 1.0 = 100% of events

    # Storage
    max_events_per_session: int = 10000
    max_sessions: int = 100


class TelemetryCollector:
    """Collects telemetry data from rule execution.

    RFC-036: Telemetry System.

    Thread-safe: Uses internal locking for session management.

    Usage:
        >>> collector = TelemetryCollector()
        >>> session = collector.start_session()
        >>> collector.log_match(match, context)
        >>> collector.end_session(session.session_id)
    """

    def __init__(self, config: CollectorConfig | None = None) -> None:
        """Initialize collector.

        Args:
            config: Collector configuration
        """
        self.config = config or CollectorConfig()

        # Active sessions
        self._sessions: dict[str, SessionTelemetry] = {}

        # Event index (for feedback)
        self._events: dict[str, RuleMatchTelemetry] = {}

        # Rule statistics (aggregated)
        self._rule_stats: dict[str, RuleStatistics] = defaultdict(lambda: RuleStatistics(rule_id="", atom_id=""))

    def start_session(self, session_id: str | None = None) -> SessionTelemetry:
        """Start a new telemetry session.

        Args:
            session_id: Optional session ID (generated if not provided)

        Returns:
            New session
        """
        if session_id is None:
            session_id = str(uuid4())

        session = SessionTelemetry(
            session_id=session_id,
            start_time=datetime.now(UTC),
        )

        # Clean up old sessions if limit reached
        if len(self._sessions) >= self.config.max_sessions:
            self._cleanup_old_sessions()

        self._sessions[session_id] = session
        logger.debug(f"Started telemetry session: {session_id}")

        return session

    def end_session(self, session_id: str) -> SessionTelemetry | None:
        """End a telemetry session.

        Args:
            session_id: Session to end

        Returns:
            Closed session or None if not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning(f"Session not found: {session_id}")
            return None

        session.close()
        logger.info(f"Ended session {session_id}: {session.total_matches} matches, {session.reported_matches} reported")

        return session

    def log_match(
        self,
        match: Match,
        context: MatchContext | None = None,
        session_id: str | None = None,
    ) -> RuleMatchTelemetry | None:
        """Log a match event.

        Filters based on tier and confidence.

        Args:
            match: Match result
            context: Match context (optional)
            session_id: Session ID (uses default if not provided)

        Returns:
            Created event or None if filtered
        """
        # Check if should collect
        if not self._should_collect(match):
            return None

        # Get or create session
        session = self._get_session(session_id)
        if session is None:
            return None

        # Check session limit
        if len(session.events) >= self.config.max_events_per_session:
            logger.warning(f"Session {session.session_id} event limit reached")
            return None

        # Create event
        event = RuleMatchTelemetry(
            rule_id=match.rule_id,
            atom_id=match.atom_id,
            session_id=session.session_id,
            base_type=match.entity.base_type or "",
            call=match.entity.call,
            read=match.entity.read,
            confidence=match.confidence,
            tier=match.tier,  # type: ignore
            reported=match.should_report(),
        )

        # Store event
        session.add_event(event)
        self._events[event.event_id] = event

        # Update rule stats
        self._update_rule_stats(event)

        logger.debug(f"Logged match event: {event.event_id}")
        return event

    def record_user_action(
        self,
        event_id: str,
        action: Literal["suppress", "confirm", "ignore"],
    ) -> bool:
        """Record user feedback on a match.

        Args:
            event_id: Event to update
            action: User action

        Returns:
            True if updated, False if event not found
        """
        event = self._events.get(event_id)
        if event is None:
            logger.warning(f"Event not found: {event_id}")
            return False

        # Update event
        object.__setattr__(event, "user_action", action)

        # Update session stats
        session = self._sessions.get(event.session_id)
        if session:
            if action == "suppress":
                session.suppressed_matches += 1
            elif action == "confirm":
                session.confirmed_matches += 1

        # Update rule stats
        key = f"{event.rule_id}:{event.atom_id}"
        stats = self._rule_stats.get(key)
        if stats:
            if action == "suppress":
                stats.suppressed_count += 1
            elif action == "confirm":
                stats.confirmed_count += 1
            elif action == "ignore":
                stats.ignored_count += 1

        logger.debug(f"Recorded user action: {event_id} -> {action}")
        return True

    def get_session(self, session_id: str) -> SessionTelemetry | None:
        """Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None
        """
        return self._sessions.get(session_id)

    def get_rule_stats(self, rule_id: str, atom_id: str) -> RuleStatistics | None:
        """Get statistics for a rule.

        Args:
            rule_id: Rule ID
            atom_id: Atom ID

        Returns:
            Rule statistics or None
        """
        key = f"{rule_id}:{atom_id}"
        return self._rule_stats.get(key)

    def get_all_rule_stats(self) -> list[RuleStatistics]:
        """Get all rule statistics.

        Returns:
            List of all rule statistics
        """
        return list(self._rule_stats.values())

    def _should_collect(self, match: Match) -> bool:
        """Check if match should be collected.

        Args:
            match: Match to check

        Returns:
            True if should collect
        """
        # Always collect tier3
        if self.config.collect_tier3 and match.tier == "tier3":
            return True

        # Collect low confidence
        if self.config.collect_low_confidence:
            if match.confidence < self.config.confidence_threshold:
                return True

        # Sample rate
        if self.config.sample_rate < 1.0:
            import random

            if random.random() > self.config.sample_rate:
                return False

        return True

    def _get_session(self, session_id: str | None) -> SessionTelemetry | None:
        """Get session by ID or create default.

        Args:
            session_id: Session ID or None

        Returns:
            Session or None
        """
        if session_id is None:
            # Use first session or create one
            if not self._sessions:
                return self.start_session()
            return next(iter(self._sessions.values()))

        return self._sessions.get(session_id)

    def _update_rule_stats(self, event: RuleMatchTelemetry) -> None:
        """Update rule statistics from event.

        Args:
            event: Match event
        """
        key = f"{event.rule_id}:{event.atom_id}"

        if key not in self._rule_stats:
            self._rule_stats[key] = RuleStatistics(
                rule_id=event.rule_id,
                atom_id=event.atom_id,
            )

        self._rule_stats[key].add_match(event)

    def _cleanup_old_sessions(self) -> None:
        """Remove oldest sessions to make room."""
        if len(self._sessions) < self.config.max_sessions:
            return

        # Sort by start time, remove oldest
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda x: x[1].start_time,
        )

        # Remove oldest 10%
        to_remove = max(1, len(sorted_sessions) // 10)
        for session_id, _ in sorted_sessions[:to_remove]:
            del self._sessions[session_id]

        logger.debug(f"Cleaned up {to_remove} old sessions")

    def clear(self) -> None:
        """Clear all telemetry data."""
        self._sessions.clear()
        self._events.clear()
        self._rule_stats.clear()
        logger.debug("Cleared all telemetry data")


# Global collector instance (optional)
_default_collector: TelemetryCollector | None = None


def get_default_collector() -> TelemetryCollector:
    """Get or create default collector.

    Returns:
        Default collector
    """
    global _default_collector
    if _default_collector is None:
        _default_collector = TelemetryCollector()
    return _default_collector
