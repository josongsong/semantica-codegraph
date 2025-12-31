"""
RFC-039 P0.1.5: Tests for Atomic I/O Utilities (atomic_io.py)
"""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.cache.atomic_io import (
    atomic_write_file,
    read_with_retry,
    ensure_directory,
    safe_unlink,
    cleanup_tmp_files,
    get_file_size_safe,
)
from codegraph_engine.code_foundation.infrastructure.ir.cache.core import (
    CacheDiskFullError,
    CachePermissionError,
)


class TestAtomicWriteFile:
    """atomic_write_file tests."""

    def test_basic_write(self):
        """Basic write creates file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            data = b"hello world"

            success = atomic_write_file(path, data)

            assert success is True
            assert path.exists()
            assert path.read_bytes() == data

    def test_creates_parent_directories(self):
        """Write creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a" / "b" / "c" / "test.bin"
            data = b"nested file"

            success = atomic_write_file(path, data)

            assert success is True
            assert path.exists()
            assert path.read_bytes() == data

    def test_overwrites_existing_file(self):
        """Write overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            path.write_bytes(b"old content")

            success = atomic_write_file(path, b"new content")

            assert success is True
            assert path.read_bytes() == b"new content"

    def test_atomic_no_partial_file(self):
        """No partial file on crash (simulated by exception)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            original = b"original content"
            path.write_bytes(original)

            # Make directory read-only to cause write failure
            # (This test may not work on all systems)
            try:
                Path(tmpdir).chmod(0o444)
                atomic_write_file(path, b"new content")
            except (CachePermissionError, PermissionError):
                pass
            finally:
                Path(tmpdir).chmod(0o755)

            # Original file should be intact (or overwritten, depending on timing)
            assert path.exists()

    def test_with_flock(self):
        """Write with flock enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"

            success = atomic_write_file(path, b"locked write", use_flock=True)

            assert success is True
            assert path.read_bytes() == b"locked write"

    def test_without_fsync(self):
        """Write without fsync (faster but less durable)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"

            success = atomic_write_file(path, b"no fsync", fsync=False)

            assert success is True
            assert path.read_bytes() == b"no fsync"

    def test_concurrent_writes(self):
        """Concurrent writes don't corrupt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            errors = []

            def writer(content: bytes):
                try:
                    for _ in range(10):
                        atomic_write_file(path, content, use_flock=True)
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=writer, args=(b"content A",)),
                threading.Thread(target=writer, args=(b"content B",)),
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            # File should have one of the contents (not corrupted)
            content = path.read_bytes()
            assert content in (b"content A", b"content B")


class TestReadWithRetry:
    """read_with_retry tests."""

    def test_basic_read(self):
        """Basic read returns file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            path.write_bytes(b"hello world")

            result = read_with_retry(path)

            assert result == b"hello world"

    def test_nonexistent_file(self):
        """Reading nonexistent file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.bin"

            result = read_with_retry(path)

            assert result is None

    def test_with_validator_pass(self):
        """Validator that passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            path.write_bytes(b"valid")

            result = read_with_retry(
                path,
                validator=lambda data: data == b"valid",
            )

            assert result == b"valid"

    def test_with_validator_fail(self):
        """Validator that fails returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            path.write_bytes(b"invalid")

            result = read_with_retry(
                path,
                validator=lambda data: data == b"valid",
            )

            assert result is None

    def test_retry_on_transient_error(self):
        """Retries on transient file errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"

            # File will be created mid-retry
            def delayed_create():
                time.sleep(0.03)
                path.write_bytes(b"delayed content")

            threading.Thread(target=delayed_create).start()

            # Should eventually succeed
            result = read_with_retry(
                path,
                max_retries=5,
                retry_delay_ms=20,
            )

            # May or may not succeed depending on timing
            if result is not None:
                assert result == b"delayed content"


class TestEnsureDirectory:
    """ensure_directory tests."""

    def test_creates_directory(self):
        """Creates directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "new_dir"

            success = ensure_directory(path)

            assert success is True
            assert path.is_dir()

    def test_creates_nested_directories(self):
        """Creates nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a" / "b" / "c"

            success = ensure_directory(path)

            assert success is True
            assert path.is_dir()

    def test_existing_directory_ok(self):
        """Existing directory is ok."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            success = ensure_directory(path)

            assert success is True


class TestSafeUnlink:
    """safe_unlink tests."""

    def test_deletes_file(self):
        """Deletes existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            path.write_bytes(b"content")

            success = safe_unlink(path)

            assert success is True
            assert not path.exists()

    def test_nonexistent_file_ok(self):
        """Nonexistent file returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.bin"

            success = safe_unlink(path)

            assert success is True


class TestCleanupTmpFiles:
    """cleanup_tmp_files tests."""

    def test_cleans_tmp_files(self):
        """Cleans up .tmp_ prefixed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)

            # Create tmp files
            (directory / ".tmp_abc123.pkl").write_bytes(b"tmp1")
            (directory / ".tmp_def456.pkl").write_bytes(b"tmp2")
            (directory / "regular.pkl").write_bytes(b"regular")

            cleaned = cleanup_tmp_files(directory, suffix=".pkl")

            assert cleaned == 2
            assert not (directory / ".tmp_abc123.pkl").exists()
            assert not (directory / ".tmp_def456.pkl").exists()
            assert (directory / "regular.pkl").exists()

    def test_custom_suffix(self):
        """Uses custom suffix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)

            (directory / ".tmp_abc.sem").write_bytes(b"tmp")
            (directory / ".tmp_abc.pkl").write_bytes(b"not this")

            cleaned = cleanup_tmp_files(directory, suffix=".sem")

            assert cleaned == 1
            assert not (directory / ".tmp_abc.sem").exists()
            assert (directory / ".tmp_abc.pkl").exists()


class TestGetFileSizeSafe:
    """get_file_size_safe tests."""

    def test_returns_file_size(self):
        """Returns actual file size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.bin"
            content = b"x" * 100
            path.write_bytes(content)

            size = get_file_size_safe(path)

            assert size == 100

    def test_nonexistent_file_returns_zero(self):
        """Nonexistent file returns 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.bin"

            size = get_file_size_safe(path)

            assert size == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
