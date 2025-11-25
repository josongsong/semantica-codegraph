"""
Git File Loader

Provides utilities for loading file contents from Git at specific commits.
"""

import subprocess
from pathlib import Path


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
            FileNotFoundError: If file doesn't exist at commit
            subprocess.CalledProcessError: If git command fails
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
            if "does not exist" in e.stderr or "Path" in e.stderr:
                raise FileNotFoundError(f"File '{file_path}' not found at commit '{commit}': {e.stderr}") from e
            raise

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
        """
        result = subprocess.run(
            ["git", "diff", old_commit, new_commit, "--", file_path],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def get_current_commit(self) -> str:
        """
        Get current HEAD commit hash.

        Returns:
            Full commit hash
        """
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()


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
