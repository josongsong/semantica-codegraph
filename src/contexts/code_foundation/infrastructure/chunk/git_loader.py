"""
Git File Loader

Provides utilities for loading file contents from Git at specific commits.

GAP A2: Git Error Categorization
    - GitError: Base exception for Git operations
    - GitFileNotFoundError: File doesn't exist at commit
    - GitInvalidCommitError: Invalid commit hash/reference
    - GitRepositoryError: Not a Git repository
    - GitPermissionError: Permission denied
    - GitNetworkError: Network operation failed
"""

import subprocess
from enum import Enum
from pathlib import Path

# ============================================================
# GAP A2: Git Error Categorization
# ============================================================


class GitErrorCategory(str, Enum):
    """Categories for Git errors (GAP A2)."""

    FILE_NOT_FOUND = "file_not_found"
    INVALID_COMMIT = "invalid_commit"
    NOT_A_REPOSITORY = "not_a_repository"
    PERMISSION_DENIED = "permission_denied"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class GitError(Exception):
    """Base exception for Git operations (GAP A2)."""

    def __init__(self, message: str, category: GitErrorCategory = GitErrorCategory.UNKNOWN, stderr: str = ""):
        super().__init__(message)
        self.category = category
        self.stderr = stderr

    def is_retryable(self) -> bool:
        """Check if error is potentially retryable."""
        return self.category == GitErrorCategory.NETWORK_ERROR


class GitFileNotFoundError(GitError, FileNotFoundError):
    """File doesn't exist at specified commit (GAP A2)."""

    def __init__(self, file_path: str, commit: str, stderr: str = ""):
        super().__init__(
            f"File '{file_path}' not found at commit '{commit}'",
            category=GitErrorCategory.FILE_NOT_FOUND,
            stderr=stderr,
        )
        self.file_path = file_path
        self.commit = commit


class GitInvalidCommitError(GitError):
    """Invalid commit hash or reference (GAP A2)."""

    def __init__(self, commit: str, stderr: str = ""):
        super().__init__(
            f"Invalid commit reference: '{commit}'",
            category=GitErrorCategory.INVALID_COMMIT,
            stderr=stderr,
        )
        self.commit = commit


class GitRepositoryError(GitError):
    """Not a valid Git repository (GAP A2)."""

    def __init__(self, path: str, stderr: str = ""):
        super().__init__(
            f"Not a Git repository: '{path}'",
            category=GitErrorCategory.NOT_A_REPOSITORY,
            stderr=stderr,
        )
        self.path = path


class GitPermissionError(GitError):
    """Permission denied for Git operation (GAP A2)."""

    def __init__(self, operation: str, stderr: str = ""):
        super().__init__(
            f"Permission denied for Git operation: '{operation}'",
            category=GitErrorCategory.PERMISSION_DENIED,
            stderr=stderr,
        )
        self.operation = operation


class GitNetworkError(GitError):
    """Network error during Git operation (GAP A2)."""

    def __init__(self, operation: str, stderr: str = ""):
        super().__init__(
            f"Network error during Git operation: '{operation}'",
            category=GitErrorCategory.NETWORK_ERROR,
            stderr=stderr,
        )
        self.operation = operation


def categorize_git_error(e: subprocess.CalledProcessError, context: str = "") -> GitError:
    """
    Categorize a subprocess error into a specific Git error type (GAP A2).

    Args:
        e: CalledProcessError from subprocess
        context: Additional context (e.g., file_path, commit)

    Returns:
        Appropriate GitError subclass
    """
    stderr = e.stderr.lower() if e.stderr else ""

    # File not found patterns
    if any(
        pattern in stderr
        for pattern in [
            "does not exist",
            "path",
            "no such file",
            "pathspec",
            "not in",
        ]
    ):
        return GitFileNotFoundError(context, "unknown", e.stderr)

    # Invalid commit patterns
    if any(
        pattern in stderr
        for pattern in [
            "unknown revision",
            "invalid object name",
            "bad revision",
            "ambiguous argument",
            "not a valid object name",
        ]
    ):
        return GitInvalidCommitError(context, e.stderr)

    # Not a repository patterns
    if any(
        pattern in stderr
        for pattern in [
            "not a git repository",
            "fatal: not a git",
            "not in a git",
        ]
    ):
        return GitRepositoryError(context, e.stderr)

    # Permission patterns
    if any(
        pattern in stderr
        for pattern in [
            "permission denied",
            "access denied",
            "operation not permitted",
        ]
    ):
        return GitPermissionError(context, e.stderr)

    # Network patterns
    if any(
        pattern in stderr
        for pattern in [
            "could not resolve host",
            "connection refused",
            "network is unreachable",
            "connection timed out",
            "unable to access",
        ]
    ):
        return GitNetworkError(context, e.stderr)

    # Unknown error
    return GitError(f"Git error: {e.stderr}", GitErrorCategory.UNKNOWN, e.stderr)


