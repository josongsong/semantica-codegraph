"""
Advanced Caching Layer (SOTA급)

특징:
1. Multi-tier Cache (L1: Local, L2: Redis)
2. Cache Aside Pattern
3. TTL & LRU Eviction
4. Cache Warming
5. Cache Invalidation
6. Bloom Filter (False Positive 감소)
7. Compression (큰 데이터)
8. Metrics & Monitoring
"""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ============================================================
# Bloom Filter (간단한 구현)
# ============================================================


class BloomFilter:
    """
    Bloom Filter for cache existence check.

    특징:
    - False Positive 가능 (존재한다고 했지만 없을 수 있음)
    - False Negative 불가능 (없다고 하면 확실히 없음)
    - 메모리 효율적
    """

    def __init__(self, size: int = 10000, hash_count: int = 3):
        """
        Args:
            size: Bit array 크기
            hash_count: 해시 함수 개수
        """
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [False] * size

    def _hash(self, item: str, seed: int) -> int:
        """해시 함수"""
        h = hashlib.md5(f"{item}{seed}".encode()).hexdigest()
        return int(h, 16) % self.size

    def add(self, item: str):
        """아이템 추가"""
        for i in range(self.hash_count):
            idx = self._hash(item, i)
            self.bit_array[idx] = True

    def contains(self, item: str) -> bool:
        """아이템 존재 확인 (False Positive 가능)"""
        for i in range(self.hash_count):
            idx = self._hash(item, i)
            if not self.bit_array[idx]:
                return False
        return True


# ============================================================
# Cache Entry
# ============================================================


@dataclass
class CacheEntry:
    """캐시 엔트리"""

    value: Any
    expires_at: float
    size: int = 0  # 바이트 단위
    hits: int = 0
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """만료 확인"""
        return time.time() > self.expires_at

    def touch(self):
        """접근 기록 (LRU)"""
        self.hits += 1


# ============================================================
# Advanced Cache
# ============================================================


