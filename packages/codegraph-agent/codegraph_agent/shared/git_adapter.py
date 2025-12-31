"""
Git Adapter

RFC-060 Section 4.2: Git Integration
- 커밋 생성
- 브랜치 관리
- PR 초안 생성 (gh CLI)
"""

import logging
import re

from codegraph_agent.ports.git import (
    BranchInfo,
    CommitInfo,
    IGitAdapter,
    PRInfo,
)
from codegraph_agent.ports.infrastructure import IInfraCommandExecutor

logger = logging.getLogger(__name__)


class GitAdapter(IGitAdapter):
    """
    Git Adapter 구현체

    책임:
    - Git 명령 실행 (commit, branch, checkout 등)
    - gh CLI로 PR 생성

    Dependency Injection:
    - executor: 명령 실행
    - cwd: Git 저장소 경로
    """

    def __init__(
        self,
        executor: IInfraCommandExecutor,
        cwd: str | None = None,
    ):
        self._executor = executor
        self._cwd = cwd

    async def status(self) -> dict[str, list[str]]:
        """Git 상태 조회"""
        result = await self._executor.execute(
            command=["git", "status", "--porcelain"],
            cwd=self._cwd,
            timeout=10.0,
        )

        staged: list[str] = []
        modified: list[str] = []
        untracked: list[str] = []

        for line in result.stdout.splitlines():
            if len(line) < 3:
                continue

            status_code = line[:2]
            file_path = line[3:]

            if status_code[0] in "MADRC":
                staged.append(file_path)
            if status_code[1] == "M":
                modified.append(file_path)
            if status_code == "??":
                untracked.append(file_path)

        return {
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
        }

    async def stage(self, files: list[str]) -> bool:
        """파일 스테이징"""
        if not files:
            return True

        result = await self._executor.execute(
            command=["git", "add", *files],
            cwd=self._cwd,
            timeout=10.0,
        )
        return result.is_success()

    async def commit(
        self,
        message: str,
        files: list[str] | None = None,
        auto_stage: bool = True,
    ) -> CommitInfo:
        """커밋 생성"""
        if files and auto_stage:
            await self.stage(files)

        result = await self._executor.execute(
            command=["git", "commit", "-m", message],
            cwd=self._cwd,
            timeout=30.0,
        )

        if not result.is_success():
            raise RuntimeError(f"Git commit failed: {result.stderr}")

        # 커밋 해시 가져오기
        hash_result = await self._executor.execute(
            command=["git", "rev-parse", "HEAD"],
            cwd=self._cwd,
            timeout=5.0,
        )
        commit_hash = hash_result.stdout.strip()

        # 커밋 정보 가져오기
        info_result = await self._executor.execute(
            command=[
                "git",
                "log",
                "-1",
                "--format=%an|%ai",
            ],
            cwd=self._cwd,
            timeout=5.0,
        )
        parts = info_result.stdout.strip().split("|")
        author = parts[0] if len(parts) > 0 else "unknown"
        timestamp = parts[1] if len(parts) > 1 else ""

        return CommitInfo(
            hash=commit_hash,
            message=message,
            author=author,
            timestamp=timestamp,
        )

    async def create_branch(
        self,
        name: str,
        checkout: bool = True,
    ) -> BranchInfo:
        """브랜치 생성"""
        if checkout:
            cmd = ["git", "checkout", "-b", name]
        else:
            cmd = ["git", "branch", name]

        result = await self._executor.execute(
            command=cmd,
            cwd=self._cwd,
            timeout=10.0,
        )

        if not result.is_success():
            raise RuntimeError(f"Failed to create branch: {result.stderr}")

        return BranchInfo(
            name=name,
            is_current=checkout,
            upstream=None,
        )

    async def checkout(self, branch: str) -> bool:
        """브랜치 전환"""
        result = await self._executor.execute(
            command=["git", "checkout", branch],
            cwd=self._cwd,
            timeout=10.0,
        )
        return result.is_success()

    async def current_branch(self) -> BranchInfo:
        """현재 브랜치 정보"""
        # 브랜치 이름
        result = await self._executor.execute(
            command=["git", "branch", "--show-current"],
            cwd=self._cwd,
            timeout=5.0,
        )
        name = result.stdout.strip()

        # Upstream 정보
        upstream_result = await self._executor.execute(
            command=[
                "git",
                "rev-parse",
                "--abbrev-ref",
                f"{name}@{{upstream}}",
            ],
            cwd=self._cwd,
            timeout=5.0,
        )
        upstream = upstream_result.stdout.strip() if upstream_result.is_success() else None

        # Ahead/Behind 계산
        ahead = 0
        behind = 0
        if upstream:
            count_result = await self._executor.execute(
                command=[
                    "git",
                    "rev-list",
                    "--left-right",
                    "--count",
                    f"{name}...{upstream}",
                ],
                cwd=self._cwd,
                timeout=5.0,
            )
            if count_result.is_success():
                parts = count_result.stdout.strip().split()
                if len(parts) == 2:
                    ahead = int(parts[0])
                    behind = int(parts[1])

        return BranchInfo(
            name=name,
            is_current=True,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
        )

    async def revert(
        self,
        commit_hash: str,
        no_commit: bool = False,
    ) -> bool:
        """커밋 되돌리기"""
        cmd = ["git", "revert"]
        if no_commit:
            cmd.append("--no-commit")
        cmd.append(commit_hash)

        result = await self._executor.execute(
            command=cmd,
            cwd=self._cwd,
            timeout=30.0,
        )
        return result.is_success()

    async def diff(
        self,
        staged: bool = False,
        file_path: str | None = None,
    ) -> str:
        """Diff 조회"""
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if file_path:
            cmd.append(file_path)

        result = await self._executor.execute(
            command=cmd,
            cwd=self._cwd,
            timeout=30.0,
        )
        return result.stdout

    # ========== PR 관련 (gh CLI) ==========

    async def create_pr_draft(
        self,
        title: str,
        body: str,
        base: str = "main",
    ) -> PRInfo:
        """PR 초안 생성"""
        if not await self.is_gh_available():
            raise RuntimeError("gh CLI not available")

        result = await self._executor.execute(
            command=[
                "gh",
                "pr",
                "create",
                "--draft",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base,
            ],
            cwd=self._cwd,
            timeout=60.0,
        )

        if not result.is_success():
            raise RuntimeError(f"Failed to create PR: {result.stderr}")

        # URL에서 PR 번호 추출
        url = result.stdout.strip()
        pr_number = 0
        match = re.search(r"/pull/(\d+)", url)
        if match:
            pr_number = int(match.group(1))

        return PRInfo(
            url=url,
            number=pr_number,
            title=title,
            is_draft=True,
        )

    async def is_gh_available(self) -> bool:
        """gh CLI 사용 가능 여부"""
        result = await self._executor.execute(
            command=["gh", "--version"],
            timeout=5.0,
        )
        return result.is_success()
