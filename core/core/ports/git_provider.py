"""
Git Provider Port

Abstract interface for Git operations.
Implementations: GitPython, git CLI wrapper, etc.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class GitCommit:
    """Git commit data transfer object."""

    def __init__(
        self,
        hash: str,
        author: str,
        author_email: str,
        authored_at: datetime,
        message: str,
        parents: list[str],
    ):
        self.hash = hash
        self.author = author
        self.author_email = author_email
        self.authored_at = authored_at
        self.message = message
        self.parents = parents


class GitDiff:
    """Git diff data transfer object."""

    def __init__(
        self,
        file_path: str,
        change_type: str,  # "added", "modified", "deleted", "renamed"
        additions: int,
        deletions: int,
        diff_content: Optional[str] = None,
    ):
        self.file_path = file_path
        self.change_type = change_type
        self.additions = additions
        self.deletions = deletions
        self.diff_content = diff_content


class GitProviderPort(ABC):
    """
    Port for Git operations.

    Responsibilities:
    - Read git history
    - Get branch information
    - Analyze changes and blame
    """

    @abstractmethod
    async def get_current_branch(self, repo_path: Path) -> str:
        """Get the current branch name."""
        pass

    @abstractmethod
    async def list_branches(self, repo_path: Path) -> list[str]:
        """List all branches in the repository."""
        pass

    @abstractmethod
    async def get_commit_history(
        self,
        repo_path: Path,
        branch: str,
        max_count: Optional[int] = None,
    ) -> list[GitCommit]:
        """
        Get commit history for a branch.

        Args:
            repo_path: Path to repository
            branch: Branch name
            max_count: Maximum number of commits to retrieve

        Returns:
            List of commits
        """
        pass

    @abstractmethod
    async def get_commit(self, repo_path: Path, commit_hash: str) -> GitCommit:
        """Get a specific commit."""
        pass

    @abstractmethod
    async def get_diff(
        self,
        repo_path: Path,
        from_ref: str,
        to_ref: str,
    ) -> list[GitDiff]:
        """
        Get diff between two refs (commits, branches, tags).

        Args:
            repo_path: Path to repository
            from_ref: Source reference
            to_ref: Target reference

        Returns:
            List of file changes
        """
        pass

    @abstractmethod
    async def get_file_blame(
        self,
        repo_path: Path,
        file_path: str,
        ref: str = "HEAD",
    ) -> list[dict[str, Any]]:
        """
        Get blame information for a file.

        Returns:
            List of line blame info (author, commit, timestamp)
        """
        pass

    @abstractmethod
    async def get_file_at_commit(
        self,
        repo_path: Path,
        file_path: str,
        commit_hash: str,
    ) -> Optional[str]:
        """
        Get file content at a specific commit.

        Returns:
            File content or None if file doesn't exist
        """
        pass

    @abstractmethod
    async def get_changed_files(
        self,
        repo_path: Path,
        commit_hash: str,
    ) -> list[str]:
        """Get list of files changed in a commit."""
        pass