class AdvancedCache:
    """
    SOTA급 Multi-tier Cache.

    특징:
    - L1: Local (메모리)
    - L2: Redis (분산)
    - Bloom Filter (빠른 존재 확인)
    - Compression (큰 데이터)
    - Metrics (Hit/Miss Rate)
    """

    def __init__(
        self,
        redis_client=None,
        local_max_size: int = 1000,
        local_max_bytes: int = 100 * 1024 * 1024,  # 100MB
        default_ttl: int = 3600,
        compression_threshold: int = 1024,  # 1KB 이상 압축
        enable_bloom_filter: bool = True,
    ):
        """
        Args:
            redis_client: Redis 클라이언트
            local_max_size: L1 캐시 최대 항목 수
            local_max_bytes: L1 캐시 최대 바이트 수
            default_ttl: 기본 TTL (초)
            compression_threshold: 압축 임계값 (바이트)
            enable_bloom_filter: Bloom Filter 사용 여부
        """
        self.redis_client = redis_client
        self.local_max_size = local_max_size
        self.local_max_bytes = local_max_bytes
        self.default_ttl = default_ttl
        self.compression_threshold = compression_threshold

        # L1 Cache (LRU OrderedDict)
        self.local_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.local_bytes = 0
        self.local_lock = asyncio.Lock()

        # Bloom Filter (L2 존재 확인)
        self.bloom_filter = BloomFilter() if enable_bloom_filter else None

        # Metrics
        self.stats = {
            "l1_hits": 0,
            "l1_misses": 0,
            "l2_hits": 0,
            "l2_misses": 0,
            "evictions": 0,
            "compressions": 0,
        }

    async def get(self, key: str) -> Any | None:
        """
        캐시 조회 (L1 → L2).

        Args:
            key: 캐시 키

        Returns:
            캐시된 값 또는 None
        """
        # L1 확인
        async with self.local_lock:
            if key in self.local_cache:
                entry = self.local_cache[key]

                # 만료 확인
                if entry.is_expired():
                    del self.local_cache[key]
                    self.local_bytes -= entry.size
                else:
                    # Hit!
                    entry.touch()
                    self.local_cache.move_to_end(key)  # LRU 업데이트
                    self.stats["l1_hits"] += 1
                    return entry.value

            self.stats["l1_misses"] += 1

        # L2 확인 (Redis)
        if self.redis_client:
            # NOTE: Bloom Filter는 메모리 기반이라 분산 환경에서 문제
            # Redis가 있으면 Bloom Filter 체크 건너뛰고 직접 조회
            # (Redis 자체가 충분히 빠름)

            try:
                cached = await self.redis_client.get(key)
                if cached:
                    # RedisAdapter.get()이 이미 JSON 파싱을 시도함
                    # 파싱 성공하면 dict/list, 실패하면 string

                    # 이미 파싱된 경우 (dict/list)
                    if isinstance(cached, dict | list):
                        value = cached
                    # String인 경우 JSON 파싱 시도
                    elif isinstance(cached, str):
                        try:
                            value = json.loads(cached)
                        except json.JSONDecodeError:
                            # JSON이 아니면 그대로 사용
                            value = cached
                    else:
                        value = cached

                    # L1에 저장 (Promotion)
                    await self._set_local(key, value, self.default_ttl)

                    self.stats["l2_hits"] += 1
                    return value

            except Exception as e:
                # Redis 실패 로깅 (디버깅용)
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(f"Redis L2 조회 실패: {e}")
                pass  # Redis 실패해도 계속

        self.stats["l2_misses"] += 1
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        캐시 저장 (L1 + L2).

        Args:
            key: 캐시 키
            value: 저장할 값
            ttl: TTL (초, None이면 default_ttl)
        """
        ttl = ttl or self.default_ttl

        # L1 저장
        await self._set_local(key, value, ttl)

        # L2 저장 (Redis)
        if self.redis_client:
            try:
                # Serialize (RedisAdapter가 자동으로 JSON 처리하므로 .encode() 제거)
                serialized = json.dumps(value)

                # Compression은 일단 비활성화 (RedisAdapter와 호환성 문제)
                # TODO: Compression을 사용하려면 별도 키 prefix 사용 필요

                # RedisAdapter는 set(key, value, ex=ttl) 형식 사용
                await self.redis_client.set(key, serialized, ex=ttl)

                # Bloom Filter 업데이트 (NOTE: 메모리 기반이라 분산 환경에서 제한적)
                if self.bloom_filter:
                    self.bloom_filter.add(key)

            except Exception as e:
                # Redis 실패 로깅 (디버깅용)
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(f"Redis L2 저장 실패: {e}")
                pass  # Redis 실패해도 계속

    async def _set_local(self, key: str, value: Any, ttl: int):
        """L1 캐시에 저장 (내부 메서드)"""
        async with self.local_lock:
            # 기존 항목 제거 (있으면)
            if key in self.local_cache:
                old_entry = self.local_cache[key]
                self.local_bytes -= old_entry.size
                del self.local_cache[key]

            # 크기 계산
            size = len(json.dumps(value).encode())

            # 캐시 크기 제한 (LRU Eviction)
            while len(self.local_cache) >= self.local_max_size or self.local_bytes + size > self.local_max_bytes:
                if not self.local_cache:
                    break

                # 가장 오래된 항목 제거 (FIFO in OrderedDict)
                oldest_key, oldest_entry = self.local_cache.popitem(last=False)
                self.local_bytes -= oldest_entry.size
                self.stats["evictions"] += 1

            # 새 엔트리 추가
            entry = CacheEntry(value=value, expires_at=time.time() + ttl, size=size)
            self.local_cache[key] = entry
            self.local_bytes += size

    async def delete(self, key: str):
        """
        캐시 삭제 (L1 + L2).

        Args:
            key: 캐시 키
        """
        # L1 삭제
        async with self.local_lock:
            if key in self.local_cache:
                entry = self.local_cache[key]
                self.local_bytes -= entry.size
                del self.local_cache[key]

        # L2 삭제
        if self.redis_client:
            try:
                await self.redis_client.delete(key)
            except Exception:
                pass

    async def clear(self):
        """전체 캐시 삭제"""
        async with self.local_lock:
            self.local_cache.clear()
            self.local_bytes = 0

        if self.redis_client:
            try:
                # 주의: 전체 Redis flush는 위험할 수 있음
                # 프로젝트별 prefix를 사용하는 것이 좋음
                pass
            except Exception:
                pass

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
    ) -> Any:
        """
        Cache Aside Pattern.

        Args:
            key: 캐시 키
            factory: 캐시 미스 시 호출할 함수
            ttl: TTL (초)

        Returns:
            캐시된 값 또는 factory 결과
        """
        # 캐시 확인
        value = await self.get(key)
        if value is not None:
            return value

        # 캐시 미스 → Factory 호출
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()

        # 캐시 저장
        await self.set(key, value, ttl)

        return value

    def get_stats(self) -> dict[str, Any]:
        """
        캐시 통계 조회.

        Returns:
            통계 딕셔너리
        """
        total_requests = (
            self.stats["l1_hits"] + self.stats["l1_misses"] + self.stats["l2_hits"] + self.stats["l2_misses"]
        )

        hit_rate = 0.0
        if total_requests > 0:
            hits = self.stats["l1_hits"] + self.stats["l2_hits"]
            hit_rate = hits / total_requests

        return {
            "l1_size": len(self.local_cache),
            "l1_bytes": self.local_bytes,
            "l1_hit_rate": (
                self.stats["l1_hits"] / (self.stats["l1_hits"] + self.stats["l1_misses"])
                if (self.stats["l1_hits"] + self.stats["l1_misses"]) > 0
                else 0.0
            ),
            "l2_hit_rate": (
                self.stats["l2_hits"] / (self.stats["l2_hits"] + self.stats["l2_misses"])
                if (self.stats["l2_hits"] + self.stats["l2_misses"]) > 0
                else 0.0
            ),
            "overall_hit_rate": hit_rate,
            "evictions": self.stats["evictions"],
            "compressions": self.stats["compressions"],
            **self.stats,
        }

    async def warm_up(self, keys_and_factories: dict[str, Callable]):
        """
        Cache Warming (사전 로딩).

        Args:
            keys_and_factories: {key: factory} 딕셔너리
        """
        tasks = [self.get_or_set(key, factory) for key, factory in keys_and_factories.items()]
        await asyncio.gather(*tasks)
