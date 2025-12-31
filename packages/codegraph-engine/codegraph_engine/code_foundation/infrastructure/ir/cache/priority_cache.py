"""
RFC-039 P0.5: Priority-based Memory Cache

Extends MemoryCache with priority-based eviction instead of pure LRU.

Priority Score Formula:
    priority = frequency * recency_weight * (1 / size_factor)

Where:
- frequency: Access count (more accessed = higher priority)
- recency_weight: Exponential decay based on time since last access
- size_factor: Larger items have lower priority (evicted first)

Use Cases:
- Keep frequently accessed small files in cache
- Evict large, rarely accessed files first
- Balance between access patterns and memory usage

Usage:
    cache = PriorityMemoryCache(max_size=500, max_bytes=512*1024*1024)

    # Get with automatic priority tracking
    value = cache.get(key)

    # Set with automatic size estimation
    cache.set(key, ir_doc)

    # Eviction happens automatically based on priority
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .core import BaseCacheStats


@dataclass
class CacheEntry:
    """
    Cache entry with priority metadata.

    Tracks access patterns for priority-based eviction.
    """

    value: Any
    size_bytes: int
    access_count: int = 1
    last_access_time: float = field(default_factory=time.time)
    created_time: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update access metadata on cache hit."""
        self.access_count += 1
        self.last_access_time = time.time()

    def priority_score(self, current_time: float, decay_factor: float = 0.001) -> float:
        """
        Calculate priority score for eviction.

        Higher score = higher priority = less likely to evict.

        Args:
            current_time: Current timestamp
            decay_factor: Controls how fast recency decays (default: 0.001)

        Returns:
            Priority score (higher = keep, lower = evict)
        """
        # Recency: Exponential decay
        time_since_access = current_time - self.last_access_time
        recency_weight = 2.0 ** (-decay_factor * time_since_access)

        # Size factor: Larger items have lower priority
        # Normalize to 1KB baseline (1000 bytes -> 1.0)
        size_factor = max(1.0, self.size_bytes / 1000.0)

        # Priority = frequency * recency / size
        priority = self.access_count * recency_weight / size_factor

        return priority


@dataclass
class PriorityCacheStats(BaseCacheStats):
    """Extended stats for priority cache."""

    priority_evictions: int = 0  # Evictions by priority (not just LRU)
    current_bytes: int = 0

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary."""
        base = super().to_dict()
        base.update(
            {
                "priority_evictions": self.priority_evictions,
                "current_bytes": self.current_bytes,
            }
        )
        return base


class PriorityMemoryCache:
    """
    Memory cache with priority-based eviction.

    RFC-039 P0.5: More intelligent eviction than pure LRU.

    Eviction Strategy:
    1. When memory limit exceeded, calculate priority for all entries
    2. Evict lowest priority entries until under limit
    3. Priority = frequency * recency / size

    Thread Safety:
    - All operations are lock-protected
    - NOT multiprocess-safe (each process has separate cache)

    Performance:
    - Get: O(1)
    - Set: O(1) amortized, O(n) when eviction needed
    - Eviction: O(n log n) for sorting by priority
    """

    def __init__(
        self,
        max_size: int = 500,
        max_bytes: int = 512 * 1024 * 1024,  # 512MB
        decay_factor: float = 0.001,
    ):
        """
        Initialize priority memory cache.

        Args:
            max_size: Maximum number of entries
            max_bytes: Maximum memory usage in bytes
            decay_factor: Recency decay factor (higher = faster decay)
        """
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._max_bytes = max_bytes
        self._decay_factor = decay_factor
        self._current_bytes = 0
        self._lock = threading.Lock()

        # Stats
        self._stats = PriorityCacheStats()

    def _estimate_size(self, value: Any) -> int:
        """
        Estimate object size in bytes.

        Uses estimated_size if available, fallback to heuristic.
        """
        if hasattr(value, "estimated_size") and isinstance(getattr(value, "estimated_size", None), (int, float)):
            return int(value.estimated_size)

        # Fallback heuristic
        try:
            nodes = getattr(value, "nodes", [])
            edges = getattr(value, "edges", [])
            nodes_len = len(nodes) if isinstance(nodes, (list, tuple)) else 0
            edges_len = len(edges) if isinstance(edges, (list, tuple)) else 0
            return nodes_len * 200 + edges_len * 100 + 1000
        except (TypeError, AttributeError):
            return 1000

    def get(self, key: str) -> Any | None:
        """
        Get cached value with access tracking.

        Args:
            key: Cache key string

        Returns:
            Cached value or None on miss
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                entry.touch()
                self._stats.hits += 1
                return entry.value

            self._stats.misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        """
        Set cached value with automatic eviction.

        Args:
            key: Cache key string
            value: Value to cache
        """
        with self._lock:
            if self._max_size == 0:
                return

            size = self._estimate_size(value)

            # Update existing entry
            if key in self._cache:
                old_entry = self._cache[key]
                self._current_bytes -= old_entry.size_bytes
                old_entry.value = value
                old_entry.size_bytes = size
                old_entry.touch()
                self._current_bytes += size
                return

            # Evict if needed
            self._evict_if_needed(size)

            # Add new entry
            entry = CacheEntry(value=value, size_bytes=size)
            self._cache[key] = entry
            self._current_bytes += size

    def _evict_if_needed(self, new_size: int) -> None:
        """
        Evict entries based on priority until constraints satisfied.

        Must be called with lock held.
        """
        # Check if eviction needed
        if self._current_bytes + new_size <= self._max_bytes and len(self._cache) < self._max_size:
            return

        # Calculate priority for all entries
        current_time = time.time()
        priorities = [
            (key, entry.priority_score(current_time, self._decay_factor)) for key, entry in self._cache.items()
        ]

        # Sort by priority (lowest first = evict first)
        priorities.sort(key=lambda x: x[1])

        # Evict until constraints satisfied
        for key, _priority in priorities:
            if self._current_bytes + new_size <= self._max_bytes and len(self._cache) < self._max_size:
                break

            entry = self._cache.pop(key)
            self._current_bytes -= entry.size_bytes
            self._stats.evictions += 1
            self._stats.priority_evictions += 1

    def delete(self, key: str) -> bool:
        """Delete cached entry."""
        with self._lock:
            if key in self._cache:
                entry = self._cache.pop(key)
                self._current_bytes -= entry.size_bytes
                return True
            return False

    def clear(self) -> None:
        """Clear all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0
            self._stats = PriorityCacheStats()

    def stats(self) -> PriorityCacheStats:
        """Get cache statistics."""
        with self._lock:
            result = PriorityCacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                priority_evictions=self._stats.priority_evictions,
                current_bytes=self._current_bytes,
            )
            return result

    def get_entry_priorities(self) -> list[tuple[str, float, int, int]]:
        """
        Get priority info for all entries (for debugging/analysis).

        Returns:
            List of (key, priority, access_count, size_bytes)
        """
        with self._lock:
            current_time = time.time()
            return [
                (
                    key,
                    entry.priority_score(current_time, self._decay_factor),
                    entry.access_count,
                    entry.size_bytes,
                )
                for key, entry in self._cache.items()
            ]


__all__ = [
    "CacheEntry",
    "PriorityCacheStats",
    "PriorityMemoryCache",
]
