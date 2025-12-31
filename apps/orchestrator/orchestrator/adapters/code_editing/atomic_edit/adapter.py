"""
Atomic Edit Adapter (SOTA급)

Port: AtomicEditPort
Technology: LockManagerProtocol

책임:
- Multi-file atomic transaction
- Hash-based conflict detection
- Rollback (Snapshot 기반)
- Multi-agent concurrency (LockManagerProtocol)

SOLID 원칙:
- S: Atomic edit 실행만 담당 (트랜잭션 오케스트레이션)
- O: 새 IsolationLevel 추가 시 기존 코드 수정 불필요
- L: AtomicEditPort 완벽히 구현
- I: 3개 메서드만 (execute, rollback, check_conflicts)
- D: LockManagerProtocol 주입 (DIP)

Hexagonal:
- Port: AtomicEditPort (code_editing.py)
- Adapter: 이 파일
- Domain: atomic_edit/models.py
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from apps.orchestrator.orchestrator.domain.code_editing import (
    AtomicEditRequest,
    AtomicEditResult,
    ConflictInfo,
    ConflictType,
    IsolationLevel,
    RollbackInfo,
    TransactionState,
)
from apps.orchestrator.orchestrator.domain.code_editing.utils import compute_content_hash
from apps.orchestrator.orchestrator.ports.lock_protocols import LockManagerProtocol

logger = logging.getLogger(__name__)


# ============================================================================
# Atomic Edit Adapter
# ============================================================================


class AtomicEditAdapter:
    """
    Atomic Edit Adapter (SOTA급)

    AtomicEditPort 구현체

    Features:
    - Multi-file atomic transaction (all-or-nothing)
    - Hash-based conflict detection (optimistic locking)
    - Rollback support (snapshot-based)
    - Multi-agent concurrency (SoftLockManager)
    - Isolation levels (READ_UNCOMMITTED, READ_COMMITTED, SERIALIZABLE)
    - Dry-run mode (preview without changes)
    - Timeout support

    Usage:
        adapter = AtomicEditAdapter(lock_manager, "/workspace")
        result = await adapter.execute(request)

        if not result.success:
            # 충돌 발생 - rollback 가능
            if result.rollback_info:
                await adapter.rollback(result.rollback_info.rollback_id)
    """

    def __init__(
        self,
        lock_manager: LockManagerProtocol,
        workspace_root: str,
    ):
        """
        Args:
            lock_manager: SoftLockManager (multi-agent 지원)
            workspace_root: Workspace 루트 경로
        """
        self.lock_manager = lock_manager
        self._workspace_root = Path(workspace_root)

        # Rollback 저장소 (메모리 - 필요시 Redis로 확장)
        self._rollback_store: dict[str, RollbackInfo] = {}

        logger.info(f"AtomicEditAdapter initialized: workspace={workspace_root}")

    # ========================================================================
    # Public API (AtomicEditPort)
    # ========================================================================

    async def execute(self, request: AtomicEditRequest) -> AtomicEditResult:
        """
        Atomic edit 실행

        Transaction 순서:
        1. Conflict 사전 체크 (isolation_level에 따라)
        2. Lock 획득 (SERIALIZABLE인 경우)
        3. Hash 검증 (optimistic locking)
        4. Snapshot 생성 (rollback용)
        5. 파일 변경 적용
        6. Lock 해제

        Args:
            request: Atomic edit 요청

        Returns:
            AtomicEditResult: 실행 결과

        Raises:
            ValueError: Invalid request
            TimeoutError: Lock timeout
            RuntimeError: Transaction failed
        """
        start_time = time.perf_counter()
        acquired_locks: list[str] = []
        rollback_info: RollbackInfo | None = None

        try:
            logger.info(
                f"Execute atomic edit: "
                f"agent={request.agent_id}, "
                f"files={request.file_count}, "
                f"isolation={request.isolation_level.value}, "
                f"dry_run={request.dry_run}"
            )

            # Step 1: Conflict 사전 체크
            conflicts = await self._check_conflicts_internal(request)
            if conflicts:
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return AtomicEditResult(
                    success=False,
                    transaction_state=TransactionState.FAILED,
                    committed_files=[],
                    conflicts=conflicts,
                    errors=[f"Conflicts detected: {len(conflicts)} files"],
                    execution_time_ms=execution_time_ms,
                )

            # Step 2: Lock 획득 (SERIALIZABLE인 경우)
            if request.isolation_level == IsolationLevel.SERIALIZABLE:
                lock_result = await self._acquire_locks(request)
                if not lock_result["success"]:
                    execution_time_ms = (time.perf_counter() - start_time) * 1000
                    return AtomicEditResult(
                        success=False,
                        transaction_state=TransactionState.FAILED,
                        committed_files=[],
                        conflicts=lock_result["conflicts"],
                        errors=["Lock acquisition failed"],
                        execution_time_ms=execution_time_ms,
                    )
                acquired_locks = lock_result["acquired_locks"]

            # Step 3: Hash 검증 (optimistic locking)
            hash_conflicts = await self._verify_hashes(request)
            if hash_conflicts:
                await self._release_locks(request.agent_id, acquired_locks)
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return AtomicEditResult(
                    success=False,
                    transaction_state=TransactionState.FAILED,
                    committed_files=[],
                    conflicts=hash_conflicts,
                    errors=["Hash mismatch - file was modified"],
                    execution_time_ms=execution_time_ms,
                )

            # Dry-run이면 여기서 종료
            if request.dry_run:
                await self._release_locks(request.agent_id, acquired_locks)
                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return AtomicEditResult(
                    success=True,
                    transaction_state=TransactionState.COMMITTED,
                    committed_files=[edit.file_path for edit in request.edits],
                    execution_time_ms=execution_time_ms,
                )

            # Step 4: Snapshot 생성 (rollback용)
            rollback_info = await self._create_snapshot(request)

            # Step 5: 파일 변경 적용
            try:
                await self._apply_changes(request)
            except Exception as apply_error:
                # 실패 시 즉시 rollback
                logger.error(f"Apply failed, rolling back: {apply_error}")
                await self._restore_snapshot(rollback_info)
                await self._release_locks(request.agent_id, acquired_locks)

                execution_time_ms = (time.perf_counter() - start_time) * 1000
                return AtomicEditResult(
                    success=False,
                    transaction_state=TransactionState.ROLLED_BACK,
                    committed_files=[],
                    rollback_info=rollback_info,
                    errors=[f"Apply failed: {apply_error}"],
                    execution_time_ms=execution_time_ms,
                )

            # Step 6: Lock 해제
            await self._release_locks(request.agent_id, acquired_locks)

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Atomic edit complete: files={request.file_count}, time={execution_time_ms:.1f}ms")

            return AtomicEditResult(
                success=True,
                transaction_state=TransactionState.COMMITTED,
                committed_files=[edit.file_path for edit in request.edits],
                rollback_info=rollback_info,  # 성공 후에도 rollback 가능
                execution_time_ms=execution_time_ms,
            )

        except asyncio.TimeoutError:
            await self._release_locks(request.agent_id, acquired_locks)
            if rollback_info:
                await self._restore_snapshot(rollback_info)

            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return AtomicEditResult(
                success=False,
                transaction_state=TransactionState.FAILED,
                committed_files=[],
                rollback_info=rollback_info,
                errors=[f"Timeout after {request.timeout_seconds}s"],
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            logger.error(f"Atomic edit failed: {e}")
            await self._release_locks(request.agent_id, acquired_locks)
            if rollback_info:
                await self._restore_snapshot(rollback_info)

            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return AtomicEditResult(
                success=False,
                transaction_state=TransactionState.FAILED,
                committed_files=[],
                rollback_info=rollback_info,
                errors=[str(e)],
                execution_time_ms=execution_time_ms,
            )

    async def rollback(self, rollback_id: str) -> AtomicEditResult:
        """
        Rollback 실행

        Args:
            rollback_id: Rollback ID

        Returns:
            AtomicEditResult: Rollback 결과

        Raises:
            ValueError: Invalid rollback_id
            RuntimeError: Rollback failed
        """
        start_time = time.perf_counter()

        try:
            logger.info(f"Rollback: {rollback_id}")

            # Rollback 정보 조회
            rollback_info = self._rollback_store.get(rollback_id)
            if not rollback_info:
                raise ValueError(f"Rollback not found: {rollback_id}")

            # 스냅샷 복원
            await self._restore_snapshot(rollback_info)

            # Rollback 정보 삭제
            del self._rollback_store[rollback_id]

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(f"Rollback complete: files={rollback_info.file_count}, time={execution_time_ms:.1f}ms")

            return AtomicEditResult(
                success=True,
                transaction_state=TransactionState.COMMITTED,
                committed_files=list(rollback_info.original_state.keys()),
                rollback_info=rollback_info,
                execution_time_ms=execution_time_ms,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            execution_time_ms = (time.perf_counter() - start_time) * 1000
            return AtomicEditResult(
                success=False,
                transaction_state=TransactionState.FAILED,
                committed_files=[],
                errors=[str(e)],
                execution_time_ms=execution_time_ms,
            )

    async def check_conflicts(self, request: AtomicEditRequest) -> list[str]:
        """
        충돌 사전 체크 (dry-run)

        Args:
            request: Atomic edit 요청

        Returns:
            list[str]: 충돌 파일 목록 (빈 리스트면 충돌 없음)

        Raises:
            ValueError: Invalid request
        """
        conflicts = await self._check_conflicts_internal(request)
        return [c.file_path for c in conflicts]

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _check_conflicts_internal(self, request: AtomicEditRequest) -> list[ConflictInfo]:
        """내부 충돌 체크 (ConflictInfo 반환)"""
        conflicts: list[ConflictInfo] = []

        for edit in request.edits:
            # 파일 존재 확인
            file = self._resolve_path(edit.file_path)
            if not file.exists():
                conflicts.append(
                    ConflictInfo(
                        file_path=edit.file_path,
                        conflict_type=ConflictType.FILE_DELETED,
                        message=f"File not found: {edit.file_path}",
                    )
                )
                continue

            # Lock 체크 (SERIALIZABLE인 경우)
            if request.isolation_level == IsolationLevel.SERIALIZABLE:
                existing_lock = await self.lock_manager.get_lock(edit.file_path)
                if existing_lock and existing_lock.agent_id != request.agent_id:
                    conflicts.append(
                        ConflictInfo(
                            file_path=edit.file_path,
                            conflict_type=ConflictType.LOCK_HELD,
                            locked_by=existing_lock.agent_id,
                            message=f"File locked by {existing_lock.agent_id}",
                        )
                    )

        return conflicts

    async def _acquire_locks(self, request: AtomicEditRequest) -> dict:
        """Lock 획득 (SERIALIZABLE)"""
        acquired_locks: list[str] = []
        conflicts: list[ConflictInfo] = []

        try:
            for edit in request.edits:
                # 타임아웃 적용
                result = await asyncio.wait_for(
                    self.lock_manager.acquire_lock(
                        agent_id=request.agent_id,
                        file_path=edit.file_path,
                        lock_type="WRITE",
                    ),
                    timeout=request.timeout_seconds,
                )

                if not result.success:
                    # Lock 실패 - 이미 획득한 Lock 해제
                    await self._release_locks(request.agent_id, acquired_locks)

                    if result.existing_lock:
                        conflicts.append(
                            ConflictInfo(
                                file_path=edit.file_path,
                                conflict_type=ConflictType.LOCK_HELD,
                                locked_by=result.existing_lock.agent_id,
                                message=result.message,
                            )
                        )

                    return {
                        "success": False,
                        "acquired_locks": [],
                        "conflicts": conflicts,
                    }

                acquired_locks.append(edit.file_path)

            return {
                "success": True,
                "acquired_locks": acquired_locks,
                "conflicts": [],
            }

        except asyncio.TimeoutError:
            await self._release_locks(request.agent_id, acquired_locks)
            raise

    async def _release_locks(self, agent_id: str, file_paths: list[str]) -> None:
        """Lock 해제"""
        for file_path in file_paths:
            try:
                await self.lock_manager.release_lock(agent_id, file_path)
            except Exception as e:
                logger.warning(f"Failed to release lock {file_path}: {e}")

    async def _verify_hashes(self, request: AtomicEditRequest) -> list[ConflictInfo]:
        """Hash 검증 (optimistic locking)"""
        conflicts: list[ConflictInfo] = []

        for edit in request.edits:
            # 파일 읽기
            file = self._resolve_path(edit.file_path)
            try:
                actual_content = file.read_text(encoding="utf-8")
            except FileNotFoundError:
                conflicts.append(
                    ConflictInfo(
                        file_path=edit.file_path,
                        conflict_type=ConflictType.FILE_DELETED,
                        message=f"File not found: {edit.file_path}",
                    )
                )
                continue

            if not edit.verify_hash(actual_content):
                actual_hash = compute_content_hash(actual_content, length=16)
                conflicts.append(
                    ConflictInfo(
                        file_path=edit.file_path,
                        conflict_type=ConflictType.HASH_MISMATCH,
                        expected_hash=edit.expected_hash,
                        actual_hash=actual_hash,
                        message="File was modified since request creation",
                    )
                )

        return conflicts

    async def _create_snapshot(self, request: AtomicEditRequest) -> RollbackInfo:
        """Snapshot 생성 (rollback용)"""
        original_state: dict[str, str] = {}

        for edit in request.edits:
            # 파일 읽기
            file = self._resolve_path(edit.file_path)
            if file.exists():
                original_state[edit.file_path] = file.read_text(encoding="utf-8")
            else:
                original_state[edit.file_path] = ""

        rollback_id = f"rollback-{uuid.uuid4().hex[:8]}"
        rollback_info = RollbackInfo(
            rollback_id=rollback_id,
            original_state=original_state,
            timestamp=datetime.now(),
            reason=f"Atomic edit by {request.agent_id}",
        )

        # 저장
        self._rollback_store[rollback_id] = rollback_info

        return rollback_info

    async def _restore_snapshot(self, rollback_info: RollbackInfo) -> None:
        """Snapshot 복원"""
        for file_path, content in rollback_info.original_state.items():
            file = self._resolve_path(file_path)
            if content:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8")
            else:
                # 원래 없던 파일은 삭제
                if file.exists():
                    file.unlink()

    async def _apply_changes(self, request: AtomicEditRequest) -> None:
        """파일 변경 적용"""
        for edit in request.edits:
            file = self._resolve_path(edit.file_path)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(edit.new_content, encoding="utf-8")

    def _resolve_path(self, file_path: str) -> Path:
        """파일 경로 resolve"""
        path = Path(file_path)
        if path.is_absolute():
            return path
        return self._workspace_root / file_path
