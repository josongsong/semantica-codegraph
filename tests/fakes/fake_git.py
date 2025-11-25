"""
Fake Git Provider for Unit Testing
"""

from typing import Any


class FakeGitProvider:
    """
    GitProviderPort Fake 구현.

    Git 명령 없이 동작.
    """

    def __init__(self):
        self.commits: list[dict[str, Any]] = []
        self.branches: list[str] = ["main"]
        self.current_branch: str = "main"

    def get_current_branch(self) -> str:
        """현재 브랜치."""
        return self.current_branch

    def get_commits(self, since: str | None = None) -> list[dict[str, Any]]:
        """커밋 리스트."""
        return self.commits

    def get_diff(self, commit1: str, commit2: str) -> list[str]:
        """Diff 파일 리스트."""
        return []

    def checkout(self, branch: str):
        """브랜치 체크아웃."""
        if branch in self.branches:
            self.current_branch = branch

    def add_fake_commit(self, commit_hash: str, message: str, files: list[str]):
        """테스트용 커밋 추가."""
        self.commits.append(
            {
                "hash": commit_hash,
                "message": message,
                "files": files,
            }
        )
