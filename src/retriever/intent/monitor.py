"""
Intent Fallback Monitoring

Tracks and alerts on LLM intent classification fallback rates.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FallbackStats:
    """Statistics for intent fallback monitoring."""

    total_classifications: int = 0
    llm_successes: int = 0
    fallback_count: int = 0
    reasons: Counter = field(default_factory=Counter)
    last_reset: datetime = field(default_factory=datetime.now)

    @property
    def fallback_rate(self) -> float:
        """Calculate fallback rate as percentage."""
        if self.total_classifications == 0:
            return 0.0
        return self.fallback_count / self.total_classifications

    @property
    def success_rate(self) -> float:
        """Calculate LLM success rate as percentage."""
        if self.total_classifications == 0:
            return 0.0
        return self.llm_successes / self.total_classifications


class IntentFallbackMonitor:
    """
    Monitors LLM intent classification fallback rates.

    Tracks why and how often the system falls back to rule-based
    classification, and alerts when rates exceed thresholds.
    """

    def __init__(self, alert_threshold: int = 100, alert_rate: float = 0.3):
        """
        Initialize fallback monitor.

        Args:
            alert_threshold: Number of classifications before checking rate
            alert_rate: Fallback rate threshold for alerting (0.0-1.0)
        """
        self.alert_threshold = alert_threshold
        self.alert_rate = alert_rate
        self.stats = FallbackStats()

    def log_llm_success(self, latency_ms: float):
        """
        Log successful LLM classification.

        Args:
            latency_ms: Time taken for classification
        """
        self.stats.total_classifications += 1
        self.stats.llm_successes += 1

        self._check_alert()

    def log_fallback(self, reason: str):
        """
        Log fallback to rule-based classification.

        Args:
            reason: Reason for fallback (e.g., "timeout", "llm_error", "parse_error")
        """
        self.stats.total_classifications += 1
        self.stats.fallback_count += 1
        self.stats.reasons[reason] += 1

        self._check_alert()

    def _check_alert(self):
        """Check if alert threshold is reached and log warning."""
        if self.stats.total_classifications % self.alert_threshold == 0:
            fallback_rate = self.stats.fallback_rate

            if fallback_rate > self.alert_rate:
                logger.warning(
                    f"⚠️  High LLM intent fallback rate detected:\n"
                    f"  Total classifications: {self.stats.total_classifications}\n"
                    f"  LLM success rate: {self.stats.success_rate:.1%}\n"
                    f"  Fallback rate: {fallback_rate:.1%}\n"
                    f"  Top fallback reasons: {dict(self.stats.reasons.most_common(5))}"
                )
            else:
                logger.info(
                    f"✓ Intent classification stats (last {self.alert_threshold}):\n"
                    f"  LLM success rate: {self.stats.success_rate:.1%}\n"
                    f"  Fallback rate: {fallback_rate:.1%}"
                )

    def get_stats(self) -> FallbackStats:
        """
        Get current fallback statistics.

        Returns:
            Current FallbackStats snapshot
        """
        return self.stats

    def reset(self):
        """Reset all statistics."""
        self.stats = FallbackStats()
        logger.info("Intent fallback monitor statistics reset")

    def get_summary(self) -> dict:
        """
        Get summary statistics as dict.

        Returns:
            Dictionary with current statistics
        """
        return {
            "total_classifications": self.stats.total_classifications,
            "llm_successes": self.stats.llm_successes,
            "fallback_count": self.stats.fallback_count,
            "success_rate": self.stats.success_rate,
            "fallback_rate": self.stats.fallback_rate,
            "reasons": dict(self.stats.reasons),
            "last_reset": self.stats.last_reset.isoformat(),
        }
