"""
Redis Client

Redis 캐시 클라이언트
"""


class RedisClient:
    """Redis 클라이언트 래퍼"""

    def __init__(self, redis_adapter):
        """
        초기화

        Args:
            redis_adapter: Redis 어댑터
        """
        self.redis = redis_adapter

    async def get(self, key: str) -> str | None:
        """값 가져오기"""
        return await self.redis.get(key)

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """값 설정"""
        await self.redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        """값 삭제"""
        await self.redis.delete(key)

    async def exists(self, key: str) -> bool:
        """키 존재 여부"""
        return await self.redis.exists(key)
