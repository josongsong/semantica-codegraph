"""
WAL (Write-Ahead Log) Unit Tests
"""

import tempfile
from pathlib import Path

import pytest

from src.contexts.reasoning_engine.infrastructure.storage.wal import (
    WALEntry,
    WriteAheadLog,
)


def test_wal_append_and_replay():
    """WAL append 및 replay 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal = WriteAheadLog(tmpdir)

        # Entry 생성
        entry1 = WALEntry(
            entry_id="e1",
            timestamp=1000.0,
            operation="create",
            object_type="snapshot",
            object_id="snap1",
            data=b"test data 1",
        )

        entry2 = WALEntry(
            entry_id="e2",
            timestamp=1001.0,
            operation="update",
            object_type="ir",
            object_id="ir1",
            data=b"test data 2",
        )

        # Append
        wal.append(entry1)
        wal.append(entry2)

        # Replay
        replayed = wal.replay()

        assert len(replayed) == 2
        assert replayed[0].entry_id == "e1"
        assert replayed[0].data == b"test data 1"
        assert replayed[1].entry_id == "e2"
        assert replayed[1].data == b"test data 2"


def test_wal_rotation():
    """WAL rotation 검증"""
    import time as time_module

    with tempfile.TemporaryDirectory() as tmpdir:
        wal = WriteAheadLog(tmpdir)

        # 초기 log 파일
        initial_log = wal.current_log

        # Rotation (파일 크기가 10MB 미만이므로 rotation 안 됨)
        wal.rotate()
        assert wal.current_log == initial_log

        # 큰 데이터 추가 (11MB)
        large_data = b"x" * (11 * 1024 * 1024)
        entry = WALEntry(
            entry_id="large",
            timestamp=1000.0,
            operation="create",
            object_type="snapshot",
            object_id="s1",
            data=large_data,
        )

        wal.append(entry)

        # 다른 timestamp 보장
        time_module.sleep(1.1)

        # 파일이 10MB 초과했으므로 rotation
        wal.rotate()

        # Rotation 후 새 파일로 전환 (파일은 아직 생성 안 됨)
        assert wal.current_log != initial_log

        # 새 파일에 entry 추가하면 생성됨
        small_entry = WALEntry(
            entry_id="small",
            timestamp=2000.0,
            operation="update",
            object_type="ir",
            object_id="ir1",
        )
        wal.append(small_entry)
        assert wal.current_log.exists()


def test_wal_truncate():
    """WAL truncate 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal = WriteAheadLog(tmpdir)

        entry = WALEntry(
            entry_id="e1",
            timestamp=1000.0,
            operation="create",
            object_type="snapshot",
            object_id="s1",
        )

        wal.append(entry)

        # Truncate (현재 시간 이후로 설정하면 모든 파일 삭제)
        import time

        wal.truncate_before(time.time() + 1000)

        # Replay (빈 결과)
        replayed = wal.replay()
        assert len(replayed) == 0


def test_wal_checksum_verification():
    """WAL checksum 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal = WriteAheadLog(tmpdir)

        entry = WALEntry(
            entry_id="e1",
            timestamp=1000.0,
            operation="create",
            object_type="snapshot",
            object_id="s1",
            data=b"test data",
        )

        wal.append(entry)

        # 파일 조작 (checksum 손상)
        log_file = wal.current_log

        # 마지막 바이트 변경
        with open(log_file, "rb") as f:
            content = f.read()

        corrupted = content[:-1] + b"X"

        with open(log_file, "wb") as f:
            f.write(corrupted)

        # Replay (corrupted entry는 무시)
        replayed = wal.replay()
        assert len(replayed) == 0  # Checksum 실패로 entry 무시


def test_wal_stats():
    """WAL 통계 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal = WriteAheadLog(tmpdir)

        # Entry 추가
        for i in range(5):
            entry = WALEntry(
                entry_id=f"e{i}",
                timestamp=1000.0 + i,
                operation="create",
                object_type="snapshot",
                object_id=f"s{i}",
            )
            wal.append(entry)

        stats = wal.get_stats()

        assert stats["log_count"] >= 1
        assert stats["total_size_mb"] > 0
