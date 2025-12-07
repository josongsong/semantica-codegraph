"""
Atomic File Writer Unit Tests
"""

import tempfile
from pathlib import Path

import pytest

from src.contexts.reasoning_engine.infrastructure.storage.atomic_writer import (
    AtomicFileWriter,
)


def test_atomic_write():
    """Atomic write 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = AtomicFileWriter()

        target_path = Path(tmpdir) / "test.dat"
        data = b"test data"

        # Atomic write
        writer.write_atomic(target_path, data)

        # 파일 확인
        assert target_path.exists()

        with open(target_path, "rb") as f:
            assert f.read() == data

        # Checksum 파일 존재
        checksum_path = target_path.parent / (target_path.name + ".checksum")
        assert checksum_path.exists()


def test_atomic_write_integrity():
    """Integrity 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = AtomicFileWriter()

        target_path = Path(tmpdir) / "test.dat"
        data = b"test data"

        # Atomic write with verification
        writer.write_atomic(target_path, data, verify=True)

        # Verify integrity
        assert writer.verify_integrity(target_path) is True


def test_atomic_write_corrupted():
    """Corrupted file 감지 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = AtomicFileWriter()

        target_path = Path(tmpdir) / "test.dat"
        data = b"test data"

        # Atomic write
        writer.write_atomic(target_path, data)

        # 파일 조작
        with open(target_path, "wb") as f:
            f.write(b"corrupted data")

        # Integrity check 실패
        assert writer.verify_integrity(target_path) is False


def test_atomic_write_rollback_on_error():
    """Error 시 temp 파일 정리 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = AtomicFileWriter()

        # 존재하지 않는 디렉토리 (write 실패)
        target_path = Path(tmpdir) / "nonexistent" / "test.dat"
        data = b"test data"

        # Write 실패
        with pytest.raises(FileNotFoundError):
            writer.write_atomic(target_path, data)

        # Temp 파일 생성 안 됨
        temp_path = target_path.with_suffix(".tmp")
        assert not temp_path.exists()


def test_cleanup_temp_files():
    """Temp 파일 정리 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = AtomicFileWriter()
        tmpdir_path = Path(tmpdir)

        # Temp 파일 생성
        temp1 = tmpdir_path / "file1.tmp"
        temp2 = tmpdir_path / "file2.tmp"

        temp1.write_bytes(b"temp1")
        temp2.write_bytes(b"temp2")

        # Cleanup
        writer.cleanup_temp_files(tmpdir_path)

        # Temp 파일 삭제됨
        assert not temp1.exists()
        assert not temp2.exists()


def test_no_temp_file_without_write():
    """Write 전 temp 파일 없음 검증"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Temp 파일 없음
        temp_files = list(tmpdir_path.glob("*.tmp"))
        assert len(temp_files) == 0
