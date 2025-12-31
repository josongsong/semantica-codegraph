"""
Incremental Orchestrator (RFC-045)

ShadowFS 이벤트 기반 증분 업데이트 조율

책임:
- ShadowFS "commit" 이벤트 수신
- 변경된 파일 수집
- IncrementalIRBuilder 호출
- 인덱스 업데이트 트리거

Event Flow:
    ShadowFS.commit() → EventBus.emit() → IncrementalOrchestrator.on_event()
                                          → IncrementalIRBuilder.build_incremental()
                                          → IndexService.update()
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


# ============================================================================
# Ports (DIP - Dependency Inversion)
# ============================================================================


class IIndexUpdater(Protocol):
    """인덱스 업데이트 Port"""

    async def update_ir(
        self,
        file_path: str,
        ir_document: object,  # IRDocument
    ) -> bool:
        """
        IR 문서를 인덱스에 반영

        Args:
            file_path: 파일 경로
            ir_document: 새 IR 문서

        Returns:
            성공 여부
        """
        ...

    async def remove_file(self, file_path: str) -> bool:
        """
        파일을 인덱스에서 제거

        Args:
            file_path: 삭제된 파일 경로

        Returns:
            성공 여부
        """
        ...


# ============================================================================
# Domain Models
# ============================================================================


@dataclass
class PendingChange:
    """보류 중인 변경"""

    file_path: str
    new_content: str | None  # None이면 삭제
    old_content: str | None
    txn_id: str


@dataclass
class UpdateResult:
    """업데이트 결과"""

    success: bool
    updated_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ============================================================================
# Orchestrator
# ============================================================================


class IncrementalOrchestrator:
    """
    Incremental Update Orchestrator

    ShadowFS EventBus의 Plugin으로 등록되어 이벤트 수신

    Usage:
        from codegraph_runtime.codegen_loop.infrastructure.shadowfs.event_bus import EventBus

        event_bus = EventBus()
        orchestrator = IncrementalOrchestrator(
            repo_id="my-repo",
            workspace_root=Path("/path/to/repo"),
            index_updater=my_index_service,
        )
        event_bus.register(orchestrator)

    Event Handling:
        - "write": 변경 수집 (커밋 전)
        - "delete": 삭제 수집 (커밋 전)
        - "commit": 실제 증분 업데이트 실행
        - "rollback": 수집된 변경 폐기
    """

    def __init__(
        self,
        repo_id: str,
        workspace_root: Path,
        index_updater: IIndexUpdater | None = None,
    ):
        """
        Args:
            repo_id: 리포지토리 ID
            workspace_root: 워크스페이스 루트 경로
            index_updater: 인덱스 업데이트 어댑터 (Optional)
        """
        self._repo_id = repo_id
        self._workspace_root = workspace_root
        self._index_updater = index_updater

        # Lazy import to avoid circular dependency
        self._builder: "IncrementalIRBuilder | None" = None

        # Transaction별 보류 변경 {txn_id: [PendingChange]}
        self._pending: dict[str, list[PendingChange]] = {}

    async def on_event(self, event: object) -> None:
        """
        ShadowFS 이벤트 핸들러

        EventBus.register()로 등록 시 호출됨

        Args:
            event: ShadowFSEvent (duck typing)
        """
        # Duck typing for ShadowFSEvent
        event_type = getattr(event, "type", None)
        if event_type is None:
            return

        txn_id = getattr(event, "txn_id", "")
        path = getattr(event, "path", "")

        if event_type == "write":
            await self._on_write(
                txn_id=txn_id,
                path=path,
                new_content=getattr(event, "new_content", ""),
                old_content=getattr(event, "old_content", None),
            )

        elif event_type == "delete":
            await self._on_delete(
                txn_id=txn_id,
                path=path,
                old_content=getattr(event, "old_content", None),
            )

        elif event_type == "commit":
            await self._on_commit(txn_id=txn_id)

        elif event_type == "rollback":
            await self._on_rollback(txn_id=txn_id)

    async def _on_write(
        self,
        txn_id: str,
        path: str,
        new_content: str,
        old_content: str | None,
    ) -> None:
        """파일 쓰기 이벤트 - 변경 수집"""
        if txn_id not in self._pending:
            self._pending[txn_id] = []

        self._pending[txn_id].append(
            PendingChange(
                file_path=path,
                new_content=new_content,
                old_content=old_content,
                txn_id=txn_id,
            )
        )

        logger.debug(f"Collected write: {path} (txn={txn_id})")

    async def _on_delete(
        self,
        txn_id: str,
        path: str,
        old_content: str | None,
    ) -> None:
        """파일 삭제 이벤트 - 삭제 수집"""
        if txn_id not in self._pending:
            self._pending[txn_id] = []

        self._pending[txn_id].append(
            PendingChange(
                file_path=path,
                new_content=None,  # 삭제
                old_content=old_content,
                txn_id=txn_id,
            )
        )

        logger.debug(f"Collected delete: {path} (txn={txn_id})")

    async def _on_commit(self, txn_id: str) -> None:
        """커밋 이벤트 - 증분 업데이트 실행"""
        if txn_id not in self._pending:
            logger.debug(f"No pending changes for txn={txn_id}")
            return

        changes = self._pending.pop(txn_id)
        if not changes:
            return

        logger.info(f"Processing {len(changes)} changes (txn={txn_id})")

        result = await self._process_changes(changes)

        if result.success:
            logger.info(
                f"Incremental update success: {len(result.updated_files)} updated, {len(result.skipped_files)} skipped"
            )
        else:
            logger.error(f"Incremental update failed: {result.errors}")

    async def _on_rollback(self, txn_id: str) -> None:
        """롤백 이벤트 - 수집된 변경 폐기"""
        if txn_id in self._pending:
            count = len(self._pending.pop(txn_id))
            logger.info(f"Discarded {count} pending changes (txn={txn_id})")

    async def _process_changes(
        self,
        changes: list[PendingChange],
    ) -> UpdateResult:
        """
        변경사항 처리

        1. IR 재빌드 (IncrementalIRBuilder)
        2. 인덱스 업데이트 (IIndexUpdater)
        """
        result = UpdateResult(success=True)

        # Lazy initialize builder
        if self._builder is None:
            from codegraph_engine.code_foundation.infrastructure.incremental.incremental_builder import (
                IncrementalIRBuilder,
            )

            self._builder = IncrementalIRBuilder(
                repo_id=self._repo_id,
                workspace_root=self._workspace_root,
            )

        # Separate writes and deletes
        writes = [c for c in changes if c.new_content is not None]
        deletes = [c for c in changes if c.new_content is None]

        # Process writes
        if writes:
            # Convert paths to Path objects
            file_paths = []
            for change in writes:
                file_path = self._workspace_root / change.file_path
                file_paths.append(file_path)

            try:
                build_result = self._builder.build_incremental(file_paths)

                # Update index
                if self._index_updater:
                    for file_path, ir_doc in build_result.ir_documents.items():
                        try:
                            await self._index_updater.update_ir(file_path, ir_doc)
                            result.updated_files.append(file_path)
                        except Exception as e:
                            result.failed_files.append(file_path)
                            result.errors.append(f"{file_path}: {e}")
                else:
                    result.updated_files.extend(build_result.rebuilt_files)

                result.skipped_files.extend(
                    f for f in build_result.changed_files if f not in build_result.rebuilt_files
                )

            except Exception as e:
                result.success = False
                result.errors.append(f"Build failed: {e}")

        # Process deletes
        for change in deletes:
            file_path = str(self._workspace_root / change.file_path)

            if self._index_updater:
                try:
                    await self._index_updater.remove_file(file_path)
                    result.updated_files.append(file_path)
                except Exception as e:
                    result.failed_files.append(file_path)
                    result.errors.append(f"{file_path}: {e}")

        if result.failed_files:
            result.success = False

        return result

    def get_pending_count(self, txn_id: str) -> int:
        """트랜잭션의 보류 변경 수"""
        return len(self._pending.get(txn_id, []))

    def clear_all_pending(self) -> None:
        """모든 보류 변경 제거 (테스트용)"""
        self._pending.clear()
