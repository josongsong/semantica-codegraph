"""
Git Repository Implementation (Infrastructure Layer)

PartialCommitter의 Infrastructure 구현체.
CASCADE Fuzzy Patcher 통합 포함.

Hexagonal Architecture:
- Domain에서 독립적
- IFuzzyPatcher Port 사용
- Infrastructure 세부사항 캡슐화
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
    commit_sha: str | None
    branch_name: str | None
    applied_files: list[str]
    errors: list[str]
    rollback_sha: str | None = None  # Rollback용 이전 commit

    def __post_init__(self):
        if self.applied_files is None:
            self.applied_files = []
        if self.errors is None:
            self.errors = []


class GitRepositoryImpl:
    """
    Git Repository Infrastructure Implementation (SOTA급).

    승인된 변경사항만 Git에 안전하게 적용합니다.

    CASCADE 통합:
    - Fuzzy Patcher fallback (git apply 실패 시)

    Hexagonal:
    - IFuzzyPatcher Port 의존
    - Domain 독립적
    """

    def __init__(self, repo_path: str = ".", fuzzy_patcher=None):
        """
        Args:
            repo_path: Repository 경로
            fuzzy_patcher: IFuzzyPatcher (Optional, CASCADE 통합)
        """
        self.repo_path = Path(repo_path)
        self.fuzzy_patcher = fuzzy_patcher  # CASCADE Fuzzy Patcher (Optional)

    async def apply_partial(
        self,
        approved_file_diffs: list,
        commit_message: str,
        branch_name: str | None = None,
        create_shadow: bool = True,
    ) -> PartialCommitResult:
        """
        승인된 변경사항만 부분 커밋.

        Flow:
        1. Shadow branch 생성 (Rollback 대비)
        2. Branch 생성/전환
        3. Patch 생성
        4. Patch 적용 (git apply → CASCADE Fuzzy fallback)
        5. Staging
        6. Commit

        Args:
            approved_file_diffs: 승인된 FileDiff 목록
            commit_message: 커밋 메시지
            branch_name: 브랜치 이름 (None이면 현재 브랜치)
            create_shadow: Shadow branch 생성 여부

        Returns:
            PartialCommitResult
        """
        applied_files = []
        errors = []
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

            # 4. Patch 적용 (git apply → CASCADE Fuzzy fallback)
            for file_path, patch in patches:
                try:
                    await self._apply_patch(patch, file_path=file_path)
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
                    await self._rollback_to_shadow(rollback_sha)
                    logger.info(f"Rolled back to shadow: {rollback_sha}")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                    errors.append(f"Rollback error: {rollback_error}")

            return PartialCommitResult(
                success=False,
                commit_sha=None,
                branch_name=branch_name,
                applied_files=applied_files,
                errors=errors,
                rollback_sha=rollback_sha,
            )

    # ========================================================================
    # CASCADE Integration: Fuzzy Patcher
    # ========================================================================

    async def _apply_patch(self, patch: str, file_path: str | None = None) -> None:
        """
        Patch 적용 (git apply → CASCADE Fuzzy fallback).

        Args:
            patch: Git patch 문자열
            file_path: 대상 파일 경로 (Optional, CASCADE Fuzzy용)

        Raises:
            RuntimeError: 적용 실패 시
        """
        # Temporary patch file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch)
            patch_file = f.name

        # DEBUG: Patch 내용 로깅
        logger.debug(f"Generated patch file: {patch_file}")
        logger.debug(f"Patch content:\n{patch}")

        try:
            # ================================================================
            # Step 1: git apply 시도
            # ================================================================
            # Note: --cached는 staged area에 적용하지만, 파일이 이미 committed되어 있으면
            # working tree에 먼저 적용하고 나중에 git add로 staging
            result = subprocess.run(
                ["git", "apply", patch_file],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                # ================================================================
                # Step 2: CASCADE Fuzzy Patcher fallback
                # ================================================================
                if self.fuzzy_patcher and file_path:
                    logger.warning(
                        f"git apply failed for {file_path}, trying CASCADE Fuzzy Patcher... (stderr: {result.stderr})"
                    )

                    try:
                        # Fuzzy Patcher 호출

                        # file_path를 절대 경로로 변환
                        abs_file_path = self.repo_path / file_path
                        if not abs_file_path.is_absolute():
                            abs_file_path = abs_file_path.resolve()

                        fuzzy_result = await self.fuzzy_patcher.apply_patch(
                            file_path=str(abs_file_path),
                            diff=patch,
                            fallback_to_fuzzy=True,
                        )

                        if fuzzy_result.is_success():
                            logger.info(
                                f"✅ CASCADE Fuzzy Patcher succeeded! "
                                f"(confidence={fuzzy_result.confidence_score():.2f}, "
                                f"status={fuzzy_result.status.value})"
                            )
                            # Fuzzy 성공 → 파일 수정됨 → git add 필요
                            # _stage_files()에서 처리하므로 여기서는 return만
                            return

                        logger.error(
                            f"CASCADE Fuzzy Patcher also failed: "
                            f"status={fuzzy_result.status.value}, "
                            f"conflicts={fuzzy_result.conflicts}"
                        )

                    except Exception as fuzzy_error:
                        logger.error(f"CASCADE Fuzzy Patcher error: {fuzzy_error}")

                # Fuzzy도 실패 → 원래 에러 발생
                raise RuntimeError(f"git apply failed (and fuzzy failed): {result.stderr}")

        finally:
            # Cleanup
            Path(patch_file).unlink(missing_ok=True)

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _create_shadow_branch(self) -> str:
        """
        Shadow branch 생성 (Rollback용).

        Returns:
            현재 commit SHA
        """
        # 현재 HEAD SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_sha = result.stdout.strip()

        # Shadow branch 생성
        import time

        shadow_branch = f"shadow-{int(time.time())}"

        subprocess.run(
            ["git", "branch", shadow_branch, commit_sha],
            cwd=self.repo_path,
            check=True,
        )

        logger.debug(f"Shadow branch created: {shadow_branch} at {commit_sha}")
        return commit_sha

    async def _checkout_or_create_branch(self, branch_name: str) -> None:
        """Branch 생성 또는 전환"""
        # Branch 존재 확인
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=self.repo_path,
            capture_output=True,
        )

        if result.returncode == 0:
            # 존재 → 전환
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=self.repo_path,
                check=True,
            )
        else:
            # 없음 → 생성 및 전환
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                check=True,
            )

    async def _stage_files(self, file_paths: list[str]) -> None:
        """파일 staging"""
        for file_path in file_paths:
            subprocess.run(
                ["git", "add", file_path],
                cwd=self.repo_path,
                check=True,
            )

    async def _create_commit(self, message: str) -> str:
        """Commit 생성 및 SHA 반환"""
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.repo_path,
            check=True,
        )

        # Commit SHA 조회
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    async def _rollback_to_shadow(self, commit_sha: str) -> None:
        """Shadow commit으로 롤백"""
        subprocess.run(
            ["git", "reset", "--hard", commit_sha],
            cwd=self.repo_path,
            check=True,
        )

    # ========================================================================
    # Public Interface (기존 PartialCommitter 호환)
    # ========================================================================

    async def rollback(self, rollback_sha: str) -> None:
        """
        롤백 (Public API).

        Args:
            rollback_sha: 롤백할 commit SHA
        """
        await self._rollback_to_shadow(rollback_sha)
