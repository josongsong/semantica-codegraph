"""
ShadowFS Port

Abstract interface for file-level overlay filesystem.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from codegraph_runtime.codegen_loop.domain.shadowfs.models import FilePatch


class ShadowFSPort(ABC):
    """
    ShadowFS Port (File Layer)

    Responsibilities:
        - In-memory file overlay
        - Tombstone deletion tracking
        - Diff generation
        - External tool materialization

    NOT responsible for:
        - IR parsing (handled by TransactionPort)
        - Transaction safety (handled by UnifiedShadowFS)
        - Edge cases (handled by infrastructure implementations)

    References:
        - UnionFS (FreeBSD, 2004)
        - OverlayFS (Linux Kernel, 2014)
        - Docker Layers

    Examples:
        >>> fs = ShadowFSCoreAdapter(workspace_root=Path("/project"))
        >>> fs.write_file("main.py", "print('hello')")
        >>> content = fs.read_file("main.py")
        >>> patches = fs.get_diff()
    """

    @abstractmethod
    def read_file(self, path: str) -> str:
        """
        Read file content

        Priority:
            1. Check deleted → FileNotFoundError
            2. Check overlay → Return modified
            3. Read disk → Return original

        Args:
            path: Relative path from workspace_root

        Returns:
            File content

        Raises:
            FileNotFoundError: File deleted or doesn't exist
        """
        raise NotImplementedError

    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """
        Write file (memory only)

        Action:
            1. Store in overlay
            2. Remove from deleted set

        Args:
            path: Relative path
            content: File content
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, path: str) -> None:
        """
        Delete file (tombstone)

        Action:
            1. Add to deleted set
            2. Remove from overlay (if exists)

        Args:
            path: Relative path
        """
        raise NotImplementedError

    @abstractmethod
    def list_files(self, prefix: str | None = None, suffix: str | None = None) -> list[str]:
        """
        List all visible files

        Strategy:
            1. Get disk files
            2. Add overlay files
            3. Remove deleted files
            4. Apply filters

        Args:
            prefix: Filter by prefix (e.g., "src/")
            suffix: Filter by suffix (e.g., ".py")

        Returns:
            Sorted list of visible file paths
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        Check if file exists

        Args:
            path: Relative path

        Returns:
            True if file exists (overlay or disk, not deleted)
        """
        raise NotImplementedError

    @abstractmethod
    def get_diff(self) -> list[FilePatch]:
        """
        Generate patches for all changes

        Returns:
            List of FilePatch objects
        """
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """
        Clear all changes

        Action:
            1. Clear overlay
            2. Clear deleted set
        """
        raise NotImplementedError

    @abstractmethod
    def get_modified_files(self) -> list[str]:
        """Get list of modified file paths"""
        raise NotImplementedError

    @abstractmethod
    def get_deleted_files(self) -> list[str]:
        """Get list of deleted file paths"""
        raise NotImplementedError

    @abstractmethod
    def is_modified(self) -> bool:
        """Check if any changes exist"""
        raise NotImplementedError

    @abstractmethod
    def prepare_for_external_tool(self) -> Path:
        """
        Materialize overlay to temporary directory

        Use case:
            External tools (pytest, tsc, docker) need real filesystem

        Strategy:
            1. Create temp directory
            2. Copy workspace (optimized with symlinks)
            3. Apply overlay
            4. Apply deletions

        Returns:
            Path to materialized directory
        """
        raise NotImplementedError

    @abstractmethod
    def cleanup_temp(self, temp_dir: Path) -> None:
        """
        Cleanup materialized temp directory

        Args:
            temp_dir: Path returned by prepare_for_external_tool()
        """
        raise NotImplementedError
