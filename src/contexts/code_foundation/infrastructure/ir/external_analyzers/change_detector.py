"""
Change Detector for Incremental Updates

RFC-023 M2: Detects changed files using Git diff

Features:
- Detect changed/modified files
- Detect deleted files
- Filter by file extension (default: .py)
- Support since-commit or uncommitted changes
"""

import subprocess
from pathlib import Path


class ChangeDetector:
    """
    Detects changed files in a Git repository.

    M2: Used for incremental Pyright analysis
    """

    def __init__(self, project_root: Path):
        """
        Initialize change detector.

        Args:
            project_root: Project root directory (must be a Git repo)

        Raises:
            ValueError: If project_root is not a Git repository
        """
        self.project_root = project_root

        # Verify it's a Git repo
        if not (project_root / ".git").exists():
            raise ValueError(f"Not a Git repository: {project_root}")

    def detect_changed_files(
        self,
        since_commit: str | None = None,
        file_extensions: list[str] | None = None,
    ) -> tuple[list[Path], list[Path]]:
        """
        Detect changed and deleted files.

        Args:
            since_commit: Git commit hash to compare against (None = uncommitted changes)
            file_extensions: File extensions to include (default: [".py"])

        Returns:
            (changed_files, deleted_files)
            - changed_files: List of modified/added files (absolute paths)
            - deleted_files: List of deleted files (absolute paths)

        Example:
            # Uncommitted changes only
            changed, deleted = detector.detect_changed_files()

            # Since specific commit
            changed, deleted = detector.detect_changed_files(since_commit="abc123")

            # All file types
            changed, deleted = detector.detect_changed_files(file_extensions=[])

        Performance:
            O(N) where N = number of changed files (not total files)
        """
        if file_extensions is None:
            file_extensions = [".py"]

        # Build git diff command
        if since_commit:
            # Compare with specific commit
            cmd = ["git", "diff", "--name-status", since_commit]
        else:
            # Uncommitted changes (staged + unstaged)
            cmd = ["git", "diff", "--name-status", "HEAD"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git diff failed: {e.stderr}") from e

        # Parse output
        changed_files = []
        deleted_files = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue

            status, file_path = parts
            full_path = self.project_root / file_path

            # Filter by extension
            if file_extensions and full_path.suffix not in file_extensions:
                continue

            # Categorize by status
            if status.startswith("D"):
                # Deleted
                deleted_files.append(full_path)
            elif status in ["A", "M", "R", "C"]:
                # Added, Modified, Renamed, Copied
                if full_path.exists():
                    changed_files.append(full_path)

        return changed_files, deleted_files

    def detect_all_uncommitted(self, file_extensions: list[str] | None = None) -> tuple[list[Path], list[Path]]:
        """
        Detect all uncommitted changes (staged + unstaged).

        This is a convenience method for detect_changed_files(since_commit=None).

        Args:
            file_extensions: File extensions to include (default: [".py"])

        Returns:
            (changed_files, deleted_files)
        """
        return self.detect_changed_files(since_commit=None, file_extensions=file_extensions)

    def detect_since_last_snapshot(
        self, snapshot_commit: str, file_extensions: list[str] | None = None
    ) -> tuple[list[Path], list[Path]]:
        """
        Detect changes since last Pyright snapshot.

        This is a convenience method for detect_changed_files(since_commit=...).

        Args:
            snapshot_commit: Git commit hash when last snapshot was created
            file_extensions: File extensions to include (default: [".py"])

        Returns:
            (changed_files, deleted_files)

        Usage:
            # Store snapshot_commit when creating snapshot
            snapshot.attrs["git_commit"] = get_current_commit()

            # Later: detect changes since that snapshot
            changed, deleted = detector.detect_since_last_snapshot(
                snapshot.attrs["git_commit"]
            )
        """
        return self.detect_changed_files(since_commit=snapshot_commit, file_extensions=file_extensions)

    def get_current_commit(self) -> str:
        """
        Get current Git commit hash (HEAD).

        Returns:
            Commit hash (e.g., "abc123def456...")

        Raises:
            RuntimeError: If Git command fails
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get current commit: {e.stderr}") from e

    def has_uncommitted_changes(self) -> bool:
        """
        Check if there are any uncommitted changes.

        Returns:
            True if there are uncommitted changes, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
