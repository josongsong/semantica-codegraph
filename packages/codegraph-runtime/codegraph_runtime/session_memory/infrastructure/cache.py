"""
Memory Caching Layer

L1 (in-memory LRU) + L2 (Redis) 캐싱
"""

import json
from collections import OrderedDict
from datetime import datetime
from typing import Any, Generic, TypeVar

from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

from .config import get_config

logger = get_logger(__name__)

T = TypeVar("T")


class LRUCache(Generic[T]):
    """
    LRU (Least Recently Used) 캐시

    O(1) get/put
    """

    def __init__(self, capacity: int):
        """
        Initialize LRU cache

        Args:
            capacity: 최대 캐시 크기
        """
        self.cache: OrderedDict[str, T] = OrderedDict()
        self.capacity = capacity
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> T | None:
        """
        캐시에서 값 가져오기

        Args:
            key: 키

        Returns:
            Value or None
        """
        if key not in self.cache:
            self._misses += 1
            record_counter("memory_cache_l1_miss_total")
            return None

        self._hits += 1
        record_counter("memory_cache_l1_hit_total")

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: str, value: T) -> None:
        """
        캐시에 값 저장

        Args:
            key: 키
            value: 값
        """
        if key in self.cache:
            # Update existing
            self.cache.move_to_end(key)
        else:
            # Add new
            if len(self.cache) >= self.capacity:
                # Evict LRU
                evicted_key = next(iter(self.cache))
                self.cache.pop(evicted_key)
                record_counter("memory_cache_l1_eviction_total")

        self.cache[key] = value

    def invalidate(self, key: str) -> bool:
        """
        캐시 무효화

        Args:
            key: 키

        Returns:
            True if key existed
        """
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def clear(self) -> None:
        """전체 캐시 초기화"""
        self.cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        """캐시 적중률"""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """현재 캐시 크기"""
        return len(self.cache)


