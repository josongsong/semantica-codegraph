"""
Two-Level Cache for Retriever V3.

L1: In-Memory LRU Cache (fast, limited size)
L2: Redis Distributed Cache (slower, larger, shared across instances)

Provides fast, thread-safe caching with TTL support for:
- Full query results (query → fused results)
- Intent classifications (query → intent probabilities)
- RRF normalized scores (hits fingerprint → rrf scores)

Performance Impact:
- L1 cache hit: ~0.1ms (memory lookup)
- L2 cache hit: ~1-2ms (Redis lookup)
- Cache miss: ~20ms (full retrieval)
- Expected hit rate: 50-60% with L2 (vs 30-40% L1 only)
"""

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Single cache entry with TTL."""

    value: T
    expires_at: float  # Unix timestamp


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache with TTL support.

    Features:
    - LRU eviction policy (least recently used)
    - TTL-based expiration
    - Thread-safe operations
    - O(1) get/set operations

    Args:
        maxsize: Maximum number of entries
        ttl: Time to live in seconds (default: 300s = 5min)
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        """
        Initialize LRU cache.

        Args:
            maxsize: Maximum number of entries
            ttl: Time to live in seconds
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> T | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            # Check TTL
            if time.time() > entry.expires_at:
                # Expired - remove and return None
                del self._cache[key]
                self._misses += 1
                return None

            # Cache hit - move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: str, value: T) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            expires_at = time.time() + self.ttl

            # Update existing entry
            if key in self._cache:
                self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
                self._cache.move_to_end(key)
                return

            # Add new entry
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

            # Evict LRU if over maxsize
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)  # Remove oldest (FIFO)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "maxsize": self.maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "ttl": self.ttl,
            }


