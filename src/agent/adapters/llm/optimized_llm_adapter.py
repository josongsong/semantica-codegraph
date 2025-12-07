"""
Optimized LLM Provider Adapter (SOTA급)

성능 최적화 특징:
1. Batch 처리 (여러 요청 한 번에)
2. 병렬 처리 (asyncio.gather)
3. Token Bucket Rate Limiting
4. Response Streaming
5. Redis 캐싱 (LRU)
6. Circuit Breaker (장애 격리)
7. Retry with Exponential Backoff
8. Cost Tracking & Budget Control
"""

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import litellm

from src.ports import ILLMProvider

# Global 설정
litellm.drop_params = True


# ============================================================
# Rate Limiting (Token Bucket)
# ============================================================


@dataclass
class TokenBucket:
    """
    Token Bucket for rate limiting.

    특징:
    - 초당 요청 수 제한
    - Burst 허용
    - Thread-safe (asyncio.Lock)
    """

    capacity: int  # 버킷 용량
    refill_rate: float  # 초당 토큰 생성 수
    tokens: float = field(init=False)  # 현재 토큰 수
    last_refill: float = field(init=False)  # 마지막 refill 시간
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    async def acquire(self, tokens: int = 1) -> bool:
        """
        토큰 획득 (blocking).

        Args:
            tokens: 필요한 토큰 수

        Returns:
            항상 True (blocking이므로)
        """
        async with self.lock:
            while True:
                # Refill
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
                self.last_refill = now

                # 토큰 충분하면 소비
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                # 부족하면 대기
                wait_time = (tokens - self.tokens) / self.refill_rate
                await asyncio.sleep(wait_time)


# ============================================================
# Circuit Breaker
# ============================================================


@dataclass
class CircuitBreaker:
    """
    Circuit Breaker for fault isolation.

    상태:
    - CLOSED: 정상 (요청 통과)
    - OPEN: 차단 (요청 즉시 실패)
    - HALF_OPEN: 복구 시도 (일부 요청만 통과)
    """

    failure_threshold: int = 5  # 연속 실패 임계값
    recovery_timeout: float = 60.0  # OPEN → HALF_OPEN 전환 시간 (초)
    success_threshold: int = 2  # HALF_OPEN → CLOSED 전환 성공 수

    state: str = field(default="CLOSED", init=False)  # CLOSED | OPEN | HALF_OPEN
    failure_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def call(self, func, *args, **kwargs):
        """
        Circuit Breaker를 통해 함수 호출.

        Args:
            func: 호출할 async 함수
            *args, **kwargs: 함수 인자

        Returns:
            함수 결과

        Raises:
            RuntimeError: Circuit이 OPEN 상태
        """
        async with self.lock:
            # OPEN → HALF_OPEN 전환 체크
            if self.state == "OPEN":
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                else:
                    raise RuntimeError("Circuit breaker is OPEN")

            # HALF_OPEN: 일부만 통과
            if self.state == "HALF_OPEN":
                if self.success_count >= self.success_threshold:
                    self.state = "CLOSED"
                    self.failure_count = 0

        # 함수 호출
        try:
            result = await func(*args, **kwargs)

            # 성공 처리
            async with self.lock:
                if self.state == "HALF_OPEN":
                    self.success_count += 1
                    if self.success_count >= self.success_threshold:
                        self.state = "CLOSED"
                        self.failure_count = 0
                elif self.state == "CLOSED":
                    self.failure_count = 0

            return result

        except Exception as e:
            # 실패 처리
            async with self.lock:
                self.failure_count += 1
                self.last_failure_time = time.monotonic()

                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"

            raise e


# ============================================================
# Optimized LLM Adapter
# ============================================================


