"""
Redis Cache Adapter (stub)

Provides minimal get/set interfaces. Replace with aioredis/redis-py integration.
"""

from typing import Any


class RedisAdapter:
    """Placeholder adapter for Redis operations."""

    def __init__(self, host: str, port: int, password: str | None, db: int) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.db = db

    async def get(self, key: str) -> Any:
        raise NotImplementedError("RedisAdapter.get is not implemented yet")

    async def set(self, key: str, value: Any, expire_seconds: int | None = None) -> None:
        raise NotImplementedError("RedisAdapter.set is not implemented yet")
