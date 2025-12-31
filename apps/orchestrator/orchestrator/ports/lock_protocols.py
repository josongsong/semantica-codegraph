"""
Lock Manager Protocols (Hexagonal Architecture)

DIP 준수: Adapter에서 Protocol 분리

책임:
- Lock 관리 추상화
- Multi-agent concurrency 지원

SOLID:
- S: Lock 관리 Protocol만 정의
- O: 새 Lock 구현체 추가 용이
- L: Protocol 완벽히 구현 가능
- I: 최소한의 메서드만 정의
- D: 구체 구현에 의존하지 않음
"""

from typing import Protocol, runtime_checkable

# ============================================================================
# Lock Protocols
# ============================================================================


@runtime_checkable
class SoftLockProtocol(Protocol):
    """
    Soft Lock Protocol

    Lock 정보 인터페이스
    """

    agent_id: str
    file_path: str


@runtime_checkable
class LockAcquisitionResultProtocol(Protocol):
    """
    Lock Acquisition Result Protocol

    Lock 획득 결과 인터페이스
    """

    success: bool
    message: str
    existing_lock: SoftLockProtocol | None


@runtime_checkable
class LockManagerProtocol(Protocol):
    """
    Lock Manager Protocol

    Multi-agent Lock 관리 인터페이스

    Features:
    - Lock 획득/해제
    - Lock 조회
    - Timeout 지원

    구현체:
    - SoftLockManager (메모리 기반)
    - 향후: RedisLockManager, PostgresLockManager 등
    """

    async def acquire_lock(
        self,
        agent_id: str,
        file_path: str,
        lock_type: str,
    ) -> LockAcquisitionResultProtocol:
        """
        Lock 획득

        Args:
            agent_id: Agent ID
            file_path: 파일 경로
            lock_type: Lock 타입 (READ, WRITE)

        Returns:
            LockAcquisitionResultProtocol: Lock 획득 결과

        Raises:
            TimeoutError: Lock 타임아웃
        """
        ...

    async def release_lock(self, agent_id: str, file_path: str) -> bool:
        """
        Lock 해제

        Args:
            agent_id: Agent ID
            file_path: 파일 경로

        Returns:
            bool: 해제 성공 여부
        """
        ...

    async def get_lock(self, file_path: str) -> SoftLockProtocol | None:
        """
        Lock 조회

        Args:
            file_path: 파일 경로

        Returns:
            SoftLockProtocol | None: Lock 정보 (없으면 None)
        """
        ...

    async def acquire_locks_ordered(
        self,
        agent_id: str,
        file_paths: list[str],
        lock_type: str,
        timeout: float = 30.0,
    ) -> tuple[bool, list[str], list[str]]:
        """
        여러 파일 Lock (순서 보장 - Deadlock 방지)

        Args:
            agent_id: Agent ID
            file_paths: 파일 경로 리스트
            lock_type: Lock 타입
            timeout: Timeout (초)

        Returns:
            (success, acquired_files, failed_files)
        """
        ...

    async def renew_lock(self, agent_id: str, file_path: str) -> bool:
        """
        Lock TTL 갱신

        Args:
            agent_id: Agent ID
            file_path: 파일 경로

        Returns:
            성공 여부
        """
        ...


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "LockManagerProtocol",
    "LockAcquisitionResultProtocol",
    "SoftLockProtocol",
]
