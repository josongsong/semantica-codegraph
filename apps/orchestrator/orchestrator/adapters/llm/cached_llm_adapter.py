"""
Cached LLM Provider Adapter

LLM 응답 캐싱 (Redis).

특징:
1. Redis 캐싱 (TTL: 1시간)
2. Cache key: hash(prompt + model)
3. Cache hit/miss 메트릭
4. Fallback to base LLM
"""

import hashlib
import json
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_shared.ports import ILLMProvider

logger = get_logger(__name__)


class CachedLLMAdapter(ILLMProvider):
    """
    Cached LLM Provider Adapter.

    Redis 캐싱으로 LLM 응답 속도 향상.

    구조:
    - L1: In-memory cache (빠름)
    - L2: Redis cache (공유)
    - L3: 실제 LLM API
    """

    def __init__(
        self,
        base_llm: ILLMProvider,
        redis_client=None,  # RedisAdapter 인스턴스
        cache_ttl: int = 3600,  # 1시간
        enable_cache: bool = True,
        in_memory_cache_size: int = 100,
    ):
        """
        Args:
            base_llm: 기본 LLM Provider (OptimizedLLMAdapter 권장)
            redis_client: Redis 클라이언트 (optional)
            cache_ttl: 캐시 TTL (초)
            enable_cache: 캐싱 활성화 여부
            in_memory_cache_size: In-memory 캐시 크기
        """
        self.base_llm = base_llm
        self.redis = redis_client
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache

        # In-memory LRU cache (L1)
        self._memory_cache: dict[str, Any] = {}
        self._cache_order: list[str] = []
        self._max_cache_size = in_memory_cache_size

        # 메트릭
        self._cache_hits = 0
        self._cache_misses = 0

    def _generate_cache_key(self, messages: list[dict[str, str]], model_tier: str, schema: type | None = None) -> str:
        """
        캐시 키 생성.

        Args:
            messages: 메시지 리스트
            model_tier: 모델 tier
            schema: Pydantic schema (optional)

        Returns:
            SHA256 해시 키
        """
        # 캐시 키 재료
        key_data = {
            "messages": messages,
            "model_tier": model_tier,
            "schema": schema.__name__ if schema else None,
        }

        # JSON 직렬화 → SHA256 해시
        key_json = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()

        return f"llm:cache:{key_hash}"

    async def _get_from_cache(self, cache_key: str) -> Any | None:
        """
        캐시에서 조회 (L1 → L2).

        Args:
            cache_key: 캐시 키

        Returns:
            캐시된 값 or None
        """
        if not self.enable_cache:
            return None

        # L1: In-memory cache
        if cache_key in self._memory_cache:
            logger.debug(f"Cache HIT (L1): {cache_key[:16]}...")
            self._cache_hits += 1
            return self._memory_cache[cache_key]

        # L2: Redis cache
        if self.redis:
            try:
                cached_value = await self.redis.get(cache_key)
                if cached_value:
                    logger.debug(f"Cache HIT (L2): {cache_key[:16]}...")
                    self._cache_hits += 1

                    # L1에도 캐싱
                    self._set_memory_cache(cache_key, cached_value)

                    return cached_value
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        # Cache MISS
        logger.debug(f"Cache MISS: {cache_key[:16]}...")
        self._cache_misses += 1
        return None

    async def _set_to_cache(self, cache_key: str, value: Any) -> None:
        """
        캐시에 저장 (L1 + L2).

        Args:
            cache_key: 캐시 키
            value: 저장할 값
        """
        if not self.enable_cache:
            return

        # L1: In-memory cache
        self._set_memory_cache(cache_key, value)

        # L2: Redis cache
        if self.redis:
            try:
                await self.redis.set(cache_key, value, ttl=self.cache_ttl)
                logger.debug(f"Cached to Redis: {cache_key[:16]}...")
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")

    def _set_memory_cache(self, key: str, value: Any) -> None:
        """
        In-memory cache에 저장 (LRU).

        Args:
            key: 캐시 키
            value: 저장할 값
        """
        # 이미 존재하면 순서만 업데이트
        if key in self._memory_cache:
            self._cache_order.remove(key)
            self._cache_order.append(key)
            self._memory_cache[key] = value
            return

        # 용량 초과 시 가장 오래된 것 제거 (LRU)
        if len(self._memory_cache) >= self._max_cache_size:
            oldest_key = self._cache_order.pop(0)
            del self._memory_cache[oldest_key]

        # 새로 추가
        self._memory_cache[key] = value
        self._cache_order.append(key)

    async def complete(self, messages: list[dict[str, str]], model_tier: str = "medium", **kwargs: Any) -> str:
        """
        텍스트 완성 (캐싱 적용).

        Args:
            messages: 메시지 리스트
            model_tier: 모델 tier
            **kwargs: 추가 인자

        Returns:
            완성된 텍스트
        """
        # 캐시 키 생성
        cache_key = self._generate_cache_key(messages, model_tier)

        # 캐시 조회
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # LLM 호출
        result = await self.base_llm.complete(messages, model_tier, **kwargs)

        # 캐싱
        await self._set_to_cache(cache_key, result)

        return result

    async def complete_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: type,
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> Any:
        """
        구조화된 출력 (캐싱 적용).

        Args:
            messages: 메시지 리스트
            schema: Pydantic schema
            model_tier: 모델 tier
            **kwargs: 추가 인자

        Returns:
            Pydantic 인스턴스
        """
        # 캐시 키 생성
        cache_key = self._generate_cache_key(messages, model_tier, schema)

        # 캐시 조회
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            # JSON → Pydantic
            return schema.model_validate(cached_result)

        # LLM 호출
        result = await self.base_llm.complete_with_schema(messages, schema, model_tier, **kwargs)

        # Pydantic → JSON (캐싱)
        result_dict = result.model_dump() if hasattr(result, "model_dump") else result
        await self._set_to_cache(cache_key, result_dict)

        return result

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """
        임베딩 생성 (캐싱 적용).

        Args:
            text: 텍스트
            model: 임베딩 모델

        Returns:
            임베딩 벡터
        """
        # 캐시 키 생성
        cache_key = f"llm:embedding:{hashlib.sha256(text.encode()).hexdigest()}"

        # 캐시 조회
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # LLM 호출
        result = await self.base_llm.get_embedding(text, model)

        # 캐싱
        await self._set_to_cache(cache_key, result)

        return result

    def get_cache_stats(self) -> dict[str, Any]:
        """
        캐시 통계 조회.

        Returns:
            캐시 통계 (hits, misses, hit_rate)
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total,
            "hit_rate_percent": hit_rate,
            "memory_cache_size": len(self._memory_cache),
        }
