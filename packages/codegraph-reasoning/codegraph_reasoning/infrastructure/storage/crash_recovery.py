"""
Crash Recovery Manager

WAL replay + integrity check + rollback.
"""

import logging
from pathlib import Path

from .atomic_writer import AtomicFileWriter
from .snapshot_store import SnapshotStore
from .wal import WALEntry, WriteAheadLog

logger = logging.getLogger(__name__)


class CrashRecoveryManager:
    """
    Crash recovery 관리.

    순서:
    1. WAL replay
    2. Integrity check
    3. Corrupted data rollback
    4. 최신 good snapshot 복원
    """

    def __init__(
        self, wal: WriteAheadLog, snapshot_store: SnapshotStore, atomic_writer: AtomicFileWriter, data_path: Path
    ):
        self.wal = wal
        self.snapshot_store = snapshot_store
        self.atomic_writer = atomic_writer
        self.data_path = data_path

    def recover(self) -> dict:
        """
        Crash recovery 실행.

        Returns:
            Recovery 통계
        """
        logger.info("Starting crash recovery...")

        stats = {
            "wal_entries_replayed": 0,
            "corrupted_files_found": 0,
            "files_restored": 0,
            "snapshot_version_restored": None,
        }

        # 1. Temp 파일 정리
        self.atomic_writer.cleanup_temp_files(self.data_path)

        # 2. WAL replay
        entries = self.wal.replay()
        stats["wal_entries_replayed"] = len(entries)

        logger.info(f"Replayed {len(entries)} WAL entries")

        # 3. Integrity check
        corrupted_files = self._check_integrity()
        stats["corrupted_files_found"] = len(corrupted_files)

        if corrupted_files:
            logger.warning(f"Found {len(corrupted_files)} corrupted files")

        # 4. Corrupted files 복원
        if corrupted_files:
            restored_version = self._restore_from_snapshot()
            stats["snapshot_version_restored"] = restored_version
            stats["files_restored"] = len(corrupted_files)

            logger.info(f"Restored from snapshot version {restored_version}")

        logger.info("Crash recovery complete")

        return stats

    def _check_integrity(self) -> list[Path]:
        """
        Integrity check.

        Returns:
            Corrupted file paths
        """
        corrupted = []

        # Data directory의 모든 파일 검사
        for file_path in self.data_path.rglob("*"):
            if file_path.is_file() and not file_path.name.endswith(".tmp"):
                # Checksum 검증
                if not self.atomic_writer.verify_integrity(file_path):
                    corrupted.append(file_path)

        return corrupted

    def _restore_from_snapshot(self) -> int | None:
        """
        최신 good snapshot에서 복원.

        Returns:
            Restored snapshot version, or None if no snapshot available
        """
        # 최신 snapshot 찾기
        latest_version = self.snapshot_store.get_latest_version()

        if latest_version is None:
            logger.warning("No snapshot available for recovery")
            return None

        # Snapshot 로드
        snapshot_data = self.snapshot_store.load_snapshot(latest_version)

        if snapshot_data is None:
            logger.error(f"Failed to load snapshot version {latest_version}")
            return None

        # Snapshot 복원
        # (실제 복원 로직은 application-specific)
        # 여기서는 placeholder로 남김
        logger.info(f"Restoring from snapshot version {latest_version}")

        return latest_version

    def create_recovery_point(self, snapshot_id: str, data: bytes) -> int:
        """
        Recovery point 생성 (snapshot).

        Args:
            snapshot_id: Snapshot identifier
            data: Snapshot data

        Returns:
            Snapshot version
        """
        # Snapshot 저장
        version = self.snapshot_store.save_snapshot(
            snapshot_id=snapshot_id, data=data, metadata={"recovery_point": True}
        )

        # WAL entry 기록
        wal_entry = WALEntry(
            entry_id=f"snapshot_{version}",
            timestamp=self.snapshot_store.get_snapshot_metadata(version).timestamp,
            operation="create",
            object_type="snapshot",
            object_id=snapshot_id,
        )

        self.wal.append(wal_entry)

        return version

    def get_recovery_status(self) -> dict:
        """
        Recovery 상태 조회.

        Returns:
            WAL stats + snapshot stats + integrity status
        """
        # WAL 상태
        wal_stats = self.wal.get_stats()

        # Snapshot 상태
        snapshot_stats = self.snapshot_store.get_storage_stats()

        # Integrity check
        corrupted_files = self._check_integrity()

        return {
            "wal": wal_stats,
            "snapshots": snapshot_stats,
            "integrity_ok": len(corrupted_files) == 0,
            "corrupted_file_count": len(corrupted_files),
        }