class RedisCache:
    """
    Redis 기반 L2 캐시 (선택적)

    Redis가 없으면 graceful degradation
    """

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 3600,
        prefix: str = "memory:",
    ):
        """
        Initialize Redis cache

        Args:
            redis_url: Redis 연결 URL
            ttl_seconds: TTL (초)
            prefix: 키 prefix
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self._client: Any = None
        self._enabled = False

    async def connect(self) -> bool:
        """
        Redis 연결

        Returns:
            True if connected
        """
        try:
            import redis.asyncio as aioredis

            self._client = await aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )

            # Ping test
            await self._client.ping()
            self._enabled = True
            logger.info("redis_cache_connected", url=self.redis_url)
            return True

        except Exception as e:
            logger.warning("redis_cache_connection_failed", error=str(e))
            self._enabled = False
            return False

    async def get(self, key: str) -> Any | None:
        """
        Redis에서 값 가져오기

        Args:
            key: 키

        Returns:
            Deserialized value or None
        """
        if not self._enabled or self._client is None:
            return None

        try:
            full_key = f"{self.prefix}{key}"
            value = await self._client.get(full_key)

            if value is None:
                record_counter("memory_cache_l2_miss_total")
                return None

            record_counter("memory_cache_l2_hit_total")
            return json.loads(value)

        except Exception as e:
            logger.error("redis_get_failed", key=key, error=str(e))
            return None

    async def put(self, key: str, value: Any) -> bool:
        """
        Redis에 값 저장

        Args:
            key: 키
            value: 값 (JSON serializable)

        Returns:
            True if successful
        """
        if not self._enabled or self._client is None:
            return False

        try:
            full_key = f"{self.prefix}{key}"
            serialized = json.dumps(value, default=str)

            await self._client.set(
                full_key,
                serialized,
                ex=self.ttl_seconds,
            )

            return True

        except Exception as e:
            logger.error("redis_put_failed", key=key, error=str(e))
            return False

    async def invalidate(self, key: str) -> bool:
        """
        캐시 무효화

        Args:
            key: 키

        Returns:
            True if key existed
        """
        if not self._enabled or self._client is None:
            return False

        try:
            full_key = f"{self.prefix}{key}"
            deleted = await self._client.delete(full_key)
            return deleted > 0

        except Exception as e:
            logger.error("redis_invalidate_failed", key=key, error=str(e))
            return False

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._client is not None:
            await self._client.close()
            self._enabled = False


class TieredCache(Generic[T]):
    """
    L1 (LRU) + L2 (Redis) 2-tier 캐시

    Read path: L1 -> L2 -> Source
    Write path: L1 <- L2 <- Source
    """

    def __init__(
        self,
        l1_cache: LRUCache[T],
        l2_cache: RedisCache | None = None,
    ):
        """
        Initialize tiered cache

        Args:
            l1_cache: L1 캐시 (LRU)
            l2_cache: L2 캐시 (Redis, 선택적)
        """
        self.l1 = l1_cache
        self.l2 = l2_cache
        self._l2_enabled = l2_cache is not None

    async def get(self, key: str) -> T | None:
        """
        캐시에서 값 가져오기 (L1 -> L2 순서)

        Args:
            key: 키

        Returns:
            Value or None
        """
        start = datetime.now()

        # L1 try
        value = self.l1.get(key)
        if value is not None:
            record_histogram(
                "memory_cache_get_latency_ms", (datetime.now() - start).total_seconds() * 1000, labels={"tier": "l1"}
            )
            return value

        # L2 try
        if self._l2_enabled and self.l2 is not None:
            value = await self.l2.get(key)
            if value is not None:
                # Promote to L1
                self.l1.put(key, value)
                record_histogram(
                    "memory_cache_get_latency_ms",
                    (datetime.now() - start).total_seconds() * 1000,
                    labels={"tier": "l2"},
                )
                return value

        # Miss
        record_counter("memory_cache_miss_total")
        return None

    async def put(self, key: str, value: T) -> None:
        """
        캐시에 값 저장 (L1 + L2 동시)

        Args:
            key: 키
            value: 값
        """
        # L1 write
        self.l1.put(key, value)

        # L2 write (async, best-effort)
        if self._l2_enabled and self.l2 is not None:
            await self.l2.put(key, value)

    async def invalidate(self, key: str) -> None:
        """
        캐시 무효화 (L1 + L2 동시)

        Args:
            key: 키
        """
        self.l1.invalidate(key)

        if self._l2_enabled and self.l2 is not None:
            await self.l2.invalidate(key)

    def clear_l1(self) -> None:
        """L1 캐시만 초기화"""
        self.l1.clear()

    @property
    def l1_hit_rate(self) -> float:
        """L1 적중률"""
        return self.l1.hit_rate

    @property
    def l1_size(self) -> int:
        """L1 크기"""
        return self.l1.size


class MemoryCacheManager:
    """
    Memory System 전용 캐시 매니저

    프로젝트별, 타입별 캐싱 전략
    """

    def __init__(self, config: Any | None = None):
        """
        Initialize cache manager

        Args:
            config: CacheConfig
        """
        self.config = config or get_config().cache

        # L1 caches (타입별)
        self.project_cache: LRUCache[Any] | None = None
        self.bug_pattern_cache: LRUCache[Any] | None = None

        # L2 cache (shared)
        self.redis_cache: RedisCache | None = None

        # Tiered caches
        self.project_tiered: TieredCache[Any] | None = None
        self.bug_pattern_tiered: TieredCache[Any] | None = None

    async def initialize(self) -> None:
        """캐시 초기화"""
        if not self.config.enable_l1_cache:
            logger.info("cache_disabled")
            return

        # L1 caches
        if self.config.cache_project_knowledge:
            self.project_cache = LRUCache(capacity=self.config.l1_cache_size)

        if self.config.cache_bug_patterns:
            self.bug_pattern_cache = LRUCache(capacity=self.config.l1_cache_size)

        # L2 cache
        if self.config.enable_l2_cache:
            self.redis_cache = RedisCache(
                redis_url=self.config.redis_url,
                ttl_seconds=self.config.redis_ttl_seconds,
            )
            await self.redis_cache.connect()

        # Tiered caches
        if self.project_cache is not None:
            self.project_tiered = TieredCache(self.project_cache, self.redis_cache)

        if self.bug_pattern_cache is not None:
            self.bug_pattern_tiered = TieredCache(self.bug_pattern_cache, self.redis_cache)

        logger.info(
            "cache_initialized",
            l1=self.config.enable_l1_cache,
            l2=self.config.enable_l2_cache,
        )

    async def get_project_knowledge(self, project_id: str) -> Any | None:
        """
        프로젝트 지식 캐시 조회

        Args:
            project_id: 프로젝트 ID

        Returns:
            ProjectKnowledge or None
        """
        if self.project_tiered is None:
            return None

        return await self.project_tiered.get(f"project:{project_id}")

    async def put_project_knowledge(self, project_id: str, knowledge: Any) -> None:
        """
        프로젝트 지식 캐시 저장

        Args:
            project_id: 프로젝트 ID
            knowledge: ProjectKnowledge
        """
        if self.project_tiered is None:
            return

        await self.project_tiered.put(f"project:{project_id}", knowledge)

    async def get_bug_patterns(self, error_type: str) -> Any | None:
        """
        버그 패턴 캐시 조회

        Args:
            error_type: 에러 타입

        Returns:
            List[BugPattern] or None
        """
        if self.bug_pattern_tiered is None:
            return None

        return await self.bug_pattern_tiered.get(f"bug_pattern:{error_type}")

    async def put_bug_patterns(self, error_type: str, patterns: Any) -> None:
        """
        버그 패턴 캐시 저장

        Args:
            error_type: 에러 타입
            patterns: List[BugPattern]
        """
        if self.bug_pattern_tiered is None:
            return

        await self.bug_pattern_tiered.put(f"bug_pattern:{error_type}", patterns)

    async def invalidate_project(self, project_id: str) -> None:
        """프로젝트 캐시 무효화"""
        if self.project_tiered is not None:
            await self.project_tiered.invalidate(f"project:{project_id}")

    async def invalidate_bug_pattern(self, error_type: str) -> None:
        """버그 패턴 캐시 무효화"""
        if self.bug_pattern_tiered is not None:
            await self.bug_pattern_tiered.invalidate(f"bug_pattern:{error_type}")

    async def close(self) -> None:
        """캐시 종료"""
        if self.redis_cache is not None:
            await self.redis_cache.close()

    def get_statistics(self) -> dict[str, Any]:
        """캐시 통계"""
        stats: dict[str, Any] = {
            "l1_enabled": self.config.enable_l1_cache,
            "l2_enabled": self.config.enable_l2_cache,
        }

        if self.project_cache is not None:
            stats["project_cache"] = {
                "hit_rate": self.project_cache.hit_rate,
                "size": self.project_cache.size,
            }

        if self.bug_pattern_cache is not None:
            stats["bug_pattern_cache"] = {
                "hit_rate": self.bug_pattern_cache.hit_rate,
                "size": self.bug_pattern_cache.size,
            }

        return stats
