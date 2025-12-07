"""
Snapshot Store Unit Tests
"""

import tempfile
import time

import pytest

from src.contexts.reasoning_engine.infrastructure.storage.snapshot_store import (
    Snapshot,
    SnapshotStore,
)


def test_snapshot_save_and_load():
    """Snapshot 저장 및 로드 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # Snapshot 저장
        data = b"test snapshot data"
        version = store.save_snapshot(
            snapshot_id="snap1",
            data=data,
            metadata={"test": "value"},
        )

        assert version == 1

        # Snapshot 로드
        loaded = store.load_snapshot(version)

        assert loaded == data


def test_snapshot_compression():
    """Snapshot 압축 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # 반복되는 데이터 (압축 효율 좋음)
        data = b"x" * 10000

        version = store.save_snapshot(
            snapshot_id="snap1",
            data=data,
        )

        # Metadata 확인
        snapshot = store.get_snapshot_metadata(version)

        assert snapshot.original_size == len(data)
        assert snapshot.compressed_size < len(data)  # 압축됨


def test_snapshot_incremental():
    """Incremental snapshot 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # Base snapshot
        base_version = store.save_snapshot(
            snapshot_id="base",
            data=b"base data",
        )

        # Incremental snapshot
        incremental_version = store.save_snapshot(
            snapshot_id="incremental",
            data=b"incremental data",
            base_version=base_version,
        )

        # Metadata 확인
        incremental = store.get_snapshot_metadata(incremental_version)

        assert incremental.is_incremental is True
        assert incremental.base_version == base_version


def test_snapshot_list():
    """Snapshot 목록 조회 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # 여러 snapshot 생성
        versions = []
        for i in range(5):
            version = store.save_snapshot(
                snapshot_id=f"snap{i}",
                data=f"data{i}".encode(),
            )
            versions.append(version)
            time.sleep(0.01)  # Timestamp 차이

        # 전체 목록
        snapshots = store.list_snapshots()
        assert len(snapshots) == 5

        # Time range filter
        mid_time = store.get_snapshot_metadata(versions[2]).timestamp

        after_snapshots = store.list_snapshots(after=mid_time)
        assert len(after_snapshots) == 2  # versions[3], versions[4]


def test_snapshot_delete():
    """Snapshot 삭제 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        version = store.save_snapshot(
            snapshot_id="snap1",
            data=b"test data",
        )

        # 삭제
        store.delete_snapshot(version)

        # 로드 실패
        loaded = store.load_snapshot(version)
        assert loaded is None


def test_snapshot_stats():
    """Snapshot 통계 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # 여러 snapshot 생성
        for i in range(3):
            store.save_snapshot(
                snapshot_id=f"snap{i}",
                data=b"x" * 1000,
            )

        stats = store.get_storage_stats()

        assert stats["snapshot_count"] == 3
        assert stats["total_original_mb"] > 0
        assert stats["compression_ratio"] > 1.0  # 압축됨


def test_snapshot_latest_version():
    """최신 snapshot version 조회 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SnapshotStore(tmpdir)

        # 초기 상태
        assert store.get_latest_version() is None

        # Snapshot 추가
        v1 = store.save_snapshot("s1", b"data1")
        assert store.get_latest_version() == v1

        v2 = store.save_snapshot("s2", b"data2")
        assert store.get_latest_version() == v2
