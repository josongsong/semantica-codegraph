"""
Rebuild Cache

IncrementalBuilder 결과 캐싱으로 2-3배 성능 향상
"""

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument

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
    IncrementalBuilder 결과 캐싱

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
        self._access_order: dict[str, float] = {}  # For LRU
        self._lock = threading.Lock()  # Thread safety

        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

        logger.info(f"RebuildCache initialized: ttl={ttl_seconds}s, max={max_entries}")

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
                del self._access_order[key]
                logger.debug(f"Cache EXPIRED: {key[:16]}, age={entry.age_seconds():.1f}s")
                return None

            # Hit
            self.hits += 1
            self._access_order[key] = time.time()
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
            # Evict if needed (LRU)
            if len(self._cache) >= self.max_entries:
                self._evict_lru()

            # Store
            entry = CacheEntry(
                updated_graph=updated_graph,
                rebuild_plan=rebuild_plan,
                rebuild_stats=rebuild_stats,
                cached_at=time.time(),
                ttl_seconds=self.ttl_seconds,
            )

            self._cache[key] = entry
            self._access_order[key] = time.time()

            logger.debug(f"Cache SET: {key[:16]}")

    def _evict_lru(self) -> None:
        """LRU eviction"""
        if not self._access_order:
            return

        # Find LRU key
        lru_key = min(self._access_order.items(), key=lambda x: x[1])[0]

        # Evict
        del self._cache[lru_key]
        del self._access_order[lru_key]
        self.evictions += 1

        logger.debug(f"Cache EVICT (LRU): {lru_key[:16]}")

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
                    del self._access_order[key]
                    logger.info(f"Cache INVALIDATE: {key[:16]}")
            else:
                # Clear all
                count = len(self._cache)
                self._cache.clear()
                self._access_order.clear()
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
