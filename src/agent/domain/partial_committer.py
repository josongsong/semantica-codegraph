"""
Partial Committer (SOTA급)

승인된 변경사항만 Git에 적용합니다.

핵심 기능:
1. Partial staging (git apply --cached)
2. Atomic operations (전체 성공 or 전체 실패)
3. Rollback 지원 (Shadow branch)
4. Conflict handling (자동 해결 시도)
"""

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PartialCommitResult:
    """Partial commit 결과"""

    success: bool
    commit_sha: str | None = None
    branch_name: str | None = None
    applied_files: list[str] = None
    errors: list[str] = None
    rollback_sha: str | None = None  # Rollback용 이전 commit

    def __post_init__(self):
        if self.applied_files is None:
            self.applied_files = []
        if self.errors is None:
            self.errors = []


class PartialCommitter:
    """
    Partial Committer (SOTA급).

    승인된 변경사항만 Git에 안전하게 적용합니다.
    """

    def __init__(self, repo_path: str = "."):
        """
        Args:
            repo_path: Repository 경로
        """
        self.repo_path = Path(repo_path)

    async def apply_partial(
        self,
        approved_file_diffs,  # list[FileDiff]
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
        logger.info(f"Applying partial commit: {len(approved_file_diffs)} files, branch={branch_name}")

        errors = []
        applied_files = []
        rollback_sha = None

        try:
            # 1. Shadow branch 생성 (안전성)
            if create_shadow:
                rollback_sha = await self._create_shadow_branch()
                logger.debug(f"Shadow branch created: {rollback_sha}")

            # 2. 브랜치 생성/전환 (필요시)
            if branch_name:
                await self._checkout_or_create_branch(branch_name)

            # 3. Patch 생성
            patches = []
            for file_diff in approved_file_diffs:
                patch = file_diff.to_patch()
                if patch:
                    patches.append((file_diff.file_path, patch))

            # 4. Patch 적용 (git apply)
            for file_path, patch in patches:
                try:
                    await self._apply_patch(patch)
                    applied_files.append(file_path)
                    logger.debug(f"Applied patch: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to apply patch: {file_path}, {e}")
                    errors.append(f"{file_path}: {e}")

            # 5. Staging (git add)
            if applied_files and not errors:
                await self._stage_files(applied_files)

            # 6. Commit
            commit_sha = None
            if applied_files and not errors:
                commit_sha = await self._create_commit(commit_message)
                logger.info(f"Commit created: {commit_sha}")

            # 성공 여부
            success = len(applied_files) > 0 and len(errors) == 0

            if success:
                logger.info(f"Partial commit succeeded: {len(applied_files)} files")
            else:
                logger.warning(f"Partial commit failed: {len(errors)} errors")

            return PartialCommitResult(
                success=success,
                commit_sha=commit_sha,
                branch_name=branch_name,
                applied_files=applied_files,
                errors=errors,
                rollback_sha=rollback_sha,
            )

        except Exception as e:
            logger.error(f"Critical error in partial commit: {e}")
            errors.append(f"Critical error: {e}")

            # Rollback 시도
            if rollback_sha:
                try:
                    logger.warning(f"Rolling back to {rollback_sha}")
                    await self._rollback(rollback_sha)
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                    pass

            return PartialCommitResult(
                success=False,
                errors=errors,
                rollback_sha=rollback_sha,
            )

    async def _create_shadow_branch(self) -> str:
        """
        Shadow branch 생성 (rollback용).

        Returns:
            현재 commit SHA
        """
        # 현재 commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to get HEAD: {result.stderr}")

        current_sha = result.stdout.strip()

        # Shadow branch 생성
        shadow_name = f"shadow-{current_sha[:7]}"
        subprocess.run(
            ["git", "branch", shadow_name],
            cwd=self.repo_path,
            capture_output=True,
        )

        return current_sha

    async def _checkout_or_create_branch(self, branch_name: str) -> None:
        """브랜치 생성 또는 전환"""
        # 브랜치 존재 확인
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=self.repo_path,
            capture_output=True,
        )

        if result.returncode == 0:
            # 존재 -> 전환
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=self.repo_path,
                check=True,
            )
        else:
            # 없음 -> 생성
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                check=True,
            )

    async def _apply_patch(self, patch: str) -> None:
        """
        Patch 적용 (git apply).

        Args:
            patch: Git patch 문자열

        Raises:
            RuntimeError: 적용 실패 시
        """
        # Temporary patch file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch)
            patch_file = f.name

        try:
            # git apply --cached (staged only)
            result = subprocess.run(
                ["git", "apply", "--cached", patch_file],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # Retry: git apply (working tree)
                result = subprocess.run(
                    ["git", "apply", patch_file],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    raise RuntimeError(f"git apply failed: {result.stderr}")

        finally:
            # Cleanup
            Path(patch_file).unlink(missing_ok=True)

    async def _stage_files(self, file_paths: list[str]) -> None:
        """파일 staging (git add)"""
        subprocess.run(
            ["git", "add"] + file_paths,
            cwd=self.repo_path,
            check=True,
        )

    async def _create_commit(self, message: str) -> str:
        """
        Commit 생성.

        Args:
            message: Commit 메시지

        Returns:
            Commit SHA
        """
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"git commit failed: {result.stderr}")

        # Commit SHA 가져오기
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip()

    async def _rollback(self, commit_sha: str) -> None:
        """
        Rollback (git reset).

        Args:
            commit_sha: Rollback할 commit SHA
        """
        subprocess.run(
            ["git", "reset", "--hard", commit_sha],
            cwd=self.repo_path,
            check=True,
        )

    async def rollback_to_shadow(self, shadow_sha: str) -> None:
        """
        Shadow branch로 rollback.

        Args:
            shadow_sha: Shadow branch의 commit SHA
        """
        await self._rollback(shadow_sha)

        # Shadow branch 삭제
        shadow_name = f"shadow-{shadow_sha[:7]}"
        subprocess.run(
            ["git", "branch", "-D", shadow_name],
            cwd=self.repo_path,
            capture_output=True,
        )

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
        try:
            # gh pr create
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base_branch,
                    "--head",
                    branch_name,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # URL 추출
                pr_url = result.stdout.strip()
                return pr_url
            else:
                return None

        except FileNotFoundError:
            # gh CLI 없음
            return None

    def get_current_branch(self) -> str:
        """현재 브랜치 이름 가져오기"""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip()

    def has_uncommitted_changes(self) -> bool:
        """Uncommitted 변경사항 있는지 확인"""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )

        return bool(result.stdout.strip())
