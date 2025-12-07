"""Git Manager

Git 버전 관리 (ADR-018)

기능:
- Branch 생성
- Commit 관리
- Diff 조회
- Rollback
"""

import subprocess
from datetime import datetime
from pathlib import Path

from src.common.observability import get_logger

from .models import CommitInfo

logger = get_logger(__name__)


class GitManager:
    """
    Git 통합

    기능:
    1. 브랜치 생성
    2. 변경사항 커밋
    3. Diff 확인
    4. Rollback
    """

    def __init__(self, workspace: Path):
        """
        Initialize GitManager

        Args:
            workspace: Git 저장소 경로
        """
        self.workspace = Path(workspace)

        # Git 저장소 확인
        git_dir = self.workspace / ".git"
        if not git_dir.exists():
            logger.warning(f"Not a git repository: {workspace}")
            self.is_git_repo = False
        else:
            self.is_git_repo = True
            logger.info(f"GitManager initialized: {workspace}")

    def create_branch(self, branch_name: str, from_branch: str | None = None) -> str:
        """
        새 브랜치 생성

        Args:
            branch_name: 브랜치 이름
            from_branch: 기준 브랜치 (None이면 현재 브랜치)

        Returns:
            생성된 브랜치 이름
        """
        if not self.is_git_repo:
            logger.warning("Not a git repo, skipping branch creation")
            return branch_name

        try:
            # 기준 브랜치 체크아웃 (필요시)
            if from_branch:
                self._run_git(["checkout", from_branch])

            # 새 브랜치 생성 및 체크아웃
            self._run_git(["checkout", "-b", branch_name])

            logger.info(f"Created branch: {branch_name}")
            return branch_name

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create branch: {e}")
            raise

    def commit_changes(self, message: str, files: list[str] | None = None, author: str | None = None) -> CommitInfo:
        """
        변경사항 커밋

        Args:
            message: 커밋 메시지
            files: 커밋할 파일 목록 (None이면 모든 변경사항)
            author: 작성자 (None이면 git config)

        Returns:
            CommitInfo
        """
        if not self.is_git_repo:
            logger.warning("Not a git repo, skipping commit")
            return self._create_mock_commit(message, files or [])

        try:
            # Stage files
            if files:
                for file in files:
                    self._run_git(["add", str(file)])
            else:
                self._run_git(["add", "-A"])

            # Commit
            commit_args = ["commit", "-m", message]
            if author:
                commit_args.extend(["--author", f"{author} <{author}@agent.local>"])

            self._run_git(commit_args)

            # Get commit info
            commit_hash = self._run_git(["rev-parse", "HEAD"]).strip()
            branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()

            commit_info = CommitInfo(
                hash=commit_hash,
                message=message,
                author=author or "Agent",
                timestamp=datetime.now(),
                branch=branch,
                files_changed=files or self._get_changed_files(),
            )

            logger.info(f"Committed: {commit_info}")
            return commit_info

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to commit: {e}")
            raise

    def get_diff(self, commit_hash: str | None = None, file_path: str | None = None) -> str:
        """
        Diff 조회

        Args:
            commit_hash: 커밋 해시 (None이면 HEAD)
            file_path: 특정 파일 (None이면 모든 파일)

        Returns:
            Diff 문자열
        """
        if not self.is_git_repo:
            logger.warning("Not a git repo, returning empty diff")
            return ""

        try:
            args = ["diff"]

            if commit_hash:
                args.extend([f"{commit_hash}^", commit_hash])

            if file_path:
                args.append(str(file_path))

            diff = self._run_git(args)

            logger.debug(f"Got diff: {len(diff)} chars")
            return diff

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get diff: {e}")
            return ""

    def rollback_to(self, commit_hash: str, hard: bool = False):
        """
        특정 커밋으로 롤백

        Args:
            commit_hash: 롤백할 커밋 해시
            hard: Hard reset (True) vs Soft reset (False)
        """
        if not self.is_git_repo:
            logger.warning("Not a git repo, skipping rollback")
            return

        try:
            reset_type = "--hard" if hard else "--soft"
            self._run_git(["reset", reset_type, commit_hash])

            logger.info(f"Rolled back to {commit_hash} ({reset_type})")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to rollback: {e}")
            raise

    def get_current_branch(self) -> str:
        """현재 브랜치 조회"""
        if not self.is_git_repo:
            return "main"

        try:
            branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
            return branch
        except subprocess.CalledProcessError:
            return "main"

    def get_commit_history(self, limit: int = 10) -> list[CommitInfo]:
        """커밋 히스토리 조회"""
        if not self.is_git_repo:
            return []

        try:
            # git log --pretty=format:"%H|%s|%an|%at" -n {limit}
            log = self._run_git(["log", "--pretty=format:%H|%s|%an|%at", f"-n{limit}"])

            commits = []
            for line in log.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|")
                if len(parts) >= 4:
                    commit_info = CommitInfo(
                        hash=parts[0],
                        message=parts[1],
                        author=parts[2],
                        timestamp=datetime.fromtimestamp(int(parts[3])),
                        branch=self.get_current_branch(),
                        files_changed=[],
                    )
                    commits.append(commit_info)

            return commits

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get commit history: {e}")
            return []

    def _run_git(self, args: list[str]) -> str:
        """
        Git 명령 실행

        Args:
            args: Git 명령 인자

        Returns:
            출력
        """
        cmd = ["git", "-C", str(self.workspace)] + args

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        return result.stdout

    def _get_changed_files(self) -> list[str]:
        """변경된 파일 목록 조회"""
        try:
            output = self._run_git(["diff", "--name-only", "HEAD"])
            return [f.strip() for f in output.split("\n") if f.strip()]
        except subprocess.CalledProcessError:
            return []

    def _create_mock_commit(self, message: str, files: list[str]) -> CommitInfo:
        """Mock 커밋 정보 생성 (Git repo 없을 때)"""
        return CommitInfo(
            hash="0000000000000000000000000000000000000000",
            message=message,
            author="Agent",
            timestamp=datetime.now(),
            branch="main",
            files_changed=files,
        )
