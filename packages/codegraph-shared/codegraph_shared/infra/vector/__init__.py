"""Vector store adapters with type-safe client creation."""

import atexit
import fcntl
import shutil
import signal
from enum import Enum
from pathlib import Path
from typing import Literal

from qdrant_client import AsyncQdrantClient

from codegraph_shared.common.observability import get_logger
from codegraph_shared.infra.vector.qdrant import QdrantAdapter

logger = get_logger(__name__)


class _LockFileManager:
    """
    Embedded 모드 lock 파일 관리 (동시 접근 방지).

    여러 프로세스가 동일한 storage_path를 사용하지 못하도록 보호합니다.
    """

    _lock_files: dict[str, tuple[Path, object]] = {}  # path -> (lock_file, file_obj)
    _shutdown_registered = False

    @classmethod
    def acquire_lock(cls, storage_path: Path) -> None:
        """
        Lock 획득 (non-blocking).

        Raises:
            RuntimeError: 이미 다른 프로세스가 사용 중
        """
        lock_file = storage_path / ".qdrant.lock"

        try:
            lock_file.touch(exist_ok=True)
            lock_fd = open(lock_file, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            import os

            lock_fd.write(f"pid={os.getpid()}\n")
            lock_fd.flush()

            cls._lock_files[str(storage_path)] = (lock_file, lock_fd)

            if not cls._shutdown_registered:
                atexit.register(cls.release_all_locks)
                cls._shutdown_registered = True

            logger.debug(f"Acquired exclusive lock: {lock_file}")

        except (OSError, BlockingIOError) as e:
            raise RuntimeError(
                f"Another process is using Qdrant storage at {storage_path}. "
                f"Embedded mode allows only one process at a time. "
                f"Solutions:\n"
                f"  1. Stop the other process\n"
                f"  2. Use different storage_path\n"
                f"  3. Use server mode for multiple processes"
            ) from e

    @classmethod
    def release_lock(cls, storage_path: Path) -> None:
        """Lock 해제."""
        key = str(storage_path)
        if key in cls._lock_files:
            lock_file, lock_fd = cls._lock_files[key]
            try:
                if hasattr(lock_fd, "fileno"):
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                logger.debug(f"Released lock: {lock_file}")
            except Exception as e:
                logger.warning(f"Failed to release lock: {e}")
            finally:
                del cls._lock_files[key]

    @classmethod
    def release_all_locks(cls) -> None:
        """모든 lock 해제 (종료 시)."""
        for storage_path in list(cls._lock_files.keys()):
            cls.release_lock(Path(storage_path))


class QdrantMode(str, Enum):
    """Qdrant 실행 모드 (타입 안전성 보장)."""

    MEMORY = "memory"
    EMBEDDED = "embedded"
    SERVER = "server"


def create_qdrant_client(
    mode: Literal["memory", "embedded", "server"] = "embedded",
    storage_path: str | None = None,
    url: str | None = None,
    host: str | None = None,
    port: int = 6333,
    grpc_port: int = 6334,
    prefer_grpc: bool = True,
    timeout: int = 60,
    check_disk_space: bool = True,
    min_disk_space_mb: int = 100,
) -> AsyncQdrantClient:
    """
    모드별 Qdrant 클라이언트 생성 (타입 안전성 및 검증 강화).

    Modes:
        - memory: 테스트용 (재시작 시 초기화, 영속성 없음)
        - embedded: 로컬 개발 (디스크 저장, 단일 프로세스)
        - server: Docker 프로덕션 (gRPC 지원, 다중 클라이언트)

    Args:
        mode: 실행 모드 (타입 체크됨)
        storage_path: embedded 모드 저장 경로
        url: server 모드 URL (host보다 우선)
        host: server 모드 호스트
        port: server 모드 HTTP 포트 (1-65535)
        grpc_port: server 모드 gRPC 포트 (1-65535)
        prefer_grpc: gRPC 사용 여부 (server 모드만)
        timeout: 연결 타임아웃 (초, default: 60)
        check_disk_space: embedded 모드 디스크 공간 체크 (default: True)
        min_disk_space_mb: 최소 필요 디스크 공간 (MB, default: 100)

    Returns:
        AsyncQdrantClient 인스턴스

    Raises:
        ValueError: 파라미터가 유효하지 않을 때
        RuntimeError: 디스크 공간 부족 또는 동시 접근 시도
        PermissionError: embedded 경로에 쓰기 권한이 없을 때

    Examples:
        >>> # Memory mode (테스트)
        >>> client = create_qdrant_client(mode="memory")

        >>> # Embedded mode (로컬 개발)
        >>> client = create_qdrant_client(
        ...     mode="embedded",
        ...     storage_path="./data/qdrant"
        ... )

        >>> # Server mode (프로덕션)
        >>> client = create_qdrant_client(
        ...     mode="server",
        ...     url="http://qdrant:6333"
        ... )
    """
    # Mode 검증 (런타임)
    valid_modes = {"memory", "embedded", "server"}
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")

    # Memory 모드
    if mode == "memory":
        logger.debug("Creating Qdrant client in memory mode")
        return AsyncQdrantClient(":memory:")

    # Embedded 모드
    elif mode == "embedded":
        path = storage_path or "./data/qdrant_storage"
        path_obj = Path(path)

        # 디렉토리 생성
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(
                f"No write permission for storage path: {path_obj}. Check permissions: chmod 755 {path_obj.parent}"
            ) from e
        except OSError as e:
            raise ValueError(f"Invalid storage path: {path_obj}. Error: {e}") from e

        # 🔥 CRITICAL: 디스크 공간 체크
        if check_disk_space:
            _check_disk_space(path_obj, min_disk_space_mb)

        # 🔥 CRITICAL: 동시 접근 방지 (Lock 획득)
        _LockFileManager.acquire_lock(path_obj)

        abs_path = str(path_obj.absolute())
        logger.info(f"Creating Qdrant client in embedded mode: {abs_path}")
        return AsyncQdrantClient(path=abs_path)

    # Server 모드
    else:  # mode == "server"
        # Port 검증
        if not (1 <= port <= 65535):
            raise ValueError(f"Invalid port: {port}. Must be 1-65535")
        if not (1 <= grpc_port <= 65535):
            raise ValueError(f"Invalid grpc_port: {grpc_port}. Must be 1-65535")
        if not (1 <= timeout <= 600):
            raise ValueError(f"Invalid timeout: {timeout}. Must be 1-600 seconds")

        # URL 우선
        if url:
            logger.info(f"Creating Qdrant client in server mode: {url} (timeout={timeout}s)")
            return AsyncQdrantClient(url=url, timeout=timeout)

        # Host 검증
        if not host:
            raise ValueError("host or url is required for server mode")

        logger.info(f"Creating Qdrant client in server mode: {host}:{port} (grpc={prefer_grpc}, timeout={timeout}s)")
        return AsyncQdrantClient(
            host=host,
            port=port,
            grpc_port=grpc_port,
            prefer_grpc=prefer_grpc,
            timeout=timeout,
            grpc_options={
                "grpc.max_reconnect_backoff_ms": 5000,
                "grpc.initial_reconnect_backoff_ms": 1000,
            },
        )


def _check_disk_space(path: Path, min_mb: int) -> None:
    """
    디스크 공간 체크 (embedded 모드).

    Args:
        path: 저장 경로
        min_mb: 최소 필요 공간 (MB)

    Raises:
        RuntimeError: 디스크 공간 부족
    """
    try:
        stat = shutil.disk_usage(path)
        free_mb = stat.free / (1024 * 1024)
        total_mb = stat.total / (1024 * 1024)
        used_mb = stat.used / (1024 * 1024)

        if free_mb < min_mb:
            raise RuntimeError(
                f"Insufficient disk space at {path}:\n"
                f"  Free: {free_mb:.1f}MB / Total: {total_mb:.1f}MB\n"
                f"  Used: {used_mb:.1f}MB ({used_mb / total_mb * 100:.1f}%)\n"
                f"  Required: {min_mb}MB\n"
                f"Solutions:\n"
                f"  1. Free up disk space: df -h\n"
                f"  2. Use different storage_path\n"
                f"  3. Reduce min_disk_space_mb parameter"
            )

        logger.debug(f"Disk space check passed: {free_mb:.1f}MB free / {total_mb:.1f}MB total")

    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"Could not check disk space (continuing): {e}")


__all__ = [
    "QdrantAdapter",
    "QdrantMode",
    "create_qdrant_client",
]
