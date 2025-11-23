"""
Git CLI Adapter

Implements GitProviderPort using GitPython or subprocess.
"""

from pathlib import Path
from typing import Any, Optional

from ...core.ports.git_provider import GitCommit, GitDiff, GitProviderPort


class GitCLIAdapter(GitProviderPort):
    """
    Git implementation using GitPython.
    """

    def __init__(self):
        """Initialize Git adapter."""
        # TODO: Initialize GitPython
        pass

    async def get_current_branch(self, repo_path: Path) -> str:
        """Get current branch."""
        # TODO: Implement
        raise NotImplementedError

    async def list_branches(self, repo_path: Path) -> list[str]:
        """List branches."""
        # TODO: Implement
        raise NotImplementedError

    async def get_commit_history(
        self,
        repo_path: Path,
        branch: str,
        max_count: Optional[int] = None,
    ) -> list[GitCommit]:
        """Get commit history."""
        # TODO: Implement
        raise NotImplementedError

    async def get_commit(self, repo_path: Path, commit_hash: str) -> GitCommit:
        """Get specific commit."""
        # TODO: Implement
        raise NotImplementedError

    async def get_diff(
        self,
        repo_path: Path,
        from_ref: str,
        to_ref: str,
    ) -> list[GitDiff]:
        """Get diff between refs."""
        # TODO: Implement
        raise NotImplementedError

    async def get_file_blame(
        self,
        repo_path: Path,
        file_path: str,
        ref: str = "HEAD",
    ) -> list[dict[str, Any]]:
        """Get file blame."""
        # TODO: Implement
        raise NotImplementedError

    async def get_file_at_commit(
        self,
        repo_path: Path,
        file_path: str,
        commit_hash: str,
    ) -> Optional[str]:
        """Get file content at commit."""
        # TODO: Implement
        raise NotImplementedError

    async def get_changed_files(
        self,
        repo_path: Path,
        commit_hash: str,
    ) -> list[str]:
        """Get changed files in commit."""
        # TODO: Implement
        raise NotImplementedError
