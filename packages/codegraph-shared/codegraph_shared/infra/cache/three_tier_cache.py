"""
Three-Tier Cache System

L1: In-Memory LRU (fastest, ~0.1ms)
L2: Redis (fast, ~1-2ms, shared)
L3: Database (slow, ~10-50ms, persistent)

Read path: L1 → L2 → L3
Write path: Write to all tiers (or L3 only with lazy population)
"""

import hashlib
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Generic, Protocol, TypeVar

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """캐시 항목 (값 + 만료시간)"""

    value: T
    expires_at: float  # Unix timestamp
    size_bytes: int = 0  # 메모리 사용량 추적


class CacheStats:
    """캐시 통계"""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.size = 0
        self.total_size_bytes = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "size": self.size,
            "total_size_bytes": self.total_size_bytes,
            "hit_rate": self.hit_rate,
        }


class LRUCacheWithStats(Generic[T]):
    """
    Thread-safe LRU cache with TTL and statistics.

    Features:
    - LRU eviction
    - TTL expiration
    - Size tracking
    - Hit/miss metrics
    - Thread-safe
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 300, track_size: bool = True):
        """
        Args:
            maxsize: 최대 항목 수
            ttl: TTL (초)
            track_size: 메모리 사용량 추적 여부
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.track_size = track_size
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = Lock()
        self._stats = CacheStats()

    def get(self, key: str) -> T | None:
        """캐시에서 조회"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            # TTL 체크
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._stats.misses += 1
                self._stats.size = len(self._cache)
                self._stats.total_size_bytes -= entry.size_bytes
                return None

            # Cache hit
            self._cache.move_to_end(key)
            self._stats.hits += 1
            return entry.value

    def set(self, key: str, value: T) -> None:
        """캐시에 저장"""
        with self._lock:
            # 크기 계산
            size_bytes = 0
            if self.track_size:
                try:
                    size_bytes = len(pickle.dumps(value))
                except Exception:
                    size_bytes = 1024  # 기본값

            expires_at = time.time() + self.ttl
            entry = CacheEntry(value=value, expires_at=expires_at, size_bytes=size_bytes)

            # 기존 항목 제거 시 크기 조정
            if key in self._cache:
                old_entry = self._cache[key]
                self._stats.total_size_bytes -= old_entry.size_bytes

            # LRU eviction
            while len(self._cache) >= self.maxsize and self.maxsize > 0:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._stats.evictions += 1
                self._stats.total_size_bytes -= evicted_entry.size_bytes

            self._cache[key] = entry
            self._stats.size = len(self._cache)
            self._stats.total_size_bytes += size_bytes

    def clear(self) -> None:
        """캐시 전체 삭제"""
        with self._lock:
            self._cache.clear()
            self._stats.size = 0
            self._stats.total_size_bytes = 0

    def stats(self) -> dict:
        """통계 조회"""
        with self._lock:
            return {
                **self._stats.to_dict(),
                "maxsize": self.maxsize,
                "ttl": self.ttl,
            }


class L2RedisCache(Generic[T]):
    """Redis 기반 L2 캐시 (분산 공유)"""

    def __init__(self, redis_client: Any, ttl: int = 300, namespace: str = "cache"):
        """
        Args:
            redis_client: async Redis client
            ttl: TTL (초)
            namespace: 키 네임스페이스
        """
        self.redis = redis_client
        self.ttl = ttl
        self.namespace = namespace

    def _make_key(self, key: str) -> str:
        """Redis 키 생성"""
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> T | None:
        """Redis에서 조회"""
        try:
            redis_key = self._make_key(key)
            data = await self.redis.get(redis_key)

            if data is None:
                return None

            # Deserialize
            result: T = pickle.loads(data)
            return result
        except Exception as e:
            logger.warning("redis_cache_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: T) -> None:
        """Redis에 저장"""
        try:
            redis_key = self._make_key(key)
            data = pickle.dumps(value)
            # RedisAdapter uses expire_seconds, raw Redis uses ex
            await self.redis.set(redis_key, data, expire_seconds=self.ttl)
        except TypeError:
            # Fallback for raw Redis client which uses ex= parameter
            try:
                await self.redis.set(redis_key, data, ex=self.ttl)
            except Exception as e:
                logger.warning("redis_cache_set_failed", key=key, error=str(e))
        except Exception as e:
            logger.warning("redis_cache_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """Redis에서 삭제"""
        try:
            redis_key = self._make_key(key)
            await self.redis.delete(redis_key)
        except Exception as e:
            logger.warning("redis_cache_delete_failed", key=key, error=str(e))

    async def clear_namespace(self) -> int:
        """네임스페이스 전체 삭제"""
        try:
            pattern = f"{self.namespace}:*"
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                return len(keys)
            return 0
        except Exception as e:
            logger.warning("redis_cache_clear_failed", error=str(e))
            return 0


class L3DatabaseLoader(Protocol[T]):
    """L3 데이터베이스 로더 프로토콜"""

    async def load(self, key: str) -> T | None:
        """데이터베이스에서 로드"""
        ...

    async def save(self, key: str, value: T) -> None:
        """데이터베이스에 저장"""
        ...

    async def delete(self, key: str) -> None:
        """데이터베이스에서 삭제"""
        ...


class ThreeTierCache(Generic[T]):
    """
    3-tier 캐시 시스템.

    Read path: L1 (memory) → L2 (Redis) → L3 (DB)
    Write path: L3에 저장 → L1/L2는 lazy population (read 시)

    Features:
    - 계층적 조회로 성능 최적화
    - Redis 장애 시 graceful degradation
    - 캐시 통계 수집
    - 백그라운드 워밍

    Usage:
        cache = ThreeTierCache(
            l1_maxsize=1000,
            l2_redis=redis_client,
            l3_loader=ChunkDBLoader(postgres),
            ttl=300,
            namespace="chunks"
        )

        # Read (L1 → L2 → L3)
        chunk = await cache.get(chunk_id)

        # Write (L3 only, L1/L2는 lazy)
        await cache.set(chunk_id, chunk)
    """

    def __init__(
        self,
        l1_maxsize: int = 1000,
        l2_redis: Any | None = None,
        l3_loader: L3DatabaseLoader[T] | None = None,
        ttl: int = 300,
        namespace: str = "cache",
        enable_warming: bool = False,
    ):
        """
        Args:
            l1_maxsize: L1 최대 크기
            l2_redis: Redis 클라이언트 (optional)
            l3_loader: DB 로더 (optional)
            ttl: TTL (초)
            namespace: 네임스페이스
            enable_warming: 백그라운드 워밍 활성화
        """
        self.namespace = namespace
        self.ttl = ttl
        self.enable_warming = enable_warming

        # L1: In-memory LRU
        self._l1 = LRUCacheWithStats[T](maxsize=l1_maxsize, ttl=ttl)

        # L2: Redis (optional)
        self._l2: L2RedisCache[T] | None = None
        if l2_redis is not None:
            self._l2 = L2RedisCache[T](l2_redis, ttl=ttl, namespace=namespace)

        # L3: Database (optional)
        self._l3 = l3_loader

        # Stats
        self._l2_hits = 0
        self._l2_misses = 0
        self._l3_hits = 0
        self._l3_misses = 0

    @staticmethod
    def _calc_hit_rate(hits: int, misses: int) -> float:
        """Calculate hit rate percentage."""
        total = hits + misses
        return (hits / total * 100) if total > 0 else 0.0

    async def get(self, key: str) -> T | None:  # type: ignore[misc]
        """
        계층적 조회: L1 → L2 → L3

        Args:
            key: 캐시 키

        Returns:
            값 또는 None
        """
        time.perf_counter()

        # L1: In-memory (fastest)
        value = self._l1.get(key)
        if value is not None:
            # L1 hit
            logger.debug("cache_l1_hit", namespace=self.namespace)
            return value  # type: ignore[return-value]

        # L2: Redis (fast)
        if self._l2 is not None:
            value = await self._l2.get(key)
            if value is not None:
                self._l2_hits += 1
                # Populate L1
                self._l1.set(key, value)
                logger.debug("cache_l2_hit", namespace=self.namespace)
                return value  # type: ignore[return-value]
            self._l2_misses += 1

        # L3: Database (slow)
        if self._l3 is not None:
            value = await self._l3.load(key)
            if value is not None:
                self._l3_hits += 1
                # Populate L1 and L2
                self._l1.set(key, value)
                if self._l2 is not None:
                    await self._l2.set(key, value)
                logger.debug("cache_l3_hit", namespace=self.namespace)
                return value  # type: ignore[return-value]
            self._l3_misses += 1

        logger.debug("cache_miss", namespace=self.namespace)
        return None

    async def set(self, key: str, value: T, write_through: bool = True) -> None:
        """
        캐시에 저장.

        Args:
            key: 캐시 키
            value: 값
            write_through: True면 L3까지 저장, False면 L1/L2만
        """
        # L1 항상 저장
        self._l1.set(key, value)

        # L2 저장 (optional)
        if self._l2 is not None:
            await self._l2.set(key, value)

        # L3 write-through (optional)
        if write_through and self._l3 is not None:
            await self._l3.save(key, value)

    async def delete(self, key: str) -> None:
        """모든 tier에서 삭제"""
        # L1
        with self._l1._lock:
            if key in self._l1._cache:
                del self._l1._cache[key]
                self._l1._stats.size = len(self._l1._cache)

        # L2
        if self._l2 is not None:
            await self._l2.delete(key)

        # L3
        if self._l3 is not None:
            await self._l3.delete(key)

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        패턴 매칭으로 무효화.

        Args:
            pattern: 키 패턴 (예: "repo:my-repo:*")

        Returns:
            무효화된 항목 수
        """
        count = 0

        # L1: Simple prefix matching
        with self._l1._lock:
            keys_to_delete = [k for k in self._l1._cache.keys() if k.startswith(pattern.replace("*", ""))]
            for k in keys_to_delete:
                del self._l1._cache[k]
            count += len(keys_to_delete)
            self._l1._stats.size = len(self._l1._cache)

        # L2: Redis pattern matching
        if self._l2 is not None:
            redis_pattern = f"{self._l2.namespace}:{pattern}"
            try:
                keys = await self._l2.redis.keys(redis_pattern)
                if keys:
                    await self._l2.redis.delete(*keys)
                    count += len(keys)
            except Exception as e:
                logger.warning("redis_invalidate_pattern_failed", pattern=pattern, error=str(e))

        return count

    def stats(self) -> dict:
        """전체 통계 조회"""
        l1_stats = self._l1.stats()

        return {
            "l1": l1_stats,
            "l2": {
                "hits": self._l2_hits,
                "misses": self._l2_misses,
                "hit_rate": self._calc_hit_rate(self._l2_hits, self._l2_misses),
            },
            "l3": {
                "hits": self._l3_hits,
                "misses": self._l3_misses,
                "hit_rate": self._calc_hit_rate(self._l3_hits, self._l3_misses),
            },
            "namespace": self.namespace,
        }

    async def warm_keys(self, keys: list[str]) -> int:
        """
        미리 지정된 키들을 L1/L2에 로드 (warming).

        Args:
            keys: 워밍할 키 목록

        Returns:
            성공한 개수
        """
        if not self._l3:
            return 0

        warmed = 0
        for key in keys:
            # L1에 이미 있으면 skip
            if self._l1.get(key) is not None:
                continue

            # L3에서 로드
            value = await self._l3.load(key)
            if value is not None:
                # L1/L2에 저장
                self._l1.set(key, value)
                if self._l2 is not None:
                    await self._l2.set(key, value)
                warmed += 1

        logger.info("cache_warming_completed", namespace=self.namespace, keys_total=len(keys), keys_warmed=warmed)
        return warmed


def make_cache_key(*parts: str) -> str:
    """
    캐시 키 생성 (해싱).

    Args:
        *parts: 키 구성 요소들

    Returns:
        SHA256 해시 키
    """
    combined = ":".join(str(p) for p in parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]
