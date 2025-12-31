"""
Common Utility Functions

중복 코드 패턴을 추출한 공통 유틸리티.

1. LazyClientInitializer - 지연 초기화 패턴
2. build_batch_values_clause - SQL 배치 쿼리 빌더
3. TTLCache - Generic LRU 캐시 with TTL
4. from_row - Row-to-Model 변환기
5. cached_method - 캐시 히트/미스 데코레이터
"""

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import fields, is_dataclass
from functools import wraps
from threading import Lock
from typing import Any, Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
ModelT = TypeVar("ModelT")


# =============================================================================
# 1. LazyClientInitializer - 지연 클라이언트 초기화
# =============================================================================


class LazyClientInitializer(Generic[T]):
    """
    지연 클라이언트 초기화 패턴.

    11+ 어댑터에서 중복되던 _get_client() 패턴을 일반화.

    Usage:
        class RedisAdapter:
            def __init__(self, host: str, port: int):
                self._client_init = LazyClientInitializer[Redis]()
                self.host = host
                self.port = port

            async def _get_client(self) -> Redis:
                return await self._client_init.get_or_create(
                    lambda: Redis(host=self.host, port=self.port)
                )

            async def close(self) -> None:
                if client := self._client_init.get_if_exists():
                    await client.close()
                self._client_init.reset()
    """

    def __init__(self) -> None:
        self._client: T | None = None
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        factory: Callable[[], T] | Callable[[], Awaitable[T]],
    ) -> T:
        """
        클라이언트 인스턴스를 가져오거나 생성.

        Args:
            factory: 클라이언트 생성 함수 (sync 또는 async)

        Returns:
            클라이언트 인스턴스
        """
        if self._client is not None:
            return self._client

        async with self._lock:
            # Double-check locking
            if self._client is not None:
                return self._client

            result = factory()
            if asyncio.iscoroutine(result):
                self._client = await result  # type: ignore[assignment]
            else:
                self._client = result  # type: ignore[assignment]

            return self._client  # type: ignore[return-value]

    def get_if_exists(self) -> T | None:
        """이미 생성된 클라이언트 반환 (없으면 None)"""
        return self._client

    def reset(self) -> None:
        """클라이언트 참조 해제"""
        self._client = None


# =============================================================================
# 2. build_batch_values_clause - SQL 배치 VALUES 절 생성
# =============================================================================


def build_batch_values_clause(num_fields: int, row_count: int, start_index: int = 1) -> str:
    """
    PostgreSQL 배치 INSERT를 위한 VALUES 절 생성.

    4곳에서 중복되던 placeholder 생성 로직을 통합.

    Args:
        num_fields: 필드 수
        row_count: 행 수
        start_index: 시작 placeholder 번호 (기본: 1)

    Returns:
        VALUES 절 문자열 (예: "($1, $2, $3), ($4, $5, $6)")

    Example:
        >>> build_batch_values_clause(3, 2)
        '($1, $2, $3), ($4, $5, $6)'

        >>> build_batch_values_clause(2, 3, start_index=5)
        '($5, $6), ($7, $8), ($9, $10)'
    """
    placeholders = []
    current = start_index

    for _ in range(row_count):
        row_placeholders = ", ".join(f"${i}" for i in range(current, current + num_fields))
        placeholders.append(f"({row_placeholders})")
        current += num_fields

    return ", ".join(placeholders)


def build_batch_values_list(items: list[Any], field_extractor: Callable[[Any], list[Any]]) -> list[Any]:
    """
    배치 INSERT를 위한 값 리스트 생성.

    Args:
        items: 모델 객체 리스트
        field_extractor: 객체에서 필드 값 추출 함수

    Returns:
        평탄화된 값 리스트

    Example:
        >>> def extract(chunk): return [chunk.id, chunk.name, chunk.value]
        >>> build_batch_values_list([chunk1, chunk2], extract)
        [chunk1.id, chunk1.name, chunk1.value, chunk2.id, chunk2.name, chunk2.value]
    """
    values = []
    for item in items:
        values.extend(field_extractor(item))
    return values


