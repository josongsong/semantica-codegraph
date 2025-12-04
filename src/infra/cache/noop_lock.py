"""
No-Op Lock Implementation

테스트 및 단일 프로세스 환경용 Lock 구현.
실제 Lock을 사용하지 않고 즉시 통과합니다.
"""

from typing import Any


class NoOpLock:
    """
    No-operation lock for single-process environments.

    항상 즉시 획득 성공하고 아무 작업도 하지 않습니다.
    테스트 환경이나 단일 프로세스 배포에서 Lock overhead를 제거합니다.

    Usage:
        # DistributedLock과 동일한 인터페이스
        lock = NoOpLock(redis_client, "key", ttl=30)
        acquired = await lock.acquire()  # 항상 True
        await lock.release()  # 아무것도 안 함
    """

    def __init__(
        self,
        redis_client: Any = None,
        lock_key: str = "",
        ttl: int = 30,
        **kwargs,
    ):
        """
        Initialize no-op lock.

        Args:
            redis_client: Ignored (호환성용)
            lock_key: Ignored (호환성용)
            ttl: Ignored (호환성용)
            **kwargs: Additional arguments (ignored)
        """
        self.lock_key = f"noop:{lock_key}"
        self.lock_id = "noop"
        self._acquired = False

    async def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """
        Acquire lock (always succeeds immediately).

        Args:
            blocking: Ignored
            timeout: Ignored

        Returns:
            Always True
        """
        self._acquired = True
        return True

    async def release(self) -> bool:
        """
        Release lock (no-op).

        Returns:
            Always True
        """
        self._acquired = False
        return True

    async def extend(self, additional_ttl: int = 0) -> bool:
        """
        Extend lock TTL (no-op).

        Args:
            additional_ttl: Ignored (optional)

        Returns:
            Always True
        """
        return True

    def is_acquired(self) -> bool:
        """Check if lock is acquired."""
        return self._acquired

    async def __aenter__(self):
        """Context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.release()
        return False