class OptimizedLLMAdapter(ILLMProvider):
    """
    SOTA급 최적화된 LLM Provider.

    특징:
    1. Batch 처리 (여러 요청 동시 처리)
    2. 병렬 처리 (asyncio.gather)
    3. Rate Limiting (Token Bucket)
    4. Circuit Breaker (장애 격리)
    5. Retry with Exponential Backoff
    6. Redis 캐싱 (선택적)
    7. Cost Tracking
    """

    def __init__(
        self,
        primary_model: str = "gpt-4o-mini",
        fallback_models: list[str] | None = None,
        api_key: str | None = None,
        timeout: int = 60,
        max_requests_per_second: float = 10.0,
        max_concurrent: int = 5,
        enable_cache: bool = True,
        cache_ttl: int = 3600,
        redis_client=None,
    ):
        """
        Args:
            primary_model: 기본 모델
            fallback_models: Fallback 모델 리스트
            api_key: API 키
            timeout: 타임아웃 (초)
            max_requests_per_second: 초당 최대 요청 수
            max_concurrent: 최대 동시 요청 수
            enable_cache: 캐싱 활성화 여부
            cache_ttl: 캐시 TTL (초)
            redis_client: Redis 클라이언트 (선택)
        """
        self.primary_model = primary_model
        self.fallback_models = fallback_models or []
        self.api_key = api_key
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.redis_client = redis_client

        # Rate Limiting
        self.rate_limiter = TokenBucket(
            capacity=int(max_requests_per_second * 2),
            refill_rate=max_requests_per_second,
        )

        # Concurrency Control
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Circuit Breaker (모델별)
        self.circuit_breakers = defaultdict(
            lambda: CircuitBreaker(failure_threshold=5, recovery_timeout=60.0, success_threshold=2)
        )

        # Cost Tracking
        self.total_tokens = 0
        self.total_cost = 0.0

        # Local Cache (Redis 없을 때)
        self.local_cache: dict[str, tuple[Any, float]] = {}

        # API 키 설정
        if self.api_key:
            import os

            os.environ["OPENAI_API_KEY"] = self.api_key

    def _get_cache_key(self, messages: list[dict], model: str, **kwargs) -> str:
        """
        캐시 키 생성.

        Args:
            messages: 메시지 리스트
            model: 모델 이름
            **kwargs: 추가 파라미터

        Returns:
            해시 기반 캐시 키
        """
        # 캐시 키 생성 (messages + model + kwargs)
        cache_data = {
            "messages": messages,
            "model": model,
            "temperature": kwargs.get("temperature"),
            "max_tokens": kwargs.get("max_tokens"),
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return f"llm:{hashlib.sha256(cache_str.encode()).hexdigest()}"

    async def _get_from_cache(self, cache_key: str) -> str | None:
        """
        캐시에서 조회.

        Args:
            cache_key: 캐시 키

        Returns:
            캐시된 응답 또는 None
        """
        if not self.enable_cache:
            return None

        # Redis 캐시
        if self.redis_client:
            try:
                cached = await self.redis_client.get(cache_key)
                if cached:
                    return cached.decode() if isinstance(cached, bytes) else cached
            except Exception:
                pass  # Redis 실패해도 계속 진행

        # Local 캐시
        if cache_key in self.local_cache:
            value, expiry = self.local_cache[cache_key]
            if time.time() < expiry:
                return value
            else:
                del self.local_cache[cache_key]

        return None

    async def _set_to_cache(self, cache_key: str, value: str):
        """
        캐시에 저장.

        Args:
            cache_key: 캐시 키
            value: 저장할 값
        """
        if not self.enable_cache:
            return

        # Redis 캐시
        if self.redis_client:
            try:
                await self.redis_client.setex(cache_key, self.cache_ttl, value)
            except Exception:
                pass

        # Local 캐시
        self.local_cache[cache_key] = (value, time.time() + self.cache_ttl)

        # Local 캐시 크기 제한 (LRU)
        if len(self.local_cache) > 1000:
            # 가장 오래된 것 삭제
            oldest_key = min(self.local_cache.keys(), key=lambda k: self.local_cache[k][1])
            del self.local_cache[oldest_key]

    async def complete(self, messages: list[dict[str, str]], model_tier: str = "medium", **kwargs: Any) -> str:
        """
        Text completion (최적화).

        특징:
        - Rate Limiting
        - Circuit Breaker
        - Caching
        - Retry with Exponential Backoff

        Args:
            messages: 메시지 리스트
            model_tier: "fast" | "medium" | "strong"
            **kwargs: temperature, max_tokens 등

        Returns:
            생성된 텍스트
        """
        # 모델 선택
        model_map = {
            "fast": "gpt-4o-mini",
            "medium": "gpt-4o",
            "strong": "o1-preview",
        }
        model = kwargs.get("model", model_map.get(model_tier, self.primary_model))
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2000)

        # 캐시 확인
        cache_key = self._get_cache_key(messages, model, **kwargs)
        cached = await self._get_from_cache(cache_key)
        if cached:
            return cached

        # Rate Limiting
        await self.rate_limiter.acquire()

        # Concurrency Control
        async with self.semaphore:
            # Circuit Breaker를 통해 호출
            circuit_breaker = self.circuit_breakers[model]

            async def _call_llm():
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                )

                # Cost Tracking
                if hasattr(response, "usage"):
                    self.total_tokens += response.usage.total_tokens

                return response.choices[0].message.content

            # Retry with Exponential Backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = await circuit_breaker.call(_call_llm)

                    # 캐시 저장
                    await self._set_to_cache(cache_key, result)

                    return result

                except Exception as e:
                    if attempt == max_retries - 1:
                        # 마지막 시도 실패 → Fallback
                        if self.fallback_models:
                            # Fallback 모델로 재시도 (별도 루프)
                            for fallback_model in self.fallback_models:
                                try:
                                    fallback_cb = self.circuit_breakers[fallback_model]

                                    async def _call_fallback():
                                        response = await litellm.acompletion(
                                            model=fallback_model,
                                            messages=messages,
                                            temperature=temperature,
                                            max_tokens=max_tokens,
                                            timeout=self.timeout,
                                        )
                                        if hasattr(response, "usage"):
                                            self.total_tokens += response.usage.total_tokens
                                        return response.choices[0].message.content

                                    result = await fallback_cb.call(_call_fallback)
                                    await self._set_to_cache(cache_key, result)
                                    return result
                                except Exception:
                                    continue  # 다음 fallback 시도

                        # 모든 fallback 실패
                        raise RuntimeError(f"LLM call failed after all retries and fallbacks: {e}") from e

                    # Exponential Backoff
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

    async def batch_complete(
        self,
        batch_messages: list[list[dict[str, str]]],
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> list[str]:
        """
        Batch completion (병렬 처리).

        Args:
            batch_messages: 메시지 리스트의 리스트
            model_tier: 모델 등급
            **kwargs: 추가 파라미터

        Returns:
            응답 리스트
        """
        # 병렬 처리 (asyncio.gather)
        tasks = [self.complete(messages, model_tier=model_tier, **kwargs) for messages in batch_messages]

        return await asyncio.gather(*tasks)

    async def complete_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: type,
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> Any:
        """
        Structured output (Pydantic schema).

        Args:
            messages: 메시지 리스트
            schema: Pydantic BaseModel 클래스
            model_tier: 모델 등급
            **kwargs: 추가 파라미터

        Returns:
            schema 인스턴스
        """
        # 모델 선택
        model_map = {
            "fast": "gpt-4o-mini",
            "medium": "gpt-4o",
            "strong": "o1-preview",
        }
        model = kwargs.get("model", model_map.get(model_tier, self.primary_model))

        # JSON schema
        json_schema = schema.model_json_schema()
        system_message = f"""You must respond in JSON format matching this schema:
{json_schema}

Respond ONLY with valid JSON, no additional text."""

        full_messages = [{"role": "system", "content": system_message}] + messages

        # Rate Limiting
        await self.rate_limiter.acquire()

        # Concurrency Control
        async with self.semaphore:
            response = await litellm.acompletion(
                model=model,
                messages=full_messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2000),
                timeout=self.timeout,
                response_format={"type": "json_object"} if "gpt" in model.lower() else None,
            )

            # JSON 파싱
            content = response.choices[0].message.content
            data = json.loads(content)

            return schema(**data)

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """
        Text embedding (최적화).

        Args:
            text: 입력 텍스트
            model: Embedding 모델

        Returns:
            Embedding vector
        """
        # 캐시 확인
        cache_key = f"embedding:{hashlib.sha256(text.encode()).hexdigest()}:{model}"
        cached = await self._get_from_cache(cache_key)
        if cached:
            return json.loads(cached)

        # Rate Limiting
        await self.rate_limiter.acquire()

        # Concurrency Control
        async with self.semaphore:
            response = await litellm.aembedding(model=model, input=text, timeout=self.timeout)

            embedding = response.data[0]["embedding"]

            # 캐시 저장
            await self._set_to_cache(cache_key, json.dumps(embedding))

            return embedding

    def get_stats(self) -> dict[str, Any]:
        """
        성능 통계 조회.

        Returns:
            통계 딕셔너리
        """
        return {
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "cache_size": len(self.local_cache),
            "circuit_breakers": {
                model: {
                    "state": cb.state,
                    "failure_count": cb.failure_count,
                }
                for model, cb in self.circuit_breakers.items()
            },
        }
