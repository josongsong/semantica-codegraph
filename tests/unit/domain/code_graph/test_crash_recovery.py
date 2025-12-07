"""
Crash Recovery Manager Unit Tests
"""

import tempfile
from pathlib import Path

import pytest

from src.contexts.reasoning_engine.infrastructure.storage.atomic_writer import (
    AtomicFileWriter,
)
from src.contexts.reasoning_engine.infrastructure.storage.crash_recovery import (
    CrashRecoveryManager,
)
from src.contexts.reasoning_engine.infrastructure.storage.snapshot_store import (
    SnapshotStore,
)
from src.contexts.reasoning_engine.infrastructure.storage.wal import WriteAheadLog


def test_crash_recovery_clean_state():
    """Clean state에서 recovery 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        wal = WriteAheadLog(str(tmpdir_path / "wal"))
        snapshot_store = SnapshotStore(str(tmpdir_path / "snapshots"))
        atomic_writer = AtomicFileWriter()

        recovery = CrashRecoveryManager(
            wal=wal,
            snapshot_store=snapshot_store,
            atomic_writer=atomic_writer,
            data_path=tmpdir_path / "data",
        )

        # Clean state recovery
        stats = recovery.recover()

        assert stats["wal_entries_replayed"] == 0
        assert stats["corrupted_files_found"] == 0
        assert stats["files_restored"] == 0


def test_crash_recovery_with_wal():
    """WAL replay 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        wal = WriteAheadLog(str(tmpdir_path / "wal"))
        snapshot_store = SnapshotStore(str(tmpdir_path / "snapshots"))
        atomic_writer = AtomicFileWriter()

        # WAL entry 추가
        from src.contexts.reasoning_engine.infrastructure.storage.wal import WALEntry

        entry = WALEntry(
            entry_id="e1",
            timestamp=1000.0,
            operation="create",
            object_type="snapshot",
            object_id="s1",
        )

        wal.append(entry)

        recovery = CrashRecoveryManager(
            wal=wal,
            snapshot_store=snapshot_store,
            atomic_writer=atomic_writer,
            data_path=tmpdir_path / "data",
        )

        # Recovery
        stats = recovery.recover()

        assert stats["wal_entries_replayed"] == 1


def test_crash_recovery_with_snapshot():
    """Snapshot 복원 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        wal = WriteAheadLog(str(tmpdir_path / "wal"))
        snapshot_store = SnapshotStore(str(tmpdir_path / "snapshots"))
        atomic_writer = AtomicFileWriter()

        # Snapshot 생성
        snapshot_store.save_snapshot(
            snapshot_id="snap1",
            data=b"snapshot data",
        )

        recovery = CrashRecoveryManager(
            wal=wal,
            snapshot_store=snapshot_store,
            atomic_writer=atomic_writer,
            data_path=tmpdir_path / "data",
        )

        # Recovery status
        status = recovery.get_recovery_status()

        assert status["snapshots"]["snapshot_count"] == 1
        assert status["integrity_ok"] is True


def test_create_recovery_point():
    """Recovery point 생성 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        wal = WriteAheadLog(str(tmpdir_path / "wal"))
        snapshot_store = SnapshotStore(str(tmpdir_path / "snapshots"))
        atomic_writer = AtomicFileWriter()

        recovery = CrashRecoveryManager(
            wal=wal,
            snapshot_store=snapshot_store,
            atomic_writer=atomic_writer,
            data_path=tmpdir_path / "data",
        )

        # Recovery point 생성
        version = recovery.create_recovery_point(
            snapshot_id="checkpoint1",
            data=b"checkpoint data",
        )

        assert version == 1

        # Snapshot 확인
        snapshot = snapshot_store.get_snapshot_metadata(version)
        assert snapshot.metadata["recovery_point"] is True


def test_recovery_status():
    """Recovery 상태 조회 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        wal = WriteAheadLog(str(tmpdir_path / "wal"))
        snapshot_store = SnapshotStore(str(tmpdir_path / "snapshots"))
        atomic_writer = AtomicFileWriter()

        recovery = CrashRecoveryManager(
            wal=wal,
            snapshot_store=snapshot_store,
            atomic_writer=atomic_writer,
            data_path=tmpdir_path / "data",
        )

        # Status 조회
        status = recovery.get_recovery_status()

        assert "wal" in status
        assert "snapshots" in status
        assert "integrity_ok" in status
        assert status["corrupted_file_count"] == 0
