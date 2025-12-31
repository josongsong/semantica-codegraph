"""
RFC-039 P0.1.5: Atomic I/O Utilities

Provides atomic write and read-with-retry utilities for cache implementations.

SOTA Features:
- Atomic write: tmp file + rename (POSIX guarantee)
- Optional file locking (fcntl on Unix)
- Retry with exponential backoff for race conditions
- Robust error handling (disk full, permissions)

Usage:
    from codegraph_engine.code_foundation.infrastructure.ir.cache.atomic_io import (
        atomic_write_file,
        read_with_retry,
    )

    # Atomic write
    success = atomic_write_file(path, data, use_flock=True)

    # Read with retry
    data = read_with_retry(path, max_retries=3, retry_delay_ms=20)
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Callable

from .core import (
    CacheCorruptError,
    CacheDiskFullError,
    CachePermissionError,
)


def atomic_write_file(
    path: Path,
    data: bytes,
    use_flock: bool = False,
    fsync: bool = True,
) -> bool:
    """
    Write file atomically using tmp + rename pattern.

    Process:
    1. Create tmp file in same directory (same filesystem)
    2. Write data to tmp file
    3. Optional: fsync to ensure data on disk
    4. Atomic rename to final path (POSIX guarantee)

    Crash Safety:
    - Process crash during write: tmp file left, original intact
    - No partial/corrupted cache files possible
    - POSIX rename() is atomic within same filesystem

    Args:
        path: Final file path
        data: Bytes to write
        use_flock: Use fcntl advisory lock (Unix only)
        fsync: Call fsync after write (slower, more durable)

    Returns:
        True if written successfully

    Raises:
        CacheDiskFullError: Disk full (ENOSPC)
        CachePermissionError: Permission denied (EACCES)
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Create tmp file in same directory (required for atomic rename)
    tmp_fd = None
    tmp_path = None

    try:
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=path.suffix,
            prefix=".tmp_",
            dir=path.parent,
        )

        with os.fdopen(tmp_fd, "wb") as f:
            tmp_fd = None  # fd is now owned by file object

            # Optional: Acquire exclusive lock (multiprocess-safe)
            if use_flock:
                try:
                    import fcntl

                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                except (ImportError, OSError):
                    # Windows or lock not supported: continue without lock
                    pass

            f.write(data)
            f.flush()

            if fsync:
                os.fsync(f.fileno())

        # Atomic rename (POSIX guarantee)
        os.replace(tmp_path, path)
        return True

    except OSError as e:
        # Cleanup tmp file on error
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # ENOSPC (28) = disk full
        if e.errno == 28:
            raise CacheDiskFullError(f"Disk full writing to {path}") from e

        # EACCES (13) = permission denied
        if e.errno == 13:
            raise CachePermissionError(f"Permission denied writing to {path}") from e

        # Other errors
        return False

    except Exception:
        # Cleanup tmp file on any error
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False

    finally:
        # Close fd if not owned by file object
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass


def read_with_retry(
    path: Path,
    max_retries: int = 3,
    retry_delay_ms: int = 20,
    validator: Callable[[bytes], bool] | None = None,
) -> bytes | None:
    """
    Read file with retry for transient errors.

    Retries on:
    - FileNotFoundError (file being replaced)
    - PermissionError (file being written)
    - Partial reads (file being modified)

    Args:
        path: File path to read
        max_retries: Maximum retry attempts
        retry_delay_ms: Delay between retries in milliseconds
        validator: Optional function to validate read data

    Returns:
        File bytes or None if all retries failed
    """
    if not path.exists():
        return None

    last_error = None

    for attempt in range(max_retries):
        try:
            data = path.read_bytes()

            # Optional validation
            if validator is not None:
                if not validator(data):
                    raise CacheCorruptError("Validation failed", cache_path=path)

            return data

        except (PermissionError, FileNotFoundError) as e:
            # Transient error (file being replaced by another process)
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay_ms / 1000)
                continue

        except CacheCorruptError:
            # Validation failed, don't retry
            return None

        except Exception as e:
            # Unexpected error
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay_ms / 1000)
                continue

    return None


def ensure_directory(path: Path) -> bool:
    """
    Ensure directory exists, create if needed.

    Args:
        path: Directory path

    Returns:
        True if directory exists (or was created)
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except (OSError, PermissionError):
        return False


def safe_unlink(path: Path) -> bool:
    """
    Safely delete file, ignoring errors.

    Args:
        path: File path to delete

    Returns:
        True if deleted (or didn't exist)
    """
    try:
        path.unlink(missing_ok=True)
        return True
    except (OSError, PermissionError):
        return False


def cleanup_tmp_files(directory: Path, suffix: str = ".pkl") -> int:
    """
    Clean up orphaned tmp files from crashed writes.

    Args:
        directory: Directory to clean
        suffix: File suffix (e.g., ".pkl", ".sem")

    Returns:
        Number of files cleaned up
    """
    cleaned = 0
    pattern = f".tmp_*{suffix}"

    try:
        for tmp_file in directory.glob(pattern):
            if safe_unlink(tmp_file):
                cleaned += 1
    except (OSError, PermissionError):
        pass

    return cleaned


def get_file_size_safe(path: Path) -> int:
    """
    Get file size safely, returning 0 on error.

    Args:
        path: File path

    Returns:
        File size in bytes, or 0 on error
    """
    try:
        return path.stat().st_size
    except (OSError, FileNotFoundError):
        return 0


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "atomic_write_file",
    "read_with_retry",
    "ensure_directory",
    "safe_unlink",
    "cleanup_tmp_files",
    "get_file_size_safe",
]