class RetrieverV3Cache:
    """
    3-tier cache for Retriever V3.

    Tier 1: Full query results (query → fused results)
    Tier 2: Intent classifications (query → intent probabilities)
    Tier 3: RRF scores (hits fingerprint → rrf scores)

    Cache keys are generated using SHA256 hashing for consistency.
    """

    def __init__(
        self,
        query_cache_size: int = 1000,
        intent_cache_size: int = 500,
        rrf_cache_size: int = 500,
        ttl: int = 300,
    ):
        """
        Initialize 3-tier cache.

        Args:
            query_cache_size: Max entries for full query results
            intent_cache_size: Max entries for intent classifications
            rrf_cache_size: Max entries for RRF scores
            ttl: Time to live in seconds (default: 5 minutes)
        """
        # Tier 1: Full query results (highest value)
        self.query_results = LRUCache[Any](maxsize=query_cache_size, ttl=ttl)

        # Tier 2: Intent classifications (reusable across strategies)
        self.intent_probs = LRUCache[Any](maxsize=intent_cache_size, ttl=ttl)

        # Tier 3: RRF scores (reusable for same hit sets)
        self.rrf_scores = LRUCache[Any](maxsize=rrf_cache_size, ttl=ttl)

    def make_query_key(
        self, repo_id: str, snapshot_id: str, query: str, strategy_config: dict[str, Any] | None = None
    ) -> str:
        """
        Generate cache key for full query results.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Search query
            strategy_config: Optional strategy configuration

        Returns:
            Cache key (hex string)
        """
        # Include repo_id + snapshot_id + query + strategy config
        key_data = f"{repo_id}:{snapshot_id}:{query}"
        if strategy_config:
            # Sort keys for consistency
            config_str = str(sorted(strategy_config.items()))
            key_data += f":{config_str}"

        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def make_intent_key(self, repo_id: str, snapshot_id: str, query: str) -> str:
        """
        Generate cache key for intent classification.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            query: Search query

        Returns:
            Cache key (hex string)
        """
        # Include repo_id + snapshot_id + query
        # Intent classification may vary per repo due to codebase-specific patterns
        key_data = f"{repo_id}:{snapshot_id}:{query}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def make_rrf_key(self, repo_id: str, snapshot_id: str, hits_by_strategy: dict[str, list[Any]]) -> str:
        """
        Generate cache key for RRF scores.

        Creates fingerprint of all chunk IDs and ranks across strategies.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/branch identifier
            hits_by_strategy: Dict of strategy → list of hits

        Returns:
            Cache key (hex string)
        """
        # Create fingerprint of repo + hits
        # Include repo_id/snapshot_id to prevent cross-repo collision
        fingerprint_parts = [f"repo:{repo_id}:{snapshot_id}"]

        for strategy in sorted(hits_by_strategy.keys()):
            hits = hits_by_strategy[strategy]
            # Use chunk_id + rank for each hit
            hit_ids = [f"{hit.chunk_id}:{hit.rank}" for hit in hits]
            fingerprint_parts.append(f"{strategy}:{','.join(hit_ids)}")

        fingerprint = "|".join(fingerprint_parts)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    def stats(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all cache tiers.

        Returns:
            Dictionary with stats for each tier
        """
        return {
            "query_results": self.query_results.stats(),
            "intent_probs": self.intent_probs.stats(),
            "rrf_scores": self.rrf_scores.stats(),
        }

    def clear_all(self) -> None:
        """Clear all cache tiers."""
        self.query_results.clear()
        self.intent_probs.clear()
        self.rrf_scores.clear()


class RedisL2Cache:
    """
    Redis-based L2 distributed cache.

    Provides shared caching across multiple instances with:
    - Automatic JSON serialization
    - TTL-based expiration
    - Namespace isolation per cache type
    - Graceful degradation on connection failure

    Usage:
        cache = RedisL2Cache(redis_client, ttl=300, namespace="retriever")
        await cache.get("key")
        await cache.set("key", {"data": "value"})
    """

    def __init__(
        self,
        redis_client,
        ttl: int = 300,
        namespace: str = "retriever_v3",
    ):
        """
        Initialize Redis L2 cache.

        Args:
            redis_client: Async Redis client (redis.asyncio.Redis)
            ttl: Time to live in seconds (default: 5 minutes)
            namespace: Key namespace prefix for isolation
        """
        self._redis = redis_client
        self._ttl = ttl
        self._namespace = namespace
        self._hits = 0
        self._misses = 0
        self._errors = 0

    def _make_key(self, key: str) -> str:
        """Create namespaced Redis key."""
        return f"{self._namespace}:{key}"

    async def get(self, key: str) -> Any | None:
        """
        Get value from Redis cache.

        Args:
            key: Cache key

        Returns:
            Deserialized value or None if not found/error
        """
        try:
            redis_key = self._make_key(key)
            value = await self._redis.get(redis_key)

            if value is None:
                self._misses += 1
                return None

            self._hits += 1
            return json.loads(value)

        except Exception:
            self._errors += 1
            return None

    async def set(self, key: str, value: Any) -> bool:
        """
        Set value in Redis cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)

        Returns:
            True if successful, False on error
        """
        try:
            redis_key = self._make_key(key)
            serialized = json.dumps(value, default=str)
            await self._redis.setex(redis_key, self._ttl, serialized)
            return True

        except Exception:
            self._errors += 1
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            redis_key = self._make_key(key)
            await self._redis.delete(redis_key)
            return True
        except Exception:
            return False

    async def clear_namespace(self) -> int:
        """
        Clear all keys in this namespace.

        Returns:
            Number of keys deleted
        """
        try:
            pattern = f"{self._namespace}:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)

            return len(keys)

        except Exception:
            return 0

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": hit_rate,
            "ttl": self._ttl,
            "namespace": self._namespace,
        }


class TwoLevelCache:
    """
    Two-level cache combining L1 (in-memory) and L2 (Redis).

    Read path: L1 → L2 → miss
    Write path: Write to both L1 and L2

    Features:
    - L1 provides sub-millisecond latency for hot data
    - L2 provides shared state across instances
    - Graceful degradation if Redis unavailable
    - Automatic L1 population on L2 hit

    Usage:
        cache = TwoLevelCache(
            l1_maxsize=1000,
            l2_redis=redis_client,
            ttl=300,
        )
        value = await cache.get("key")
        await cache.set("key", data)
    """

    def __init__(
        self,
        l1_maxsize: int = 1000,
        l2_redis=None,
        ttl: int = 300,
        namespace: str = "retriever_v3",
    ):
        """
        Initialize two-level cache.

        Args:
            l1_maxsize: Maximum L1 cache entries
            l2_redis: Optional async Redis client for L2
            ttl: Time to live in seconds
            namespace: Redis key namespace
        """
        # L1: In-memory LRU
        self._l1 = LRUCache[Any](maxsize=l1_maxsize, ttl=ttl)

        # L2: Redis (optional)
        self._l2: RedisL2Cache | None = None
        if l2_redis is not None:
            self._l2 = RedisL2Cache(l2_redis, ttl=ttl, namespace=namespace)

    async def get(self, key: str) -> Any | None:
        """
        Get value from cache (L1 → L2).

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        # Try L1 first (fast path)
        value = self._l1.get(key)
        if value is not None:
            return value

        # Try L2 if available
        if self._l2 is not None:
            value = await self._l2.get(key)
            if value is not None:
                # Populate L1 on L2 hit
                self._l1.set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any) -> None:
        """
        Set value in both caches.

        Args:
            key: Cache key
            value: Value to cache
        """
        # Always write to L1
        self._l1.set(key, value)

        # Write to L2 if available (fire and forget)
        if self._l2 is not None:
            await self._l2.set(key, value)

    def set_sync(self, key: str, value: Any) -> None:
        """
        Synchronous set for L1 only.

        Useful when async is not available.
        """
        self._l1.set(key, value)

    async def delete(self, key: str) -> None:
        """Delete from both caches."""
        # L1 doesn't have delete, just let it expire
        if self._l2 is not None:
            await self._l2.delete(key)

    async def clear(self) -> None:
        """Clear both caches."""
        self._l1.clear()
        if self._l2 is not None:
            await self._l2.clear_namespace()

    def stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        stats = {
            "l1": self._l1.stats(),
            "l2_enabled": self._l2 is not None,
        }

        if self._l2 is not None:
            stats["l2"] = self._l2.stats()

        return stats
