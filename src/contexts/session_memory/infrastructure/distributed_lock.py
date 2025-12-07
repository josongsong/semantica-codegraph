"""
Distributed Lock

Redis 기반 분산 락 (multi-process/multi-server 지원)
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from src.infra.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


class DistributedLock:
    """
    Redis 기반 분산 락

    Redlock 알고리즘 간소화 버전
    """

    def __init__(
        self,
        redis_url: str,
        lock_key: str,
        ttl_seconds: int = 30,
        retry_delay_ms: int = 100,
        max_retries: int = 10,
    ):
        """
        Initialize distributed lock

        Args:
            redis_url: Redis 연결 URL
            lock_key: 락 키
            ttl_seconds: 락 TTL (초)
            retry_delay_ms: 재시도 대기 시간 (ms)
            max_retries: 최대 재시도 횟수
        """
        self.redis_url = redis_url
        self.lock_key = f"lock:{lock_key}"
        self.ttl_seconds = ttl_seconds
        self.retry_delay_ms = retry_delay_ms
        self.max_retries = max_retries

        self._redis: Any = None
        self._lock_value: str | None = None
        self._acquired = False
        self._enabled = False

    async def connect(self) -> bool:
        """
        Redis 연결

        Returns:
            True if connected
        """
        try:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )

            await self._redis.ping()
            self._enabled = True
            logger.info("distributed_lock_connected", url=self.redis_url)
            return True

        except Exception as e:
            logger.warning("distributed_lock_connection_failed", error=str(e))
            self._enabled = False
            return False

    async def acquire(self, blocking: bool = True) -> bool:
        """
        락 획득

        Args:
            blocking: True면 재시도, False면 즉시 반환

        Returns:
            True if lock acquired
        """
        if not self._enabled or self._redis is None:
            # Redis 없으면 로컬 락처럼 동작 (fallback)
            logger.warning("distributed_lock_disabled_fallback", key=self.lock_key)
            self._acquired = True
            return True

        start = datetime.now()
        self._lock_value = str(uuid.uuid4())
        retries = 0

        while True:
            # Try SET NX (set if not exists)
            acquired = await self._redis.set(
                self.lock_key,
                self._lock_value,
                nx=True,  # Only set if not exists
                ex=self.ttl_seconds,  # Expiry
            )

            if acquired:
                self._acquired = True
                duration_ms = (datetime.now() - start).total_seconds() * 1000
                record_counter("memory_distributed_lock_acquired_total", labels={"key": self.lock_key})
                record_histogram(
                    "memory_distributed_lock_acquire_duration_ms", duration_ms, labels={"key": self.lock_key}
                )
                logger.debug("distributed_lock_acquired", key=self.lock_key, retries=retries)
                return True

            # Not acquired
            if not blocking:
                record_counter("memory_distributed_lock_failed_total", labels={"key": self.lock_key})
                return False

            retries += 1

            if retries >= self.max_retries:
                logger.warning(
                    "distributed_lock_max_retries",
                    key=self.lock_key,
                    retries=retries,
                )
                record_counter("memory_distributed_lock_timeout_total", labels={"key": self.lock_key})
                return False

            # Wait and retry
            await asyncio.sleep(self.retry_delay_ms / 1000.0)

    async def release(self) -> bool:
        """
        락 해제

        Returns:
            True if released
        """
        if not self._acquired:
            logger.warning("distributed_lock_not_acquired", key=self.lock_key)
            return False

        if not self._enabled or self._redis is None:
            self._acquired = False
            return True

        # Lua script for safe release (only release if value matches)
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            released = await self._redis.eval(
                lua_script,
                1,  # Number of keys
                self.lock_key,
                self._lock_value,
            )

            if released:
                self._acquired = False
                self._lock_value = None
                record_counter("memory_distributed_lock_released_total", labels={"key": self.lock_key})
                logger.debug("distributed_lock_released", key=self.lock_key)
                return True
            else:
                logger.warning("distributed_lock_release_failed", key=self.lock_key)
                return False

        except Exception as e:
            logger.error("distributed_lock_release_error", key=self.lock_key, error=str(e))
            return False

    async def extend(self, additional_seconds: int = 30) -> bool:
        """
        락 연장 (long-running operation)

        Args:
            additional_seconds: 추가 시간 (초)

        Returns:
            True if extended
        """
        if not self._acquired or not self._enabled or self._redis is None:
            return False

        # Lua script for safe extend (only if value matches)
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        try:
            extended = await self._redis.eval(
                lua_script,
                1,
                self.lock_key,
                self._lock_value,
                str(additional_seconds),
            )

            if extended:
                logger.debug("distributed_lock_extended", key=self.lock_key, seconds=additional_seconds)
                return True
            else:
                return False

        except Exception as e:
            logger.error("distributed_lock_extend_error", key=self.lock_key, error=str(e))
            return False

    @property
    def is_acquired(self) -> bool:
        """락 획득 여부"""
        return self._acquired

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._acquired:
            await self.release()

        if self._redis is not None:
            await self._redis.close()
            self._enabled = False

    @asynccontextmanager
    async def lock(self, blocking: bool = True) -> AsyncGenerator[bool, None]:
        """
        Context manager for lock usage

        Args:
            blocking: True면 재시도, False면 즉시 반환

        Yields:
            True if lock acquired

        Example:
            async with lock.lock():
                # Critical section
                ...
        """
        acquired = await self.acquire(blocking=blocking)

        try:
            yield acquired
        finally:
            if acquired:
                await self.release()


class DistributedLockManager:
    """
    Distributed Lock 관리자

    여러 락을 관리하고 자동 초기화
    """

    def __init__(self, redis_url: str):
        """
        Initialize lock manager

        Args:
            redis_url: Redis 연결 URL
        """
        self.redis_url = redis_url
        self.locks: dict[str, DistributedLock] = {}
        self._connected = False

    async def connect(self) -> bool:
        """
        Redis 연결 (공유)

        Returns:
            True if connected
        """
        # Test connection
        try:
            import redis.asyncio as aioredis

            redis_client = await aioredis.from_url(self.redis_url, socket_connect_timeout=5)
            await redis_client.ping()
            await redis_client.close()

            self._connected = True
            logger.info("distributed_lock_manager_connected", url=self.redis_url)
            return True

        except Exception as e:
            logger.warning("distributed_lock_manager_connection_failed", error=str(e))
            self._connected = False
            return False

    def get_lock(
        self,
        lock_key: str,
        ttl_seconds: int = 30,
    ) -> DistributedLock:
        """
        락 가져오기 또는 생성

        Args:
            lock_key: 락 키
            ttl_seconds: 락 TTL

        Returns:
            DistributedLock
        """
        if lock_key not in self.locks:
            lock = DistributedLock(
                redis_url=self.redis_url,
                lock_key=lock_key,
                ttl_seconds=ttl_seconds,
            )

            # Auto-connect if manager is connected
            if self._connected:
                asyncio.create_task(lock.connect())

            self.locks[lock_key] = lock

        return self.locks[lock_key]

    @asynccontextmanager
    async def acquire_lock(
        self,
        lock_key: str,
        blocking: bool = True,
        ttl_seconds: int = 30,
    ) -> AsyncGenerator[bool, None]:
        """
        락 획득 (context manager)

        Args:
            lock_key: 락 키
            blocking: True면 재시도
            ttl_seconds: 락 TTL

        Yields:
            True if lock acquired

        Example:
            async with lock_manager.acquire_lock("episode:123"):
                # Critical section
                ...
        """
        lock = self.get_lock(lock_key, ttl_seconds)

        async with lock.lock(blocking=blocking) as acquired:
            yield acquired

    async def close_all(self) -> None:
        """모든 락 해제 및 종료"""
        for lock in self.locks.values():
            await lock.close()

        self.locks.clear()


# Global instance
_lock_manager: DistributedLockManager | None = None


def get_lock_manager(redis_url: str | None = None) -> DistributedLockManager:
    """
    전역 lock manager 가져오기

    Args:
        redis_url: Redis URL (첫 호출 시 필수)

    Returns:
        DistributedLockManager
    """
    global _lock_manager

    if _lock_manager is None:
        if redis_url is None:
            from .config import get_config

            redis_url = get_config().cache.redis_url

        _lock_manager = DistributedLockManager(redis_url)

    return _lock_manager
