"""
Adaptive Span Pool (LRU Thrash Mitigation)

Auto-adjusts max_size based on access patterns.
Prevents thrashing in large monorepos.

Design:
- Monitor eviction rate
- If thrash detected (eviction_rate > 50%), increase max_size
- Bounded growth (max: 100K spans)
- Observable: logs adjustments
"""

from codegraph_engine.code_foundation.infrastructure.ir.models.span_pool import SpanPool
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)


class AdaptiveSpanPool:
    """
    Adaptive Span pool with thrash detection.

    Monitors SpanPool stats and auto-adjusts max_size to prevent thrashing.

    Thrash Detection:
    - If eviction_rate > 50% over last N requests, increase max_size
    - Growth: max_size *= 2 (bounded by 100K)

    Usage:
        # In LayeredIRBuilder or long-running service
        adaptive = AdaptiveSpanPool()

        # Periodically check (e.g., after each file)
        adaptive.check_and_adjust()
    """

    def __init__(
        self,
        thrash_threshold: float = 0.5,  # 50% eviction rate
        max_pool_size: int = 100_000,  # 100K cap
        check_interval: int = 100,  # Check every 100 requests
    ):
        """
        Initialize adaptive pool.

        Args:
            thrash_threshold: Eviction rate threshold (0.0-1.0)
            max_pool_size: Maximum allowed pool size
            check_interval: Check stats every N requests
        """
        self.thrash_threshold = thrash_threshold
        self.max_pool_size = max_pool_size
        self.check_interval = check_interval

        self._last_check_total = 0
        self._adjustments_made = 0

    def check_and_adjust(self) -> bool:
        """
        Check for thrashing and adjust max_size if needed.

        Returns:
            True if adjustment was made, False otherwise
        """
        stats = SpanPool.get_stats()
        total = stats["total_requests"]

        # Check interval
        if total - self._last_check_total < self.check_interval:
            return False

        self._last_check_total = total

        # Calculate eviction rate over recent requests
        eviction_count = stats["eviction_count"]
        eviction_rate = eviction_count / total if total > 0 else 0.0

        # Thrash detection
        if eviction_rate > self.thrash_threshold:
            current_max = SpanPool._max_size

            # Don't grow beyond cap
            if current_max >= self.max_pool_size:
                logger.warning(
                    "span_pool_thrash_at_max",
                    current_max=current_max,
                    eviction_rate=f"{eviction_rate:.1%}",
                    message="Pool at max size but still thrashing. Consider increasing max_pool_size.",
                )
                return False

            # Increase max_size
            new_max = min(current_max * 2, self.max_pool_size)
            SpanPool._max_size = new_max
            self._adjustments_made += 1

            logger.info(
                "span_pool_adjusted",
                old_max=current_max,
                new_max=new_max,
                eviction_rate=f"{eviction_rate:.1%}",
                adjustments_made=self._adjustments_made,
            )

            return True

        return False

    def get_stats(self) -> dict:
        """Get adaptive pool statistics"""
        return {
            "adjustments_made": self._adjustments_made,
            "current_max_size": SpanPool._max_size,
            "last_check_total": self._last_check_total,
        }
