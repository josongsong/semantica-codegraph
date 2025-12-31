"""
Redis Cache Adapter

Provides async Redis operations using redis-py.

Features:
- Lazy client initialization
- JSON serialization/deserialization
- Expiration support
- Connection health checks

Requirements:
    pip install redis[asyncio]
"""

import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from codegraph_shared.common.observability import get_logger
from codegraph_shared.common.utils import LazyClientInitializer

logger = get_logger(__name__)


class RedisAdapter:
    """
    Production Redis adapter with async support.

    Uses redis-py (async) for caching operations.
    Automatically handles JSON serialization for complex types.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
    ) -> None:
        """
        Initialize Redis adapter.

        Args:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            password: Optional Redis password
            db: Redis database number (default: 0)
        """
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self._client_init: LazyClientInitializer[Redis] = LazyClientInitializer()

    async def _get_client(self) -> Redis:
        """
        Get or create Redis client (lazy initialization).

        Returns:
            Redis client instance
        """
        return await self._client_init.get_or_create(
            lambda: Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=True,
            )
        )

    async def get(self, key: str) -> Any:
        """
        Get value from Redis.

        Automatically deserializes JSON if value is a JSON string.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found

        Raises:
            RuntimeError: If Redis operation fails
        """
        try:
            client = await self._get_client()
            value = await client.get(key)

            if value is None:
                return None

            # Try to deserialize as JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Not JSON, return as-is
                return value

        except RedisError as e:
            logger.error(f"Failed to get key {key}: {e}")
            raise RuntimeError(f"Failed to get key {key}: {e}") from e

    async def set(
        self,
        key: str,
        value: Any,
        expire_seconds: int | None = None,
        ex: int | None = None,  # Native redis client compatibility
        nx: bool = False,  # SET if Not eXists
        **kwargs: Any,
    ) -> bool | None:
        """
        Set value in Redis.

        Automatically serializes dicts/lists to JSON.
        Supports both RedisAdapter style (expire_seconds) and native Redis client style (ex, nx).

        Args:
            key: Cache key
            value: Value to cache (str, dict, list, etc.)
            expire_seconds: Optional expiration in seconds (RedisAdapter style)
            ex: Optional expiration in seconds (native Redis style)
            nx: Only set if key does not exist (native Redis SET NX)
            **kwargs: Additional Redis SET options

        Returns:
            For nx=True: True if key was set, False if key already exists (or None on error)
            For nx=False: None (Redis SET always succeeds)

        Raises:
            RuntimeError: If Redis operation fails
        """
        try:
            client = await self._get_client()

            # Serialize dicts/lists to JSON
            if isinstance(value, dict | list):
                value = json.dumps(value)

            # Use 'ex' if provided, otherwise use 'expire_seconds'
            expiration = ex if ex is not None else expire_seconds

            # Call native Redis client set() with all options
            result = await client.set(key, value, ex=expiration, nx=nx, **kwargs)

            return result

        except RedisError as e:
            logger.error(f"Failed to set key {key}: {e}")
            raise RuntimeError(f"Failed to set key {key}: {e}") from e

    async def delete(self, key: str) -> bool:
        """
        Delete key from Redis.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if key didn't exist

        Raises:
            RuntimeError: If Redis operation fails
        """
        try:
            client = await self._get_client()
            deleted = await client.delete(key)
            return deleted > 0

        except RedisError as e:
            logger.error(f"Failed to delete key {key}: {e}")
            raise RuntimeError(f"Failed to delete key {key}: {e}") from e

    async def exists(self, *keys: str) -> int:
        """
        Check if key(s) exist in Redis (native Redis client compatibility).

        Args:
            *keys: One or more cache keys

        Returns:
            Number of existing keys (0 if none exist)
        """
        try:
            client = await self._get_client()
            result = await client.exists(*keys)
            return result

        except RedisError as e:
            logger.error(f"Failed to check existence of keys: {e}")
            return 0

    async def ttl(self, key: str) -> int:
        """
        Get remaining TTL for key (native Redis client compatibility).

        Args:
            key: Cache key

        Returns:
            Remaining TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            client = await self._get_client()
            return await client.ttl(key)
        except RedisError as e:
            logger.error(f"Failed to get TTL for key {key}: {e}")
            return -2

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        """
        Execute Lua script (native Redis client compatibility).

        Args:
            script: Lua script to execute
            numkeys: Number of keys (vs. args)
            *keys_and_args: Keys and arguments for the script

        Returns:
            Script execution result
        """
        try:
            client = await self._get_client()
            return await client.eval(script, numkeys, *keys_and_args)
        except RedisError as e:
            logger.error(f"Failed to execute Lua script: {e}")
            raise RuntimeError(f"Failed to execute Lua script: {e}") from e

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration for key.

        Args:
            key: Cache key
            seconds: Expiration time in seconds

        Returns:
            True if expiration was set, False if key doesn't exist
        """
        try:
            client = await self._get_client()
            return await client.expire(key, seconds)

        except RedisError as e:
            logger.error(f"Failed to set expiration for key {key}: {e}")
            return False

    async def keys(self, pattern: str = "*", use_scan: bool = True) -> list[str]:
        """
        Get keys matching pattern using SCAN (non-blocking).

        Args:
            pattern: Key pattern (default: "*" for all keys)
            use_scan: Use SCAN iterator (default: True). Set False for small datasets.

        Returns:
            List of matching keys
        """
        try:
            client = await self._get_client()

            if use_scan:
                # Use SCAN iterator - O(1) per iteration, non-blocking
                keys_result = []
                async for key in client.scan_iter(match=pattern, count=100):
                    keys_result.append(key)
                return keys_result
            else:
                # Legacy KEYS command - only for small datasets
                return await client.keys(pattern)

        except RedisError as e:
            logger.error(f"Failed to get keys with pattern {pattern}: {e}")
            return []

    async def clear_all(self) -> None:
        """
        Clear all keys in current database.

        Warning: This is a destructive operation!
        """
        try:
            client = await self._get_client()
            await client.flushdb()
            logger.info(f"Cleared all keys in Redis DB {self.db}")

        except RedisError as e:
            logger.error(f"Failed to clear database: {e}")
            raise RuntimeError(f"Failed to clear database: {e}") from e

    async def ping(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if Redis is reachable, False otherwise
        """
        try:
            client = await self._get_client()
            await client.ping()
            return True

        except (RedisError, Exception) as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    async def close(self) -> None:
        """
        Close Redis connection.

        Should be called during application shutdown.
        """
        if client := self._client_init.get_if_exists():
            await client.aclose()
            self._client_init.reset()
            logger.info("Redis connection closed")
