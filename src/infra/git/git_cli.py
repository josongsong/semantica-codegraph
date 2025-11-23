"""
Git CLI Adapter (stub)

Provides basic shapes for git operations. Replace with actual git CLI/lib calls.
"""

from typing import Any


class GitCLIAdapter:
    """Placeholder adapter for Git operations."""

    def clone(self, repo_url: str, dest_path: str) -> None:
        raise NotImplementedError("GitCLIAdapter.clone is not implemented yet")

    def fetch(self, repo_path: str) -> None:
        raise NotImplementedError("GitCLIAdapter.fetch is not implemented yet")

    def list_branches(self, repo_path: str) -> list[str]:
        raise NotImplementedError("GitCLIAdapter.list_branches is not implemented yet")

    def show_file(self, repo_path: str, commit: str, file_path: str) -> str:
        raise NotImplementedError("GitCLIAdapter.show_file is not implemented yet")

    def log(self, repo_path: str, max_count: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError("GitCLIAdapter.log is not implemented yet")
