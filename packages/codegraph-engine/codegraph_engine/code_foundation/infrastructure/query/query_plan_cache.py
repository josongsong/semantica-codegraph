"""
QueryPlan Execution Result Cache (SOTA)

RFC-052: MCP Service Layer Architecture
Cache QueryPlan execution results for performance.

Design Principles:
- Cache key: (snapshot_id, plan_hash, budget_profile)
- Evidence reuse: Same evidence_ref for cached results
- TTL: Follows evidence TTL
- LRU eviction: Bounded memory usage

Cache Hit Conditions:
1. Same snapshot_id (version consistency)
2. Same plan_hash (logical query)
3. Same budget (result size may differ)

Cache Miss Conditions:
- Snapshot changed
- Evidence expired
- Cache eviction (LRU)
"""

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.query_plan import QueryPlan

logger = get_logger(__name__)


@dataclass
class CachedResult:
    """
    Cached QueryPlan execution result.

    Includes:
    - Execution result
    - Evidence ID (for reuse)
    - Cache metadata
    """

    result: Any
    evidence_id: str | None
    cached_at: float  # timestamp
    hit_count: int = 0

    def is_fresh(self, ttl_seconds: int) -> bool:
        """Check if cache entry is fresh"""
        age = time.time() - self.cached_at
        return age < ttl_seconds


class QueryPlanCache:
    """
    LRU cache for QueryPlan execution results.

    Thread-safe (Python GIL for dict operations).
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            max_size: Maximum cache entries (LRU eviction)
            ttl_seconds: TTL for cache entries (default: 1 hour)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CachedResult] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _make_key(self, snapshot_id: str, plan: QueryPlan) -> str:
        """
        Create cache key.

        Args:
            snapshot_id: Snapshot ID
            plan: QueryPlan

        Returns:
            Cache key (stable)
        """
        # Include budget in key (different budgets → different results)
        budget_hash = hash(plan.budget)
        return f"{snapshot_id}:{plan.compute_hash()}:{budget_hash}"

    def get(self, snapshot_id: str, plan: QueryPlan) -> CachedResult | None:
        """
        Get cached result.

        Args:
            snapshot_id: Snapshot ID
            plan: QueryPlan

        Returns:
            CachedResult or None if cache miss
        """
        key = self._make_key(snapshot_id, plan)

        if key not in self._cache:
            self._misses += 1
            logger.debug("cache_miss", key=key)
            return None

        cached = self._cache[key]

        # Check freshness
        if not cached.is_fresh(self.ttl_seconds):
            # Expired - remove
            del self._cache[key]
            self._misses += 1
            logger.debug("cache_expired", key=key)
            return None

        # Move to end (LRU)
        self._cache.move_to_end(key)
        cached.hit_count += 1
        self._hits += 1

        logger.debug(
            "cache_hit",
            key=key,
            hit_count=cached.hit_count,
            age_seconds=time.time() - cached.cached_at,
        )

        return cached

    def put(
        self,
        snapshot_id: str,
        plan: QueryPlan,
        result: Any,
        evidence_id: str | None = None,
    ) -> None:
        """
        Put result in cache.

        Args:
            snapshot_id: Snapshot ID
            plan: QueryPlan
            result: Execution result
            evidence_id: Evidence ID (for reuse)
        """
        key = self._make_key(snapshot_id, plan)

        # LRU eviction if full
        if len(self._cache) >= self.max_size:
            # Remove oldest
            oldest_key, oldest_value = self._cache.popitem(last=False)
            logger.debug(
                "cache_evicted",
                key=oldest_key,
                hit_count=oldest_value.hit_count,
            )

        # Add to cache
        self._cache[key] = CachedResult(
            result=result,
            evidence_id=evidence_id,
            cached_at=time.time(),
        )

        logger.debug("cache_put", key=key)

    def invalidate_snapshot(self, snapshot_id: str) -> int:
        """
        Invalidate all entries for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Number of entries invalidated
        """
        keys_to_remove = [key for key in self._cache.keys() if key.startswith(f"{snapshot_id}:")]

        for key in keys_to_remove:
            del self._cache[key]

        logger.info("cache_invalidated", snapshot_id=snapshot_id, count=len(keys_to_remove))
        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("cache_cleared", count=count)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "ttl_seconds": self.ttl_seconds,
        }
