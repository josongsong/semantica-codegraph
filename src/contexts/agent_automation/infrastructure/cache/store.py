"""Redis Cache Store - Redis 기반 캐시 저장소."""

from typing import TYPE_CHECKING, Any

from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.cache.redis import RedisAdapter

logger = get_logger(__name__)


class RedisCacheStore:
    """Redis 기반 캐시 저장소."""

    def __init__(
        self,
        redis_adapter: "RedisAdapter",
        ttl: int = 3600,
        key_prefix: str = "prompt_cache:",
    ):
        """
        Args:
            redis_adapter: RedisAdapter 인스턴스
            ttl: TTL (초)
            key_prefix: 키 prefix
        """
        self.redis = redis_adapter
        self.ttl = ttl
        self.key_prefix = key_prefix

    async def get(self, cache_key: str) -> Any | None:
        """캐시 조회.

        Args:
            cache_key: 캐시 키

        Returns:
            캐시된 값 또는 None
        """
        full_key = f"{self.key_prefix}{cache_key}"

        try:
            value = await self.redis.get(full_key)
            if value:
                logger.debug(f"Cache hit: {cache_key[:16]}...")
                # RedisAdapter.get()은 이미 JSON deserialize 수행
                return value
            else:
                logger.debug(f"Cache miss: {cache_key[:16]}...")
                return None

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    async def set(self, cache_key: str, value: Any) -> bool:
        """캐시 저장.

        Args:
            cache_key: 캐시 키
            value: 저장할 값

        Returns:
            성공 여부
        """
        full_key = f"{self.key_prefix}{cache_key}"

        try:
            # RedisAdapter.set()이 JSON serialize 수행
            await self.redis.set(full_key, value, ex=self.ttl)
            logger.debug(f"Cache set: {cache_key[:16]}... (TTL={self.ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    async def delete(self, cache_key: str) -> bool:
        """캐시 삭제.

        Args:
            cache_key: 캐시 키

        Returns:
            성공 여부
        """
        full_key = f"{self.key_prefix}{cache_key}"

        try:
            await self.redis.delete(full_key)
            logger.debug(f"Cache deleted: {cache_key[:16]}...")
            return True

        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    async def clear_all(self) -> int:
        """모든 캐시 삭제.

        Returns:
            삭제된 키 개수
        """
        try:
            pattern = f"{self.key_prefix}*"
            # RedisAdapter를 통해 클라이언트 얻기
            client = await self.redis._get_client()
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache keys")
                return len(keys)

            return 0

        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return 0
