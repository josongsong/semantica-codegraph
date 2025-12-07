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

from src.agent.domain.multi_agent_models import (
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

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: Redis 클라이언트 (선택)
        """
        self.redis_client = redis_client

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
                # Redis에서 모든 Lock 조회
                # TODO: Redis scan 구현
                return []
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