# =============================================================================
# 3. TTLCache - Generic LRU 캐시 with TTL
# =============================================================================


class TTLCache(Generic[K, V]):
    """
    Thread-safe Generic LRU Cache with TTL.

    7곳에서 중복되던 캐시 히트/미스 로직을 통합.

    Features:
    - LRU eviction
    - TTL expiration
    - Hit/miss statistics
    - Thread-safe

    Usage:
        cache: TTLCache[str, MyModel] = TTLCache(maxsize=1000, ttl=300)

        # Get with fallback
        value = cache.get("key")
        if value is None:
            value = await fetch_from_db("key")
            cache.set("key", value)
    """

    def __init__(self, maxsize: int = 1000, ttl: int = 300) -> None:
        """
        Args:
            maxsize: 최대 항목 수
            ttl: Time-to-live (초)
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[K, tuple[V, float]] = OrderedDict()  # (value, expires_at)
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        """
        캐시에서 값 조회.

        Args:
            key: 캐시 키

        Returns:
            값 또는 None (미스 또는 만료)
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            value, expires_at = entry

            # TTL 체크
            if time.time() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # LRU: move to end
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: K, value: V, ttl: int | None = None) -> None:
        """
        캐시에 값 저장.

        Args:
            key: 캐시 키
            value: 값
            ttl: 개별 TTL (None이면 기본값 사용)
        """
        with self._lock:
            # 기존 항목 제거
            if key in self._cache:
                del self._cache[key]

            # LRU eviction
            while len(self._cache) >= self.maxsize > 0:
                self._cache.popitem(last=False)

            effective_ttl = ttl if ttl is not None else self.ttl
            expires_at = time.time() + effective_ttl
            self._cache[key] = (value, expires_at)

    def delete(self, key: K) -> bool:
        """캐시에서 삭제. 삭제 성공 시 True."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """캐시 전체 삭제"""
        with self._lock:
            self._cache.clear()

    def invalidate_by_prefix(self, prefix: str) -> int:
        """
        prefix로 시작하는 키들 무효화.

        Args:
            prefix: 키 prefix

        Returns:
            삭제된 항목 수
        """
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if str(k).startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    def stats(self) -> dict[str, Any]:
        """캐시 통계"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (self._hits / total * 100) if total > 0 else 0.0,
                "size": len(self._cache),
                "maxsize": self.maxsize,
                "ttl": self.ttl,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None


# =============================================================================
# 4. from_row - Row-to-Model 변환
# =============================================================================


def from_row(
    row: dict[str, Any],
    model_class: type[ModelT],
    json_fields: list[str] | None = None,
    field_mapping: dict[str, str] | None = None,
) -> ModelT:
    """
    DB row를 모델 객체로 변환.

    7+ 스토어에서 중복되던 row-to-model 변환 로직을 통합.

    Args:
        row: DB row (dict)
        model_class: 대상 모델 클래스 (dataclass 권장)
        json_fields: JSON deserialize가 필요한 필드 목록
        field_mapping: DB 컬럼명 → 모델 필드명 매핑 (다를 경우)

    Returns:
        모델 인스턴스

    Example:
        @dataclass
        class Chunk:
            chunk_id: str
            attrs: dict
            children: list

        chunk = from_row(
            row={"chunk_id": "abc", "attrs": '{"key": "val"}'},
            model_class=Chunk,
            json_fields=["attrs"],
        )
    """
    json_fields = json_fields or []
    field_mapping = field_mapping or {}

    data = {}
    for key, value in row.items():
        # 필드 매핑 적용
        target_key = field_mapping.get(key, key)

        # JSON 파싱
        if key in json_fields and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # 파싱 실패 시 원본 유지

        data[target_key] = value

    # Dataclass인 경우 필드 필터링
    if is_dataclass(model_class):
        valid_fields = {f.name for f in fields(model_class)}
        data = {k: v for k, v in data.items() if k in valid_fields}

    return model_class(**data)