class GitFileLoader:
    """
    Load file contents from Git repository at specific commits.

    Usage:
        loader = GitFileLoader(repo_path="/path/to/repo")
        lines = loader.get_file_at_commit("src/main.py", "abc123")
    """

    def __init__(self, repo_path: str):
        """
        Initialize Git file loader.

        Args:
            repo_path: Path to Git repository root
        """
        self.repo_path = Path(repo_path)

    def get_file_at_commit(self, file_path: str, commit: str = "HEAD") -> list[str]:
        """
        Get file contents at a specific commit.

        Args:
            file_path: Relative path to file from repo root
            commit: Git commit hash, branch name, or "HEAD" (default)

        Returns:
            List of file lines (with newlines stripped)

        Raises:
            GitFileNotFoundError: If file doesn't exist at commit
            GitInvalidCommitError: If commit reference is invalid
            GitRepositoryError: If not a Git repository
            GitError: For other Git errors
        """
        try:
            # Use git show to get file content at specific commit
            result = subprocess.run(
                ["git", "show", f"{commit}:{file_path}"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Split into lines and strip newlines
            return result.stdout.splitlines()

        except subprocess.CalledProcessError as e:
            # GAP A2: Use categorized errors
            stderr = e.stderr.lower() if e.stderr else ""

            if any(pattern in stderr for pattern in ["does not exist", "path", "no such file"]):
                raise GitFileNotFoundError(file_path, commit, e.stderr) from e
            if any(pattern in stderr for pattern in ["unknown revision", "invalid object", "bad revision"]):
                raise GitInvalidCommitError(commit, e.stderr) from e
            if "not a git repository" in stderr:
                raise GitRepositoryError(str(self.repo_path), e.stderr) from e

            raise categorize_git_error(e, file_path) from e

    def get_current_file(self, file_path: str) -> list[str]:
        """
        Get current file contents from working directory.

        Args:
            file_path: Relative path to file from repo root

        Returns:
            List of file lines (with newlines stripped)
        """
        full_path = self.repo_path / file_path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        with open(full_path, encoding="utf-8") as f:
            return f.read().splitlines()

    def file_exists_at_commit(self, file_path: str, commit: str = "HEAD") -> bool:
        """
        Check if file exists at a specific commit.

        Args:
            file_path: Relative path to file from repo root
            commit: Git commit hash, branch name, or "HEAD"

        Returns:
            True if file exists at commit
        """
        try:
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit}:{file_path}"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def get_file_diff(self, file_path: str, old_commit: str, new_commit: str = "HEAD") -> str:
        """
        Get unified diff for a file between two commits.

        Args:
            file_path: Relative path to file from repo root
            old_commit: Old commit hash
            new_commit: New commit hash (default: HEAD)

        Returns:
            Unified diff text

        Raises:
            GitInvalidCommitError: If commit reference is invalid
            GitRepositoryError: If not a Git repository
            GitError: For other Git errors
        """
        try:
            result = subprocess.run(
                ["git", "diff", old_commit, new_commit, "--", file_path],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise categorize_git_error(e, file_path) from e

    def get_current_commit(self) -> str:
        """
        Get current HEAD commit hash.

        Returns:
            Full commit hash

        Raises:
            GitRepositoryError: If not a Git repository
            GitError: For other Git errors
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise categorize_git_error(e, "HEAD") from e


# Convenience function for simple use cases
def get_file_at_commit(repo_path: str, file_path: str, commit: str = "HEAD") -> list[str]:
    """
    Load file contents from Git at a specific commit.

    Convenience wrapper around GitFileLoader.

    Args:
        repo_path: Path to Git repository root
        file_path: Relative path to file from repo root
        commit: Git commit hash, branch name, or "HEAD"

    Returns:
        List of file lines (with newlines stripped)

    Example:
        >>> lines = get_file_at_commit("/path/to/repo", "src/main.py", "abc123")
    """
    loader = GitFileLoader(repo_path)
    return loader.get_file_at_commit(file_path, commit)
