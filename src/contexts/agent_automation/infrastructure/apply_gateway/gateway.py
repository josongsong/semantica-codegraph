"""Apply Gateway - Centralized patch application."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.contexts.agent_automation.infrastructure.exceptions import PatchApplyError
from src.contexts.agent_automation.infrastructure.queue.models import PatchProposal
from src.contexts.agent_automation.infrastructure.queue.patch_queue import PatchQueue
from src.contexts.agent_automation.infrastructure.tools.conflict_resolver import PatchConflictResolver
from src.infra.observability import get_logger

from .rollback import RollbackManager

logger = get_logger(__name__)


@dataclass
class ApplyResult:
    """Result of patch application."""

    success: bool
    patch_id: str
    file_path: str
    had_conflict: bool = False
    conflict_resolved: bool = False
    error_message: str | None = None
    formatted: bool = False
    linted: bool = False


class ApplyGateway:
    """Central gateway for safe patch application.

    Provides:
    - Conflict detection and resolution
    - Automatic rollback on failure
    - Format/lint integration (optional)
    - All-or-nothing guarantees for batch operations
    """

    def __init__(
        self,
        patch_queue: PatchQueue,
        conflict_resolver: PatchConflictResolver,
        rollback_manager: RollbackManager | None = None,
        auto_format: bool = True,
        auto_lint: bool = False,
    ):
        """Initialize apply gateway.

        Args:
            patch_queue: Patch queue
            conflict_resolver: Conflict resolver
            rollback_manager: Rollback manager (default: creates new one)
            auto_format: Run ruff format after apply
            auto_lint: Run ruff check --fix after apply
        """
        self.patch_queue = patch_queue
        self.conflict_resolver = conflict_resolver
        self.rollback_manager = rollback_manager or RollbackManager()
        self.auto_format = auto_format
        self.auto_lint = auto_lint

    async def apply_next(self, repo_id: str, repo_path: Path) -> ApplyResult | None:
        """Apply the next pending patch from queue.

        Args:
            repo_id: Repository ID
            repo_path: Repository root path

        Returns:
            ApplyResult or None if queue empty
        """
        # Get next patch
        patch = await self.patch_queue.dequeue(repo_id)
        if not patch:
            return None

        return await self.apply_patch(patch, repo_path)

    async def apply_patch(self, patch: PatchProposal, repo_path: Path) -> ApplyResult:
        """Apply a single patch.

        Args:
            patch: Patch to apply
            repo_path: Repository root path

        Returns:
            ApplyResult
        """
        file_path = repo_path / patch.file_path

        # Backup file
        self.rollback_manager.backup_file(file_path)

        try:
            # Read current content
            current_content = file_path.read_text() if file_path.exists() else ""

            # Check for conflicts
            has_conflict, conflict_details = await self.patch_queue.detect_conflicts(patch, current_content)

            if has_conflict:
                logger.warning(
                    "patch_conflict_detected",
                    patch_id=patch.patch_id,
                    conflict_type=conflict_details.get("type") if conflict_details else None,
                )

                # Try to resolve conflict using 3-way merge
                merge_result = self.conflict_resolver.merge_3way(
                    base=patch.base_content or "",
                    ours=current_content,
                    theirs=self._apply_diff(current_content, patch.patch_content),
                )

                if merge_result.success:
                    # Conflict resolved
                    file_path.write_text(merge_result.content)
                    await self.patch_queue.mark_applied(patch.patch_id)

                    result = ApplyResult(
                        success=True,
                        patch_id=patch.patch_id,
                        file_path=patch.file_path,
                        had_conflict=True,
                        conflict_resolved=True,
                    )
                else:
                    # Conflict unresolved
                    await self.patch_queue.mark_conflict(patch.patch_id, conflict_details or {})
                    self.rollback_manager.rollback()

                    return ApplyResult(
                        success=False,
                        patch_id=patch.patch_id,
                        file_path=patch.file_path,
                        had_conflict=True,
                        conflict_resolved=False,
                        error_message="Conflict could not be resolved",
                    )
            else:
                # No conflict, apply directly
                new_content = self._apply_diff(current_content, patch.patch_content)
                file_path.write_text(new_content)
                await self.patch_queue.mark_applied(patch.patch_id)

                result = ApplyResult(
                    success=True,
                    patch_id=patch.patch_id,
                    file_path=patch.file_path,
                )

            # Format if enabled
            if self.auto_format and file_path.suffix == ".py":
                formatted = await self._run_formatter(file_path)
                result.formatted = formatted

            # Lint if enabled
            if self.auto_lint and file_path.suffix == ".py":
                linted = await self._run_linter(file_path)
                result.linted = linted

            # Commit backup
            self.rollback_manager.commit()

            logger.info(
                "patch_applied",
                patch_id=patch.patch_id,
                file_path=patch.file_path,
                had_conflict=result.had_conflict,
                formatted=result.formatted,
            )

            return result

        except Exception as e:
            logger.error(
                "patch_apply_failed",
                patch_id=patch.patch_id,
                file_path=patch.file_path,
                error=str(e),
            )

            # Rollback on error
            self.rollback_manager.rollback()
            await self.patch_queue.mark_failed(patch.patch_id, str(e))

            return ApplyResult(
                success=False,
                patch_id=patch.patch_id,
                file_path=patch.file_path,
                error_message=str(e),
            )

    async def apply_batch(
        self,
        repo_id: str,
        repo_path: Path,
        max_patches: int = 100,
    ) -> list[ApplyResult]:
        """Apply multiple patches with all-or-nothing guarantee.

        Args:
            repo_id: Repository ID
            repo_path: Repository root path
            max_patches: Maximum patches to apply

        Returns:
            List of ApplyResults
        """
        patches = await self.patch_queue.peek(repo_id, count=max_patches)
        results = []
        rollback_manager = RollbackManager()

        try:
            for patch in patches:
                # Use shared rollback manager for all patches
                old_manager = self.rollback_manager
                self.rollback_manager = rollback_manager

                result = await self.apply_patch(patch, repo_path)
                results.append(result)

                self.rollback_manager = old_manager

                if not result.success:
                    # One failed, rollback all
                    logger.warning(
                        "batch_apply_failed_rolling_back",
                        failed_patch=patch.patch_id,
                        total_patches=len(patches),
                    )
                    rollback_manager.rollback()
                    break

            if all(r.success for r in results):
                # All succeeded, commit
                rollback_manager.commit()
                logger.info("batch_apply_success", count=len(results))
            else:
                logger.error("batch_apply_failed", count=len(results))

            return results

        except Exception as e:
            logger.error("batch_apply_exception", error=str(e))
            rollback_manager.rollback()
            raise

    def _apply_diff(self, original_content: str, patch_content: str) -> str:
        """Apply unified diff to content using diff-match-patch.

        Args:
            original_content: Original file content
            patch_content: Unified diff

        Returns:
            Patched content

        Raises:
            PatchApplyError: If patch application fails
        """
        result = self.conflict_resolver.apply_patch_text(
            target=original_content,
            patch_text=patch_content,
        )

        if result.success:
            return result.content
        else:
            raise PatchApplyError(f"Failed to apply patch: {result.message}")

    async def _run_formatter(self, file_path: Path) -> bool:
        """Run ruff format on file.

        Args:
            file_path: File to format

        Returns:
            True if formatted successfully
        """
        try:
            result = subprocess.run(
                ["ruff", "format", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("format_failed", file_path=str(file_path), error=str(e))
            return False

    async def _run_linter(self, file_path: Path) -> bool:
        """Run ruff check --fix on file.

        Args:
            file_path: File to lint

        Returns:
            True if linted successfully
        """
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("lint_failed", file_path=str(file_path), error=str(e))
            return False
