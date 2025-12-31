"""Match Cache - LRU Cache for Match Results.

Purpose: Cache (entity_id, rule_id) → Match results.

Features:
    - LRU eviction policy
    - Configurable max size
    - Thread-safe
    - Statistics tracking
    - Observability (logging)

Usage:
    >>> cache = MatchCache(max_size=1000)
    >>> cache.set("entity1", "rule1", match)
    >>> cached = cache.get("entity1", "rule1")
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class MatchCache:
    """LRU cache for match results.

    Thread-safe LRU cache with statistics.

    Example:
        >>> cache = MatchCache(max_size=1000)
        >>> cache.set("e1", "r1", match_result)
        >>> result = cache.get("e1", "r1")
    """

    def __init__(self, max_size: int = 10000) -> None:
        """Initialize cache.

        Args:
            max_size: Maximum number of entries
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.max_size = max_size
        self._cache: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._lock = Lock()

        # Statistics
        self._hits = 0
        self._misses = 0

    def get(self, entity_id: str, rule_id: str) -> Any | None:
        """Get cached match result.

        Args:
            entity_id: Entity identifier
            rule_id: Rule identifier

        Returns:
            Cached result or None
        """
        key = (entity_id, rule_id)

        with self._lock:
            if key in self._cache:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]

            self._misses += 1
            return None

    def set(self, entity_id: str, rule_id: str, result: Any) -> None:
        """Set cache entry.

        Args:
            entity_id: Entity identifier
            rule_id: Rule identifier
            result: Match result
        """
        key = (entity_id, rule_id)

        with self._lock:
            # Update existing
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = result
                return

            # Add new
            self._cache[key] = result

            # Evict LRU if needed
            if len(self._cache) > self.max_size:
                evicted_key, _ = self._cache.popitem(last=False)  # Remove oldest
                logger.debug(f"Cache evicted: {evicted_key}")

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats with current metrics
        """
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._cache),
                max_size=self.max_size,
            )

    def size(self) -> int:
        """Get current cache size.

        Returns:
            Number of entries
        """
        with self._lock:
            return len(self._cache)