def to_row(
    model: Any,
    json_fields: list[str] | None = None,
    exclude_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    모델 객체를 DB row로 변환.

    Args:
        model: 모델 인스턴스
        json_fields: JSON serialize가 필요한 필드 목록
        exclude_fields: 제외할 필드 목록

    Returns:
        DB row dict
    """
    json_fields = json_fields or []
    exclude_fields = exclude_fields or []

    if is_dataclass(model):
        data = {f.name: getattr(model, f.name) for f in fields(model)}
    elif hasattr(model, "__dict__"):
        data = dict(model.__dict__)
    else:
        raise TypeError(f"Cannot convert {type(model)} to row")

    # 필드 제외
    for field in exclude_fields:
        data.pop(field, None)

    # JSON 직렬화
    for field in json_fields:
        if field in data and data[field] is not None:
            data[field] = json.dumps(data[field])

    return data


# =============================================================================
# 5. cached_method - 캐시 적용 데코레이터
# =============================================================================


def cached_method(
    cache_attr: str,
    key_builder: Callable[..., str],
    result_transformer: Callable[[Any], Any] | None = None,
):
    """
    메서드에 캐싱을 적용하는 데코레이터.

    CachedGraphStore의 8개 중복 메서드를 대체.

    Args:
        cache_attr: 캐시 객체 속성명 (예: "_relation_cache")
        key_builder: 캐시 키 생성 함수
        result_transformer: 결과 변환 함수 (예: set → list)

    Usage:
        class CachedStore:
            def __init__(self):
                self._cache = TTLCache(maxsize=1000, ttl=300)
                self.store = ActualStore()

            @cached_method(
                cache_attr="_cache",
                key_builder=lambda self, func_id: f"called_by:{func_id}",
                result_transformer=list,
            )
            async def query_called_by(self, func_id: str) -> list[str]:
                result = await self.store.query_called_by(func_id)
                return set(result)  # 캐시에는 set으로 저장
    """

    def decorator(method: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(method)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> T:
            cache: TTLCache = getattr(self, cache_attr)
            cache_key = key_builder(self, *args, **kwargs)

            # Cache hit
            cached = cache.get(cache_key)
            if cached is not None:
                if result_transformer:
                    return result_transformer(cached)
                return cached

            # Cache miss - call original method
            result = await method(self, *args, **kwargs)

            # Store in cache
            cache.set(cache_key, result)

            # Transform for return if needed
            if result_transformer:
                return result_transformer(result)
            return result

        return wrapper

    return decorator


# =============================================================================
# 6. Batch Processing Utilities
# =============================================================================


async def process_in_batches(
    items: list[T],
    batch_size: int,
    processor: Callable[[list[T]], Awaitable[Any]],
    max_concurrency: int = 4,
) -> list[Any]:
    """
    리스트를 배치로 나눠 병렬 처리.

    Qdrant, Chunk Store 등에서 중복되던 배치 처리 로직을 통합.

    Args:
        items: 처리할 항목들
        batch_size: 배치 크기
        processor: 배치 처리 함수
        max_concurrency: 최대 동시 실행 수

    Returns:
        각 배치의 결과 리스트
    """
    if not items:
        return []

    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

    if len(batches) <= 1:
        # 단일 배치는 바로 처리
        return [await processor(items)]

    # 병렬 처리 with concurrency limit
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[Any] = []

    async def process_batch(batch: list[T]) -> Any:
        async with semaphore:
            return await processor(batch)

    results = await asyncio.gather(*[process_batch(batch) for batch in batches])
    return list(results)


def deduplicate_by_key(items: list[T], key_func: Callable[[T], Any]) -> list[T]:
    """
    키 함수 기준으로 중복 제거 (마지막 항목 유지).

    Args:
        items: 항목 리스트
        key_func: 키 추출 함수

    Returns:
        중복 제거된 리스트
    """
    seen: dict[Any, T] = {}
    for item in items:
        seen[key_func(item)] = item
    return list(seen.values())
