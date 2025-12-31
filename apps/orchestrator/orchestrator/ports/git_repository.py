"""
Git Repository Port (Domain Interface)

Domain이 Git 작업을 요청하는 인터페이스.
Infrastructure가 구현.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PartialCommitResult:
    """Partial commit 결과"""

    success: bool
    commit_sha: str | None = None
    branch_name: str | None = None
    applied_files: list[str] | None = None
    errors: list[str] | None = None
    rollback_sha: str | None = None

    def __post_init__(self):
        if self.applied_files is None:
            self.applied_files = []
        if self.errors is None:
            self.errors = []


class IGitRepository(ABC):
    """
    Git Repository Port (헥사고날 아키텍처)

    Domain이 정의하는 Git 작업 인터페이스.
    Infrastructure가 구현 (GitPython, subprocess 등).
    """

    @abstractmethod
    async def apply_partial(
        self,
        approved_file_diffs,
        commit_message: str,
        branch_name: str | None = None,
        create_shadow: bool = True,
    ) -> PartialCommitResult:
        """
        승인된 변경사항만 적용 및 커밋.

        Args:
            approved_file_diffs: 승인된 FileDiff 리스트
            commit_message: Commit 메시지
            branch_name: 브랜치 이름 (None = 현재 브랜치)
            create_shadow: Shadow branch 생성 여부 (rollback용)

        Returns:
            PartialCommitResult
        """
        pass

    @abstractmethod
    async def rollback_to_shadow(self, shadow_sha: str) -> None:
        """
        Shadow branch로 rollback.

        Args:
            shadow_sha: Shadow branch의 commit SHA
        """
        pass

    @abstractmethod
    async def create_pr(
        self,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> str | None:
        """
        PR 생성 (GitHub CLI).

        Args:
            branch_name: PR 브랜치
            title: PR 제목
            body: PR 본문
            base_branch: Base 브랜치

        Returns:
            PR URL or None
        """
        pass

    @abstractmethod
    def get_current_branch(self) -> str:
        """현재 브랜치 이름"""
        pass

    @abstractmethod
    def has_uncommitted_changes(self) -> bool:
        """Uncommitted 변경사항 존재 여부"""
        pass
