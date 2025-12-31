"""
Git Adapter Port (Hexagonal Architecture)

RFC-060 Section 4.2: Git Integration
- 커밋 생성
- 브랜치 관리
- PR 초안 생성
- Rollback 지원
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommitInfo:
    """커밋 정보 (Immutable Value Object)"""

    hash: str
    message: str
    author: str
    timestamp: str


@dataclass(frozen=True)
class BranchInfo:
    """브랜치 정보 (Immutable Value Object)"""

    name: str
    is_current: bool
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0


@dataclass(frozen=True)
class PRInfo:
    """Pull Request 정보 (Immutable Value Object)"""

    url: str
    number: int
    title: str
    is_draft: bool


class IGitAdapter(Protocol):
    """Git Adapter Port

    책임:
    - 파일 스테이징 및 커밋
    - 브랜치 생성/전환
    - PR 초안 생성 (gh CLI)
    - Rollback (git revert)
    """

    async def status(self) -> dict[str, list[str]]:
        """
        Git 상태 조회

        Returns:
            {
                "staged": [...],
                "modified": [...],
                "untracked": [...],
            }
        """
        ...

    async def stage(self, files: list[str]) -> bool:
        """파일 스테이징 (git add)"""
        ...

    async def commit(
        self,
        message: str,
        files: list[str] | None = None,
        auto_stage: bool = True,
    ) -> CommitInfo:
        """
        커밋 생성

        Args:
            message: 커밋 메시지
            files: 커밋할 파일 (None이면 스테이징된 파일)
            auto_stage: files가 주어지면 자동 스테이징

        Returns:
            CommitInfo: 생성된 커밋 정보
        """
        ...

    async def create_branch(
        self,
        name: str,
        checkout: bool = True,
    ) -> BranchInfo:
        """브랜치 생성"""
        ...

    async def checkout(self, branch: str) -> bool:
        """브랜치 전환"""
        ...

    async def current_branch(self) -> BranchInfo:
        """현재 브랜치 정보"""
        ...

    async def revert(
        self,
        commit_hash: str,
        no_commit: bool = False,
    ) -> bool:
        """커밋 되돌리기 (git revert)"""
        ...

    async def diff(
        self,
        staged: bool = False,
        file_path: str | None = None,
    ) -> str:
        """Diff 조회"""
        ...

    # ========== PR 관련 (gh CLI) ==========

    async def create_pr_draft(
        self,
        title: str,
        body: str,
        base: str = "main",
    ) -> PRInfo:
        """
        PR 초안 생성 (gh pr create --draft)

        Requires: gh CLI 설치 및 인증
        """
        ...

    async def is_gh_available(self) -> bool:
        """gh CLI 사용 가능 여부"""
        ...
