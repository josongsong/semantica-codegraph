"""
Distributed Lock Implementation using Redis (Redlock algorithm).

Provides distributed locking for concurrent indexing jobs with:
- Redlock-based algorithm for single writer guarantee
- Exponential backoff for lock acquisition
- Automatic lock expiration (TTL)
- Lock extension for long-running jobs
- Context manager support

Requirements:
    - redis-py (async): pip install redis[asyncio]
    - Redis client type: redis.asyncio.Redis
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from src.common.observability import get_logger

logger = get_logger(__name__)
# Lua script for atomic lock release (check owner + delete)
RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua script for atomic lock extension (check owner + extend TTL)
EXTEND_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class LockAcquisitionError(Exception):
    """Raised when lock acquisition fails after retries."""

    pass


class LockReleaseError(Exception):
    """Raised when lock release fails (e.g., not owner)."""

    pass


class DistributedLock:
    """
    Redis-based distributed lock with Redlock algorithm.

    Features:
    - Single writer guarantee per lock key
    - Automatic expiration (TTL) for stale lock detection
    - Exponential backoff for lock contention
    - Lock extension for long-running operations
    - Context manager support for safe lock management

    Usage:
        async with DistributedLock(redis_client, "my_lock", ttl=30):
            # Critical section - only one process can enter
            await do_work()

        # Or manual management:
        lock = DistributedLock(redis_client, "my_lock", ttl=30)
        if await lock.acquire(blocking=True, timeout=10):
            try:
                await do_work()
            finally:
                await lock.release()
    """

    def __init__(
        self,
        redis_client: Any,
        lock_key: str,
        ttl: int = 30,
        retry_delay: float = 0.1,
        retry_max_delay: float = 5.0,
        jitter: float = 0.05,
    ):
        """
        Initialize distributed lock.

        Args:
            redis_client: Redis async client (redis.asyncio.Redis from redis-py)
                         Must support: set(nx=True, ex=...), eval(), exists(), ttl()
            lock_key: Unique key for the lock
            ttl: Lock expiration time in seconds (default: 30s)
            retry_delay: Initial retry delay in seconds (default: 0.1s)
            retry_max_delay: Maximum retry delay for exponential backoff (default: 5s)
            jitter: Random jitter factor for retry delays (default: 0.05 = 5%)
        """
        self.redis_client = redis_client
        self.lock_key = f"lock:{lock_key}"
        self.ttl = ttl
        self.retry_delay = retry_delay
        self.retry_max_delay = retry_max_delay
        self.jitter = jitter

        # Unique identifier for this lock instance (to verify ownership)
        self.lock_id = str(uuid.uuid4())
        self._acquired = False
        self._acquire_time: float | None = None

        logger.debug(f"DistributedLock initialized: key={self.lock_key}, ttl={ttl}s, id={self.lock_id[:8]}")

    async def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """
        Acquire the lock.

        Args:
            blocking: If True, wait until lock is acquired or timeout
                     If False, return immediately
            timeout: Maximum time to wait in seconds (None = wait forever)
                    Only applies when blocking=True

        Returns:
            True if lock was acquired, False otherwise

        Raises:
            LockAcquisitionError: If blocking=True and timeout expires
        """
        start_time = time.time()
        attempt = 0

        while True:
            # Try to acquire lock (SET NX EX)
            success = await self._try_acquire()

            if success:
                self._acquired = True
                self._acquire_time = time.time()
                elapsed = time.time() - start_time
                logger.info(
                    f"Lock acquired: key={self.lock_key}, id={self.lock_id[:8]}, "
                    f"attempts={attempt + 1}, elapsed={elapsed:.3f}s"
                )
                return True

            # Non-blocking mode - return immediately
            if not blocking:
                logger.debug(f"Lock acquisition failed (non-blocking): key={self.lock_key}")
                return False

            # Check timeout
            elapsed = time.time() - start_time
            if timeout is not None and elapsed >= timeout:
                logger.warning(
                    f"Lock acquisition timeout: key={self.lock_key}, timeout={timeout}s, attempts={attempt + 1}"
                )
                raise LockAcquisitionError(
                    f"Failed to acquire lock '{self.lock_key}' after {timeout}s ({attempt + 1} attempts)"
                )

            # Exponential backoff with jitter
            delay = min(self.retry_delay * (2**attempt), self.retry_max_delay)
            jitter_amount = delay * self.jitter * (2 * (time.time() % 1) - 1)  # ±jitter%
            delay += jitter_amount

            # Don't exceed remaining timeout
            if timeout is not None:
                delay = min(delay, timeout - elapsed)

            logger.debug(f"Lock busy, retrying in {delay:.3f}s: key={self.lock_key}, attempt={attempt + 1}")
            await asyncio.sleep(delay)
            attempt += 1

    async def _try_acquire(self) -> bool:
        """
        Try to acquire lock once (atomic SET NX EX).

        Returns:
            True if lock was acquired, False if already held by another process
        """
        try:
            # Redis SET with NX (only if not exists) and EX (expiration)
            # Returns True if key was set, False if key already exists
            result = await self.redis_client.set(self.lock_key, self.lock_id, ex=self.ttl, nx=True)

            return bool(result)

        except Exception as e:
            logger.error(f"Error acquiring lock: key={self.lock_key}, error={e}")
            return False

    async def release(self) -> bool:
        """
        Release the lock.

        Only the lock owner (matching lock_id) can release the lock.
        Uses Lua script for atomic check-and-delete.

        Returns:
            True if lock was released, False if not held by this instance

        Raises:
            LockReleaseError: If lock is not held or release fails
        """
        if not self._acquired:
            logger.warning(f"Attempted to release non-acquired lock: key={self.lock_key}")
            return False

        try:
            # Execute Lua script for atomic release
            result = await self.redis_client.eval(RELEASE_SCRIPT, 1, self.lock_key, self.lock_id)

            if result == 1:
                self._acquired = False
                hold_time = time.time() - self._acquire_time if self._acquire_time else 0
                logger.info(f"Lock released: key={self.lock_key}, id={self.lock_id[:8]}, hold_time={hold_time:.3f}s")
                return True
            else:
                # Lock expired or was taken by another process
                logger.warning(
                    f"Lock release failed (not owner or expired): key={self.lock_key}, id={self.lock_id[:8]}"
                )
                self._acquired = False
                return False

        except Exception as e:
            logger.error(f"Error releasing lock: key={self.lock_key}, error={e}")
            self._acquired = False
            raise LockReleaseError(f"Failed to release lock '{self.lock_key}': {e}") from e

    async def extend(self, additional_ttl: int | None = None) -> bool:
        """
        Extend lock expiration time (for long-running jobs).

        Args:
            additional_ttl: Additional TTL in seconds (default: use original TTL)

        Returns:
            True if lock was extended, False if not held by this instance
        """
        if not self._acquired:
            logger.warning(f"Attempted to extend non-acquired lock: key={self.lock_key}")
            return False

        ttl = additional_ttl or self.ttl

        try:
            # Execute Lua script for atomic extension
            result = await self.redis_client.eval(EXTEND_SCRIPT, 1, self.lock_key, self.lock_id, ttl)

            if result == 1:
                logger.debug(f"Lock extended: key={self.lock_key}, id={self.lock_id[:8]}, ttl={ttl}s")
                return True
            else:
                # Lock expired or was taken by another process
                logger.warning(f"Lock extension failed (not owner or expired): key={self.lock_key}")
                self._acquired = False
                return False

        except Exception as e:
            logger.error(f"Error extending lock: key={self.lock_key}, error={e}")
            return False

    async def is_locked(self) -> bool:
        """
        Check if lock is currently held (by any process).

        Returns:
            True if lock exists, False otherwise
        """
        try:
            exists = await self.redis_client.exists(self.lock_key)
            return bool(exists)
        except Exception as e:
            logger.error(f"Error checking lock status: key={self.lock_key}, error={e}")
            return False

    async def get_ttl(self) -> int:
        """
        Get remaining TTL for the lock.

        Returns:
            Remaining TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            ttl = await self.redis_client.ttl(self.lock_key)
            return int(ttl)
        except Exception as e:
            logger.error(f"Error getting lock TTL: key={self.lock_key}, error={e}")
            return -2

    def is_acquired(self) -> bool:
        """
        Check if lock is acquired by this instance.

        Returns:
            True if this instance holds the lock
        """
        return self._acquired

    async def __aenter__(self):
        """Context manager entry - acquire lock."""
        await self.acquire(blocking=True)
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager exit - release lock."""
        if self._acquired:
            await self.release()
        return False


@asynccontextmanager
async def distributed_lock(
    redis_client: Any,
    lock_key: str,
    ttl: int = 30,
    blocking: bool = True,
    timeout: float | None = None,
):
    """
    Async context manager for distributed lock (convenience function).

    Args:
        redis_client: Redis client instance
        lock_key: Unique key for the lock
        ttl: Lock expiration time in seconds
        blocking: Wait until lock is acquired
        timeout: Maximum wait time in seconds (None = wait forever)

    Yields:
        DistributedLock instance

    Example:
        async with distributed_lock(redis, "index_job:repo123", ttl=60) as lock:
            # Critical section
            await index_repository()
    """
    lock = DistributedLock(redis_client, lock_key, ttl=ttl)

    acquired = await lock.acquire(blocking=blocking, timeout=timeout)

    if not acquired:
        raise LockAcquisitionError(f"Failed to acquire lock: {lock_key}")

    try:
        yield lock
    finally:
        if lock.is_acquired():
            await lock.release()
