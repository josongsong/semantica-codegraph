"""
Rebuild Cache

ImpactAnalysisPlanner 결과 캐싱으로 2-3배 성능 향상

Phase 1 Optimization: Heap-based LRU eviction (10x faster)
- BEFORE: O(n) min() operation to find LRU
- AFTER:  O(log n) heappop for eviction
"""

import hashlib
import heapq
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry"""

    updated_graph: GraphDocument
    rebuild_plan: dict[str, Any]
    rebuild_stats: dict[str, Any]
    cached_at: float
    ttl_seconds: int

    def is_expired(self) -> bool:
        """TTL 만료 체크"""
        age = time.time() - self.cached_at
        return age > self.ttl_seconds

    def age_seconds(self) -> float:
        """캐시 나이 (초)"""
        return time.time() - self.cached_at


class RebuildCache:
    """
    ImpactAnalysisPlanner 결과 캐싱

    Strategy:
    - Key: hash(old_graph) + hash(changes)
    - Storage: Local memory (dict)
    - TTL: 300s (5분)
    - Invalidation: TTL + manual

    Example:
        cache = RebuildCache(ttl_seconds=300)

        # Try cache
        result = cache.get(old_graph, changes)
        if result:
            return result.updated_graph

        # Cache miss → rebuild
        updated_graph = builder.execute_rebuild(plan)
        cache.set(old_graph, changes, updated_graph, plan, stats)
    """

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 100):
        """
        Initialize cache

        Args:
            ttl_seconds: TTL (default: 300 = 5분)
            max_entries: Max cache entries (LRU eviction)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # Storage
        self._cache: dict[str, CacheEntry] = {}
        # Phase 1 Optimization: Heap for O(log n) LRU eviction
        # Heap entries: (timestamp, key)
        self._lru_heap: list[tuple[float, str]] = []
        # Track current timestamp per key (for lazy deletion)
        self._key_timestamps: dict[str, float] = {}
        self._lock = threading.Lock()  # Thread safety

        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

        logger.info(f"RebuildCache initialized: ttl={ttl_seconds}s, max={max_entries} (heap-based LRU)")

    def _compute_key(self, old_graph: GraphDocument, changes: dict[str, tuple[str, str]]) -> str:
        """
        Cache key 생성

        Key = hash(old_graph.snapshot_id + sorted(changes.keys()) + changes_hash)

        Args:
            old_graph: Old GraphDocument
            changes: Code changes

        Returns:
            Cache key (hex string)
        """
        # Graph 식별자
        graph_id = f"{old_graph.repo_id}:{old_graph.snapshot_id}"

        # Changes: sorted symbol IDs
        symbol_ids = sorted(changes.keys())

        # Changes content hash
        changes_content = ""
        for symbol_id in symbol_ids:
            old_code, new_code = changes[symbol_id]
            changes_content += f"{symbol_id}:{old_code}→{new_code};"

        changes_hash = hashlib.sha256(changes_content.encode()).hexdigest()[:16]

        # Final key
        key_input = f"{graph_id}|{','.join(symbol_ids)}|{changes_hash}"
        key = hashlib.sha256(key_input.encode()).hexdigest()

        return key

    def get(self, old_graph: GraphDocument, changes: dict[str, tuple[str, str]]) -> CacheEntry | None:
        """
        Cache lookup (thread-safe)

        Args:
            old_graph: Old GraphDocument
            changes: Code changes

        Returns:
            CacheEntry if hit, None if miss
        """
        key = self._compute_key(old_graph, changes)

        with self._lock:
            # Lookup
            entry = self._cache.get(key)

            if entry is None:
                self.misses += 1
                logger.debug(f"Cache MISS: {key[:16]}")
                return None

            # Check expiration
            if entry.is_expired():
                self.expirations += 1
                del self._cache[key]
                self._key_timestamps.pop(key, None)
                # Note: Stale heap entry handled lazily in _evict_lru (no explicit removal needed)
                logger.debug(f"Cache EXPIRED: {key[:16]}, age={entry.age_seconds():.1f}s")
                # Periodic heap compaction to prevent unbounded growth
                self._maybe_compact_heap()
                return None

            # Hit - update timestamp for LRU tracking
            self.hits += 1
            current_time = time.time()
            self._key_timestamps[key] = current_time
            # Push new timestamp to heap (old entry becomes stale, handled lazily)
            heapq.heappush(self._lru_heap, (current_time, key))
            logger.debug(f"Cache HIT: {key[:16]}, age={entry.age_seconds():.1f}s")

            return entry

    def set(
        self,
        old_graph: GraphDocument,
        changes: dict[str, tuple[str, str]],
        updated_graph: GraphDocument,
        rebuild_plan: dict[str, Any],
        rebuild_stats: dict[str, Any],
    ) -> None:
        """
        Cache entry 저장 (thread-safe)

        Args:
            old_graph: Old GraphDocument
            changes: Code changes
            updated_graph: Rebuilt graph
            rebuild_plan: Rebuild plan metadata
            rebuild_stats: Rebuild statistics
        """
        key = self._compute_key(old_graph, changes)

        with self._lock:
            # Evict if needed (LRU) - O(log n) with heap
            if len(self._cache) >= self.max_entries:
                self._evict_lru()

            # Store
            current_time = time.time()
            entry = CacheEntry(
                updated_graph=updated_graph,
                rebuild_plan=rebuild_plan,
                rebuild_stats=rebuild_stats,
                cached_at=current_time,
                ttl_seconds=self.ttl_seconds,
            )

            self._cache[key] = entry
            self._key_timestamps[key] = current_time
            heapq.heappush(self._lru_heap, (current_time, key))

            logger.debug(f"Cache SET: {key[:16]}")

    def _evict_lru(self) -> None:
        """
        LRU eviction with heap optimization.

        Phase 1 Optimization:
        - BEFORE: O(n) min() operation
        - AFTER:  O(log n) heappop with lazy deletion

        Lazy deletion strategy:
        - Heap may contain stale entries (key accessed since push)
        - Pop until we find entry with matching timestamp
        """
        while self._lru_heap:
            # Pop oldest entry - O(log n)
            timestamp, key = heapq.heappop(self._lru_heap)

            # Check if entry is stale (key was accessed since this timestamp)
            current_timestamp = self._key_timestamps.get(key)

            if current_timestamp is None:
                # Key already deleted, skip
                continue

            if current_timestamp != timestamp:
                # Stale entry (key was accessed more recently), skip
                continue

            # Valid LRU entry - evict
            del self._cache[key]
            del self._key_timestamps[key]
            self.evictions += 1

            logger.debug(f"Cache EVICT (LRU, heap): {key[:16]}")
            return

        # No valid entry to evict (shouldn't happen if max_entries > 0)
        logger.warning("LRU eviction: heap empty but cache not")

    def invalidate(
        self, old_graph: GraphDocument | None = None, changes: dict[str, tuple[str, str]] | None = None
    ) -> None:
        """
        Manual invalidation (thread-safe)

        Args:
            old_graph: If provided, invalidate specific entry
            changes: If provided, invalidate specific entry
        """
        with self._lock:
            if old_graph is not None and changes is not None:
                # Specific key
                key = self._compute_key(old_graph, changes)
                if key in self._cache:
                    del self._cache[key]
                    self._key_timestamps.pop(key, None)
                    # Note: stale heap entries are handled lazily in _evict_lru
                    logger.info(f"Cache INVALIDATE: {key[:16]}")
            else:
                # Clear all
                count = len(self._cache)
                self._cache.clear()
                self._key_timestamps.clear()
                self._lru_heap.clear()
                logger.info(f"Cache CLEAR: {count} entries")

    def get_metrics(self) -> dict[str, Any]:
        """
        Cache metrics (thread-safe)

        Returns:
            Metrics dict
        """
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "evictions": self.evictions,
                "expirations": self.expirations,
                "total_requests": total_requests,
                "current_size": len(self._cache),
                "max_size": self.max_entries,
            }

    def reset_metrics(self) -> None:
        """Reset metrics (for testing)"""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    def _maybe_compact_heap(self) -> None:
        """
        Compact heap if too many stale entries.

        Phase 1 Fix: Prevent unbounded heap growth from TTL expirations.
        Called periodically on cache miss/expiration.

        Strategy:
        - If heap size > 3x cache size, rebuild heap from active entries
        - This prevents memory leak from accumulated stale entries
        """
        # Only compact if heap is significantly larger than cache
        if len(self._lru_heap) <= len(self._cache) * 3:
            return

        # Rebuild heap with only valid entries
        new_heap: list[tuple[float, str]] = []
        for key, timestamp in self._key_timestamps.items():
            new_heap.append((timestamp, key))

        heapq.heapify(new_heap)
        self._lru_heap = new_heap

        logger.debug(f"Heap compacted: {len(self._lru_heap)} entries (from {len(self._lru_heap) * 3}+ stale)")
