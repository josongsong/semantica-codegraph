"""
Git Helper Utilities

Utilities for Git operations during indexing.
"""

import subprocess
from pathlib import Path


class GitHelper:
    """Helper for Git operations."""

    def __init__(self, repo_path: str | Path):
        """
        Initialize Git helper.

        Args:
            repo_path: Path to the Git repository
        """
        self.repo_path = Path(repo_path)

    def is_git_repo(self) -> bool:
        """Check if the path is a Git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def get_current_commit_hash(self) -> str | None:
        """
        Get current commit hash.

        Returns:
            Commit hash or None if not a Git repo
        """
        if not self.is_git_repo():
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_current_branch(self) -> str | None:
        """
        Get current branch name.

        Returns:
            Branch name or None if not a Git repo
        """
        if not self.is_git_repo():
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_changed_files(
        self, since_commit: str | None = None, include_untracked: bool = True
    ) -> list[str]:
        """
        Get list of changed files.

        Args:
            since_commit: Compare changes since this commit (default: HEAD)
            include_untracked: Include untracked files

        Returns:
            List of file paths relative to repo root
        """
        if not self.is_git_repo():
            return []

        changed_files = set()

        try:
            # Get modified and staged files
            cmd = ["git", "diff", "--name-only"]
            if since_commit:
                cmd.append(since_commit)
            else:
                cmd.append("HEAD")

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files.update(result.stdout.strip().split("\n"))

            # Get staged files
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files.update(result.stdout.strip().split("\n"))

            # Get untracked files
            if include_untracked:
                result = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                changed_files.update(result.stdout.strip().split("\n"))

        except subprocess.CalledProcessError:
            pass

        # Filter out empty strings
        return [f for f in changed_files if f]

    def fetch(self) -> bool:
        """
        Fetch latest changes from remote.

        Returns:
            True if successful
        """
        if not self.is_git_repo():
            return False

        try:
            subprocess.run(
                ["git", "fetch"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def pull(self) -> bool:
        """
        Pull latest changes from remote.

        Returns:
            True if successful
        """
        if not self.is_git_repo():
            return False

        try:
            subprocess.run(
                ["git", "pull"],
                cwd=self.repo_path,
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def clone(self, repo_url: str, target_path: Path) -> bool:
        """
        Clone a Git repository.

        Args:
            repo_url: Repository URL
            target_path: Target directory path

        Returns:
            True if successful
        """
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                ["git", "clone", repo_url, str(target_path)],
                capture_output=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def get_file_last_modified_commit(self, file_path: str) -> str | None:
        """
        Get the last commit that modified a file.

        Args:
            file_path: Path to file relative to repo root

        Returns:
            Commit hash or None
        """
        if not self.is_git_repo():
            return None

        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", file_path],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_repo_info(self) -> dict:
        """
        Get repository information.

        Returns:
            Dictionary with repo info
        """
        return {
            "is_git_repo": self.is_git_repo(),
            "current_commit": self.get_current_commit_hash(),
            "current_branch": self.get_current_branch(),
            "repo_path": str(self.repo_path),
        }
