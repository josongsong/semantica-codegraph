"""
Soft Lock Manager (SOTA급)

여러 Agent의 파일 편집을 추적하고 충돌을 방지합니다.

핵심 기능:
1. Soft Lock 획득/해제
2. 충돌 감지
3. Hash Drift 감지
4. Redis 기반 실시간 Lock
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.orchestrator.orchestrator.domain.multi_agent_models import (
    Conflict,
    ConflictType,
    DriftDetectionResult,
    LockAcquisitionResult,
    LockType,
    SoftLock,
)

logger = logging.getLogger(__name__)


class SoftLockManager:
    """
    Soft Lock Manager (SOTA급).

    Redis를 사용한 분산 Lock 관리.
    """

    # 클래스 변수로 메모리 Lock 공유 (여러 인스턴스에서도 공유)
    _shared_memory_locks: dict[str, SoftLock] = {}

    def __init__(self, redis_client=None, deadlock_detector=None):
        """
        Args:
            redis_client: Redis 클라이언트 (선택)
            deadlock_detector: Deadlock 감지기 (선택)
        """
        self.redis_client = redis_client
        self.deadlock_detector = deadlock_detector

    async def acquire_lock(
        self,
        agent_id: str,
        file_path: str,
        lock_type: LockType = LockType.WRITE,
    ) -> LockAcquisitionResult:
        """
        Lock 획득.

        Args:
            agent_id: Agent ID
            file_path: 파일 경로
            lock_type: Lock 타입

        Returns:
            LockAcquisitionResult
        """
        logger.debug(f"Acquiring lock: agent={agent_id}, file={file_path}")

        try:
            # 기존 Lock 확인
            existing_lock = await self.get_lock(file_path)

            if existing_lock:
                # 같은 Agent면 허용
                if existing_lock.agent_id == agent_id:
                    logger.debug(f"Lock already held by same agent: {agent_id}")
                    return LockAcquisitionResult(
                        success=True,
                        lock=existing_lock,
                        message="Lock already held by same agent",
                    )

                # 다른 Agent → 충돌
                logger.warning(f"Lock conflict: {file_path} locked by {existing_lock.agent_id}")

                conflict = Conflict(
                    conflict_id=f"conflict-{datetime.now().timestamp()}",
                    file_path=file_path,
                    agent_a_id=agent_id,
                    agent_b_id=existing_lock.agent_id,
                    conflict_type=ConflictType.CONCURRENT_EDIT,
                )

                return LockAcquisitionResult(
                    success=False,
                    existing_lock=existing_lock,
                    conflict=conflict,
                    message=f"File locked by {existing_lock.agent_id}",
                )

            # Lock 생성
            file_hash = await self._calculate_file_hash(file_path)

            lock = SoftLock(
                file_path=file_path,
                agent_id=agent_id,
                file_hash=file_hash,
                lock_type=lock_type,
            )

            # 저장
            await self._store_lock(lock)

            logger.info(f"Lock acquired: agent={agent_id}, file={file_path}")

            return LockAcquisitionResult(
                success=True,
                lock=lock,
                message="Lock acquired",
            )

        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return LockAcquisitionResult(
                success=False,
                message=f"Error: {e}",
            )

    async def release_lock(
        self,
        agent_id: str,
        file_path: str,
    ) -> bool:
        """
        Lock 해제.

        Args:
            agent_id: Agent ID
            file_path: 파일 경로

        Returns:
            성공 여부
        """
        logger.debug(f"Releasing lock: agent={agent_id}, file={file_path}")

        try:
            # 기존 Lock 확인
            existing_lock = await self.get_lock(file_path)

            if not existing_lock:
                logger.warning(f"No lock to release: {file_path}")
                return False

            # 소유권 확인
            if existing_lock.agent_id != agent_id:
                logger.error(f"Cannot release lock held by {existing_lock.agent_id}")
                return False

            # 삭제
            await self._delete_lock(file_path)

            logger.info(f"Lock released: agent={agent_id}, file={file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
            return False

    async def acquire_locks_ordered(
        self,
        agent_id: str,
        file_paths: list[str],
        lock_type: LockType = LockType.WRITE,
        timeout: float = 30.0,
    ) -> tuple[bool, list[str], list[str]]:
        """
        여러 파일 Lock (알파벳 순서 강제 - Deadlock 방지)

        Algorithm:
        1. 파일 경로 정렬 (알파벳 순서)
        2. 순서대로 Lock 획득
        3. 실패 시 이미 획득한 Lock 모두 해제 (Rollback)

        Deadlock Prevention:
        - 모든 Agent가 같은 순서로 Lock 획득 → Deadlock 불가능
        - Two-Phase Locking (2PL)

        Args:
            agent_id: Agent ID
            file_paths: 파일 경로 리스트
            lock_type: Lock 타입
            timeout: 전체 타임아웃 (초)

        Returns:
            (success, acquired_files, failed_files)

        Raises:
            ValueError: Empty file_paths
            TimeoutError: Timeout 초과

        Examples:
            >>> success, acquired, failed = await lock_manager.acquire_locks_ordered(
            ...     agent_id="agent-1",
            ...     file_paths=["utils.py", "main.py"],  # 순서 무관
            ...     timeout=30.0,
            ... )
            >>> # 내부적으로 ["main.py", "utils.py"] 순서로 획득 (알파벳)
        """
        if not file_paths:
            raise ValueError("file_paths cannot be empty")

        import time as time_module

        # 🔥 알파벳 순서로 정렬 (Deadlock 방지)
        sorted_files = sorted(set(file_paths))

        logger.info(
            f"Acquiring {len(sorted_files)} locks in order",
            extra={
                "agent": agent_id,
                "files": sorted_files[:5] if len(sorted_files) <= 5 else sorted_files[:5] + ["..."],
            },
        )

        acquired = []
        start_time = time_module.time()

        try:
            for file_path in sorted_files:
                # Timeout 체크
                elapsed = time_module.time() - start_time
                if elapsed > timeout:
                    logger.error(
                        f"Lock acquisition timeout: {elapsed:.1f}s",
                        extra={
                            "agent": agent_id,
                            "acquired": len(acquired),
                            "target": len(sorted_files),
                        },
                    )

                    # Rollback
                    await self._release_locks_ordered(agent_id, acquired)

                    raise TimeoutError(f"Lock acquisition timeout: {elapsed:.1f}s")

                # Lock 획득 시도
                result = await self.acquire_lock(
                    agent_id=agent_id,
                    file_path=file_path,
                    lock_type=lock_type,
                )

                if not result.success:
                    # 실패 - Rollback
                    logger.warning(
                        f"Lock failed: {file_path}, rolling back {len(acquired)} locks",
                        extra={"agent": agent_id},
                    )

                    await self._release_locks_ordered(agent_id, acquired)

                    return False, [], sorted_files

                acquired.append(file_path)

            # 모두 성공
            logger.info(
                f"All locks acquired: {len(acquired)} files",
                extra={
                    "agent": agent_id,
                    "elapsed": f"{time_module.time() - start_time:.3f}s",
                },
            )

            return True, acquired, []

        except TimeoutError:
            # Timeout → Rollback
            await self._release_locks_ordered(agent_id, acquired)
            raise

        except Exception as e:
            logger.error(
                f"Lock acquisition error: {e}",
                extra={"agent": agent_id},
                exc_info=True,
            )

            # Rollback
            await self._release_locks_ordered(agent_id, acquired)

            return False, [], sorted_files

    async def _release_locks_ordered(
        self,
        agent_id: str,
        file_paths: list[str],
    ):
        """
        여러 Lock 해제 (역순 - LIFO)

        Algorithm:
        - 획득 역순으로 해제
        - 에러 무시 (best effort)

        Args:
            agent_id: Agent ID
            file_paths: 파일 경로 리스트

        Thread-Safety: release_lock()이 개별 보호
        """
        for file_path in reversed(file_paths):
            try:
                await self.release_lock(agent_id, file_path)
            except Exception as e:
                logger.warning(f"Failed to release lock: {file_path}, {e}")

    async def renew_lock(
        self,
        agent_id: str,
        file_path: str,
    ) -> bool:
        """
        Lock TTL 갱신 (Keep-alive용)

        Algorithm:
        1. Lock 조회
        2. 소유권 확인
        3. acquired_at 갱신
        4. 재저장 (Redis TTL 연장)

        Args:
            agent_id: Agent ID
            file_path: 파일 경로

        Returns:
            성공 여부

        Thread-Safety: get_lock(), _store_lock()이 보호

        Examples:
            >>> success = await lock_manager.renew_lock("agent-1", "main.py")
            >>> if not success:
            ...     logger.error("Lock renewal failed")
        """
        try:
            # Lock 조회
            lock = await self.get_lock(file_path)

            if not lock:
                logger.debug(f"Lock not found (expired?): {file_path}")
                return False

            # 소유권 확인
            if lock.agent_id != agent_id:
                logger.warning(
                    f"Cannot renew lock owned by {lock.agent_id}",
                    extra={"agent": agent_id, "file": file_path},
                )
                return False

            # 🔥 acquired_at 갱신 (Immutable 위반하지만 필요)
            # NOTE: SoftLock은 mutable (frozen=False)
            from datetime import datetime

            lock.acquired_at = datetime.now()

            # 재저장 (Redis TTL 자동 연장)
            await self._store_lock(lock)

            logger.debug(f"Lock renewed: {agent_id}, file={file_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to renew lock: {file_path}, {e}")
            return False

    async def get_lock(self, file_path: str) -> SoftLock | None:
        """
        Lock 조회.

        Args:
            file_path: 파일 경로

        Returns:
            SoftLock or None
        """
        try:
            if self.redis_client:
                # Redis에서 조회
                lock_data = await self._get_from_redis(file_path)

                if lock_data:
                    lock = SoftLock.from_dict(lock_data)

                    # 만료 확인
                    if lock.is_expired():
                        logger.warning(f"Lock expired: {file_path}")
                        await self._delete_lock(file_path)
                        return None

                    return lock
            else:
                # 메모리에서 조회 (클래스 변수 사용)
                lock = SoftLockManager._shared_memory_locks.get(file_path)

                if lock and lock.is_expired():
                    logger.warning(f"Lock expired: {file_path}")
                    del SoftLockManager._shared_memory_locks[file_path]
                    return None

                return lock

        except Exception as e:
            logger.error(f"Failed to get lock: {e}")
            return None

    async def check_lock(self, file_path: str) -> bool:
        """
        Lock 존재 여부 확인.

        Args:
            file_path: 파일 경로

        Returns:
            Lock 존재 여부
        """
        lock = await self.get_lock(file_path)
        return lock is not None

    async def detect_drift(
        self,
        file_path: str,
    ) -> DriftDetectionResult:
        """
        Hash Drift 감지.

        파일이 Lock 시점 이후 변경되었는지 확인합니다.

        Args:
            file_path: 파일 경로

        Returns:
            DriftDetectionResult
        """
        logger.debug(f"Detecting drift: {file_path}")

        try:
            # Lock 조회
            lock = await self.get_lock(file_path)

            if not lock:
                return DriftDetectionResult(
                    drift_detected=False,
                    file_path=file_path,
                    message="No lock exists",
                )

            # 현재 파일 hash
            current_hash = await self._calculate_file_hash(file_path)

            # 비교
            if current_hash != lock.file_hash:
                logger.warning(f"Hash drift detected: {file_path}")
                logger.debug(f"  Original: {lock.file_hash}")
                logger.debug(f"  Current:  {current_hash}")

                return DriftDetectionResult(
                    drift_detected=True,
                    file_path=file_path,
                    original_hash=lock.file_hash,
                    current_hash=current_hash,
                    lock_info=lock,
                    message="Hash drift detected",
                )

            return DriftDetectionResult(
                drift_detected=False,
                file_path=file_path,
                original_hash=lock.file_hash,
                current_hash=current_hash,
                lock_info=lock,
                message="No drift",
            )

        except Exception as e:
            logger.error(f"Failed to detect drift: {e}")
            return DriftDetectionResult(
                drift_detected=False,
                file_path=file_path,
                message=f"Error: {e}",
            )

    async def list_locks(self) -> list[SoftLock]:
        """
        모든 Lock 조회.

        Returns:
            Lock 리스트
        """
        try:
            if self.redis_client:
                # 🔥 Redis SCAN 구현 (SOTA)
                locks = []
                cursor = 0

                # SCAN iteration (1000개씩)
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor=cursor,
                        match="lock:*",
                        count=1000,
                    )

                    # 각 key의 Lock 조회
                    for key in keys:
                        lock_data = await self.redis_client.get(key)

                        if lock_data:
                            try:
                                lock = SoftLock.from_dict(lock_data)

                                # 만료 체크
                                if not lock.is_expired():
                                    locks.append(lock)
                                else:
                                    # 만료된 Lock 삭제
                                    await self.redis_client.delete(key)

                            except Exception as e:
                                logger.warning(f"Invalid lock data: {key}, {e}")

                    # Cursor 0 → 완료
                    if cursor == 0:
                        break

                logger.debug(f"Listed {len(locks)} locks from Redis")
                return locks
            else:
                # 메모리에서 조회 (클래스 변수 사용)
                # 만료된 것 제거
                expired_keys = [fp for fp, lock in SoftLockManager._shared_memory_locks.items() if lock.is_expired()]
                for key in expired_keys:
                    del SoftLockManager._shared_memory_locks[key]

                return list(SoftLockManager._shared_memory_locks.values())

        except Exception as e:
            logger.error(f"Failed to list locks: {e}")
            return []

    async def _store_lock(self, lock: SoftLock) -> None:
        """Lock 저장 (Redis or 메모리)"""
        if self.redis_client:
            await self._store_to_redis(lock)
        else:
            # 클래스 변수 사용 (여러 인스턴스 간 공유)
            SoftLockManager._shared_memory_locks[lock.file_path] = lock

    async def _delete_lock(self, file_path: str) -> None:
        """Lock 삭제"""
        if self.redis_client:
            await self._delete_from_redis(file_path)
        else:
            SoftLockManager._shared_memory_locks.pop(file_path, None)

    async def _calculate_file_hash(self, file_path: str) -> str:
        """파일 hash 계산"""
        try:
            path = Path(file_path)

            if not path.exists():
                return "nonexistent"

            content = path.read_bytes()
            return hashlib.sha256(content).hexdigest()

        except Exception as e:
            logger.error(f"Failed to calculate hash: {e}")
            return "error"

    async def _store_to_redis(self, lock: SoftLock) -> None:
        """Redis에 저장"""
        if not self.redis_client:
            return

        key = f"lock:{lock.file_path}"
        value = lock.to_dict()

        # TTL과 함께 저장 (RedisAdapter.set 사용)
        await self.redis_client.set(key, json.dumps(value), ex=lock.ttl_seconds)

        logger.debug(f"Lock stored to Redis: {key}")

    async def _get_from_redis(self, file_path: str) -> dict[str, Any] | None:
        """Redis에서 조회"""
        if not self.redis_client:
            return None

        key = f"lock:{file_path}"
        data = await self.redis_client.get(key)

        if not data:
            return None

        # RedisAdapter.get()이 자동으로 JSON 파싱해서 dict로 반환
        # 추가 파싱 불필요
        logger.debug(f"Lock retrieved from Redis: {key}")
        return data

    async def _delete_from_redis(self, file_path: str) -> None:
        """Redis에서 삭제"""
        if not self.redis_client:
            return

        key = f"lock:{file_path}"
        await self.redis_client.delete(key)

        logger.debug(f"Lock deleted from Redis: {key}")
