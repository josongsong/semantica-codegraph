"""
Git CLI Adapter

Provides git operations using GitPython library.

Features:
- Repository cloning and fetching
- Branch listing
- File retrieval at specific commits
- Commit log retrieval
- Changed files detection
- Diff generation
- Async interface with sync GitPython wrapped via asyncio.to_thread()

Requirements:
    pip install GitPython

Note:
    GitPython is synchronous. This adapter provides an async interface
    by wrapping sync calls with asyncio.to_thread(). This allows the
    adapter to be used in async contexts without blocking the event loop.
"""

import asyncio
from typing import Any

from git import Repo
from git.exc import GitCommandError

from src.common.observability import get_logger

logger = get_logger(__name__)


class GitCLIAdapter:
    """
    Git operations adapter using GitPython.

    Provides a high-level interface for common git operations
    needed for code indexing and change tracking.
    All public methods are async for consistency with other adapters.
    """

    def __init__(self) -> None:
        """Initialize Git CLI adapter."""
        pass

    # ==================== Async Methods ====================

    async def clone(self, repo_url: str, dest_path: str) -> None:
        """
        Clone a git repository.

        Args:
            repo_url: Repository URL (https or ssh)
            dest_path: Destination path for clone

        Raises:
            RuntimeError: If clone fails
        """
        await asyncio.to_thread(self._clone_sync, repo_url, dest_path)

    async def fetch(self, repo_path: str) -> None:
        """
        Fetch updates from remote repository.

        Args:
            repo_path: Path to local repository

        Raises:
            RuntimeError: If fetch fails
        """
        await asyncio.to_thread(self._fetch_sync, repo_path)

    async def list_branches(self, repo_path: str) -> list[str]:
        """
        List all branches in repository.

        Args:
            repo_path: Path to local repository

        Returns:
            List of branch names

        Raises:
            RuntimeError: If operation fails
        """
        return await asyncio.to_thread(self._list_branches_sync, repo_path)

    async def show_file(self, repo_path: str, commit: str, file_path: str) -> str:
        """
        Get file content at specific commit.

        Args:
            repo_path: Path to local repository
            commit: Commit SHA or reference (e.g., "HEAD", "main")
            file_path: Path to file within repository

        Returns:
            File content as string

        Raises:
            RuntimeError: If operation fails
            ValueError: If file is binary (non-text)
        """
        return await asyncio.to_thread(self._show_file_sync, repo_path, commit, file_path)

    async def log(self, repo_path: str, max_count: int = 10) -> list[dict[str, Any]]:
        """
        Get commit log.

        Args:
            repo_path: Path to local repository
            max_count: Maximum number of commits to retrieve

        Returns:
            List of commit dictionaries with keys:
                - sha: Commit SHA
                - author: Author name
                - email: Author email
                - timestamp: ISO format timestamp
                - message: Commit message

        Raises:
            RuntimeError: If operation fails
        """
        return await asyncio.to_thread(self._log_sync, repo_path, max_count)

    async def get_current_commit(self, repo_path: str) -> str:
        """
        Get current commit SHA (HEAD).

        Args:
            repo_path: Path to local repository

        Returns:
            Commit SHA

        Raises:
            RuntimeError: If operation fails
        """
        return await asyncio.to_thread(self._get_current_commit_sync, repo_path)

    async def get_changed_files(self, repo_path: str, from_commit: str, to_commit: str = "HEAD") -> list[str]:
        """
        Get list of changed files between commits.

        Args:
            repo_path: Path to local repository
            from_commit: Starting commit SHA
            to_commit: Ending commit SHA (default: HEAD)

        Returns:
            List of changed file paths (includes both old and new paths for renames)

        Raises:
            RuntimeError: If operation fails
        """
        return await asyncio.to_thread(self._get_changed_files_sync, repo_path, from_commit, to_commit)

    async def get_file_diff(self, repo_path: str, file_path: str, from_commit: str, to_commit: str = "HEAD") -> str:
        """
        Get diff for specific file between commits.

        Args:
            repo_path: Path to local repository
            file_path: Path to file within repository
            from_commit: Starting commit SHA
            to_commit: Ending commit SHA (default: HEAD)

        Returns:
            Diff content as string (empty if no changes)

        Raises:
            RuntimeError: If operation fails
        """
        return await asyncio.to_thread(self._get_file_diff_sync, repo_path, file_path, from_commit, to_commit)

    # ==================== Sync Implementation Methods ====================

    def _clone_sync(self, repo_url: str, dest_path: str) -> None:
        """Sync implementation of clone."""
        try:
            logger.info(f"Cloning {repo_url} to {dest_path}")
            Repo.clone_from(repo_url, dest_path)
            logger.info(f"Successfully cloned {repo_url}")

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to clone repository: {e}")
            raise RuntimeError(f"Failed to clone repository: {e}") from e

    def _fetch_sync(self, repo_path: str) -> None:
        """Sync implementation of fetch."""
        try:
            repo = Repo(repo_path)
            logger.info(f"Fetching updates for {repo_path}")
            repo.remotes.origin.fetch()
            logger.info(f"Successfully fetched updates for {repo_path}")

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to fetch: {e}")
            raise RuntimeError(f"Failed to fetch: {e}") from e

    def _list_branches_sync(self, repo_path: str) -> list[str]:
        """Sync implementation of list_branches."""
        try:
            repo = Repo(repo_path)
            return [branch.name for branch in repo.branches]

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to list branches: {e}")
            raise RuntimeError(f"Failed to list branches: {e}") from e

    def _show_file_sync(self, repo_path: str, commit: str, file_path: str) -> str:
        """Sync implementation of show_file."""
        try:
            repo = Repo(repo_path)
            commit_obj = repo.commit(commit)

            # Get file blob
            blob = commit_obj.tree / file_path

            # Read file content
            content_bytes = blob.data_stream.read()

            # Decode to string (raise if binary)
            try:
                return content_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError(f"File {file_path} is not a text file") from e

        except ValueError:
            # Re-raise ValueError for binary files
            raise
        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to show file: {e}")
            raise RuntimeError(f"Failed to show file: {e}") from e

    def _log_sync(self, repo_path: str, max_count: int = 10) -> list[dict[str, Any]]:
        """Sync implementation of log."""
        try:
            repo = Repo(repo_path)
            commits = []

            for commit in repo.iter_commits(max_count=max_count):
                commits.append(
                    {
                        "sha": commit.hexsha,
                        "author": commit.author.name,
                        "email": commit.author.email,
                        "timestamp": commit.committed_datetime.isoformat(),
                        "message": commit.message.strip(),
                    }
                )

            return commits

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to get log: {e}")
            raise RuntimeError(f"Failed to get log: {e}") from e

    def _get_current_commit_sync(self, repo_path: str) -> str:
        """Sync implementation of get_current_commit."""
        try:
            repo = Repo(repo_path)
            return repo.head.commit.hexsha

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to get current commit: {e}")
            raise RuntimeError(f"Failed to get current commit: {e}") from e

    def _get_changed_files_sync(self, repo_path: str, from_commit: str, to_commit: str = "HEAD") -> list[str]:
        """Sync implementation of get_changed_files."""
        try:
            repo = Repo(repo_path)
            from_commit_obj = repo.commit(from_commit)
            to_commit_obj = repo.commit(to_commit)

            # Get diff between commits
            diffs = from_commit_obj.diff(to_commit_obj)

            # Collect all changed file paths
            changed_files = set()
            for diff_item in diffs:
                # Add both a_path (old) and b_path (new) to handle renames
                if diff_item.a_path:
                    changed_files.add(diff_item.a_path)
                if diff_item.b_path:
                    changed_files.add(diff_item.b_path)

            return sorted(changed_files)

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to get changed files: {e}")
            raise RuntimeError(f"Failed to get changed files: {e}") from e

    def _get_file_diff_sync(self, repo_path: str, file_path: str, from_commit: str, to_commit: str = "HEAD") -> str:
        """Sync implementation of get_file_diff."""
        try:
            repo = Repo(repo_path)
            from_commit_obj = repo.commit(from_commit)
            to_commit_obj = repo.commit(to_commit)

            # Get diff for specific file
            diffs = from_commit_obj.diff(to_commit_obj, paths=file_path)

            if not diffs:
                return ""

            # Return first diff (should only be one for single file)
            return diffs[0].diff.decode("utf-8")

        except (GitCommandError, Exception) as e:
            logger.error(f"Failed to get file diff: {e}")
            raise RuntimeError(f"Failed to get file diff: {e}") from e
