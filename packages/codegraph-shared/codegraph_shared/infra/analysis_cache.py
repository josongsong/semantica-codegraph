"""
Analysis Cache Layer (SOTA)

분석 결과 캐싱으로 중복 분석 방지.

Features:
- Redis 백엔드 (분산 환경 지원)
- In-memory 폴백 (Redis 없을 때)
- TTL 기반 자동 만료
- 스펙 해시 기반 캐시 키

Usage:
    cache = get_analysis_cache()

    # Check cache
    result = await cache.get(spec)
    if result:
        return result  # Cache hit

    # Execute and cache
    result = await execute(spec)
    await cache.set(spec, result)
"""

import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class AnalysisCacheBackend(ABC):
    """Abstract cache backend."""

    @abstractmethod
    async def get(self, key: str) -> dict | None:
        """Get cached value."""
        pass

    @abstractmethod
    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        """Set cached value with TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cached value."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached values."""
        pass


class InMemoryCache(AnalysisCacheBackend):
    """In-memory cache (single instance only)."""

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, tuple[dict, float]] = {}  # key -> (value, expires_at)
        self._max_size = max_size

    async def get(self, key: str) -> dict | None:
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        expires_at = time.time() + ttl_seconds
        self._cache[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    async def clear(self) -> None:
        self._cache.clear()


class RedisCache(AnalysisCacheBackend):
    """Redis-backed cache (distributed)."""

    def __init__(self, redis_url: str, prefix: str = "analysis_cache:"):
        self._redis_url = redis_url
        self._prefix = prefix
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self._redis_url)
        return self._client

    async def get(self, key: str) -> dict | None:
        try:
            client = await self._get_client()
            data = await client.get(f"{self._prefix}{key}")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning("redis_cache_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        try:
            client = await self._get_client()
            await client.setex(
                f"{self._prefix}{key}",
                ttl_seconds,
                json.dumps(value, default=str),
            )
        except Exception as e:
            logger.warning("redis_cache_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        try:
            client = await self._get_client()
            await client.delete(f"{self._prefix}{key}")
        except Exception as e:
            logger.warning("redis_cache_delete_failed", key=key, error=str(e))

    async def clear(self) -> None:
        try:
            client = await self._get_client()
            keys = await client.keys(f"{self._prefix}*")
            if keys:
                await client.delete(*keys)
        except Exception as e:
            logger.warning("redis_cache_clear_failed", error=str(e))


class AnalysisCache:
    """
    Analysis Cache (SOTA).

    Caches analysis results to avoid redundant computation.

    Cache key is based on:
    - spec hash (intent, template_id, scope, options)
    - snapshot hash (code state)

    TTL varies by analysis type:
    - cost_analysis: 1 hour
    - race_analysis: 1 hour
    - taint_analysis: 30 min (security-sensitive)
    - default: 15 min
    """

    # TTL by analysis type (seconds)
    TTL_CONFIG = {
        "cost_analysis": 3600,  # 1 hour
        "race_analysis": 3600,  # 1 hour
        "taint_analysis": 1800,  # 30 min
        "impact_analysis": 900,  # 15 min
        "default": 900,  # 15 min
    }

    def __init__(self, backend: AnalysisCacheBackend):
        self._backend = backend
        self._hits = 0
        self._misses = 0

    def _make_key(self, spec: dict, snapshot_hash: str | None = None) -> str:
        """Generate cache key from spec."""
        # Normalize spec for consistent hashing
        normalized = {
            "intent": spec.get("intent"),
            "template_id": spec.get("template_id"),
            "scope": spec.get("scope", {}),
            "options": spec.get("options", {}),
        }

        spec_json = json.dumps(normalized, sort_keys=True, default=str)
        spec_hash = hashlib.sha256(spec_json.encode()).hexdigest()[:16]

        if snapshot_hash:
            return f"{spec_hash}:{snapshot_hash[:16]}"
        return spec_hash

    def _get_ttl(self, spec: dict) -> int:
        """Get TTL based on analysis type."""
        template_id = spec.get("template_id", "")
        return self.TTL_CONFIG.get(template_id, self.TTL_CONFIG["default"])

    async def get(
        self,
        spec: dict,
        snapshot_hash: str | None = None,
    ) -> dict | None:
        """
        Get cached analysis result.

        Args:
            spec: Analysis spec
            snapshot_hash: Optional snapshot hash for stricter cache key

        Returns:
            Cached result or None
        """
        key = self._make_key(spec, snapshot_hash)
        result = await self._backend.get(key)

        if result:
            self._hits += 1
            logger.debug("cache_hit", key=key[:20])
        else:
            self._misses += 1
            logger.debug("cache_miss", key=key[:20])

        return result

    async def set(
        self,
        spec: dict,
        result: dict,
        snapshot_hash: str | None = None,
        ttl_override: int | None = None,
    ) -> None:
        """
        Cache analysis result.

        Args:
            spec: Analysis spec
            result: Analysis result to cache
            snapshot_hash: Optional snapshot hash
            ttl_override: Override default TTL
        """
        key = self._make_key(spec, snapshot_hash)
        ttl = ttl_override or self._get_ttl(spec)

        await self._backend.set(key, result, ttl)
        logger.debug("cache_set", key=key[:20], ttl=ttl)

    async def invalidate(
        self,
        spec: dict,
        snapshot_hash: str | None = None,
    ) -> None:
        """Invalidate cached result."""
        key = self._make_key(spec, snapshot_hash)
        await self._backend.delete(key)

    async def clear(self) -> None:
        """Clear all cached results."""
        await self._backend.clear()

    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 3),
        }


# Singleton
_analysis_cache: AnalysisCache | None = None


def get_analysis_cache() -> AnalysisCache:
    """
    Get AnalysisCache singleton.

    Auto-selects backend:
    - Redis if REDIS_URL configured
    - In-memory otherwise
    """
    global _analysis_cache

    if _analysis_cache is None:
        from codegraph_shared.infra.config.settings import Settings

        settings = Settings()
        redis_url = getattr(settings, "redis_url", None)

        if redis_url:
            backend = RedisCache(redis_url)
            logger.info("analysis_cache_init", backend="redis")
        else:
            backend = InMemoryCache(max_size=500)
            logger.info("analysis_cache_init", backend="in_memory")

        _analysis_cache = AnalysisCache(backend)

    return _analysis_cache
