"""
Patch Tools

코드 패치 제안 및 적용 도구.

기능:
- ProposePatchTool: 코드 변경 제안 생성 (diff 포함)
- ApplyPatchTool: 제안된 패치 적용 (충돌 감지 및 해결 지원)

충돌 해결:
- 패치 적용 시 파일이 변경되었으면 3-way merge 시도
- 자동 병합 실패 시 충돌 마커와 함께 반환
"""

import ast
import difflib
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import (
    ApplyPatchInput,
    ApplyPatchOutput,
    ConflictInfo,
    ProposePatchInput,
    ProposePatchOutput,
)
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool
from src.contexts.agent_automation.infrastructure.tools.conflict_resolver import PatchConflictResolver

logger = get_logger(__name__)


class PatchStore:
    """
    패치 저장소 (in-memory).

    실제 프로덕션에서는 DB나 파일시스템에 저장할 수 있습니다.
    """

    def __init__(self):
        self.patches: dict[str, dict[str, Any]] = {}

    def save_patch(
        self,
        patch_id: str,
        path: str,
        start_line: int,
        end_line: int,
        new_code: str,
        description: str,
        original_code: str,
        base_content: str | None = None,
    ) -> None:
        """Save patch to store.

        Args:
            patch_id: Unique patch identifier
            path: File path
            start_line: Start line (1-based)
            end_line: End line (1-based, inclusive)
            new_code: New code to replace
            description: Patch description
            original_code: Original code being replaced
            base_content: Full file content at patch creation time (for conflict resolution)
        """
        self.patches[patch_id] = {
            "patch_id": patch_id,
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "new_code": new_code,
            "description": description,
            "original_code": original_code,
            "base_content": base_content,  # 충돌 해결용 원본 전체 내용
            "created_at": time.time(),
        }

    def get_patch(self, patch_id: str) -> dict[str, Any] | None:
        """Get patch from store."""
        return self.patches.get(patch_id)

    def delete_patch(self, patch_id: str) -> None:
        """Delete patch from store."""
        self.patches.pop(patch_id, None)


# Global patch store (shared across instances)
_patch_store = PatchStore()


class ProposePatchTool(BaseTool[ProposePatchInput, ProposePatchOutput]):
    """
    패치 제안 도구.

    파일의 특정 영역을 변경하는 패치를 생성하고 diff를 보여줍니다.
    """

    name = "propose_patch"
    description = "Create a code change proposal with unified diff"
    input_schema = ProposePatchInput
    output_schema = ProposePatchOutput

    def __init__(
        self,
        base_path: str | Path = ".",
        patch_queue=None,
        repo_id: str | None = None,
        index_version_id: int | None = None,
    ):
        """
        Initialize propose patch tool.

        Args:
            base_path: Base directory for file operations
            patch_queue: PatchQueue 인스턴스 (옵션, P0-2)
            repo_id: 저장소 ID (옵션)
            index_version_id: 인덱스 버전 ID (옵션)
        """
        super().__init__()
        self.base_path = Path(base_path)
        self.patch_store = _patch_store  # Fallback to in-memory
        self.patch_queue = patch_queue
        self.repo_id = repo_id
        self.index_version_id = index_version_id

    async def _execute(self, input_data: ProposePatchInput) -> ProposePatchOutput:
        """
        Execute patch proposal.

        Args:
            input_data: Patch parameters

        Returns:
            Patch proposal with diff
        """
        try:
            file_path = self.base_path / input_data.path

            # Check file exists
            if not file_path.exists():
                return ProposePatchOutput(
                    success=False,
                    path=input_data.path,
                    error=f"File not found: {input_data.path}",
                )

            # Read file
            try:
                content = file_path.read_text()
                lines = content.splitlines(keepends=True)
            except Exception as e:
                return ProposePatchOutput(
                    success=False,
                    path=input_data.path,
                    error=f"Failed to read file: {e}",
                )

            # Validate line range
            if input_data.start_line < 1 or input_data.end_line > len(lines):
                return ProposePatchOutput(
                    success=False,
                    path=input_data.path,
                    error=f"Invalid line range: {input_data.start_line}-{input_data.end_line} "
                    f"(file has {len(lines)} lines)",
                )

            if input_data.start_line > input_data.end_line:
                return ProposePatchOutput(
                    success=False,
                    path=input_data.path,
                    error=f"start_line ({input_data.start_line}) > end_line ({input_data.end_line})",
                )

            # Extract original code
            original_lines = lines[input_data.start_line - 1 : input_data.end_line]
            original_code = "".join(original_lines)

            # Create new content
            new_code_lines = input_data.new_code.splitlines(keepends=True)
            if new_code_lines and not new_code_lines[-1].endswith("\n"):
                new_code_lines[-1] += "\n"

            new_lines = lines[: input_data.start_line - 1] + new_code_lines + lines[input_data.end_line :]

            # Generate diff
            diff = "".join(
                difflib.unified_diff(
                    lines,
                    new_lines,
                    fromfile=f"a/{input_data.path}",
                    tofile=f"b/{input_data.path}",
                    lineterm="",
                )
            )

            # Validation
            validation = self._validate_patch(input_data.path, new_lines)

            # Generate patch ID
            patch_id = str(uuid.uuid4())

            # Save patch to queue (if available) or fallback to in-memory store
            if self.patch_queue and self.repo_id:
                # P0-2: Use PatchQueue
                "".join(new_lines)
                queued_patch = await self.patch_queue.enqueue(
                    repo_id=self.repo_id,
                    file_path=input_data.path,
                    patch_content=diff,  # Use unified diff format
                    base_content=content,
                    index_version_id=self.index_version_id,
                    description=input_data.description,
                )
                patch_id = queued_patch.patch_id
                logger.info(f"Patch enqueued to PatchQueue: id={patch_id}")
            else:
                # Fallback: in-memory store (legacy)
                self.patch_store.save_patch(
                    patch_id=patch_id,
                    path=input_data.path,
                    start_line=input_data.start_line,
                    end_line=input_data.end_line,
                    new_code=input_data.new_code,
                    description=input_data.description,
                    original_code=original_code,
                    base_content=content,
                )
                logger.info(f"Patch saved to in-memory store: id={patch_id}")

            return ProposePatchOutput(
                success=True,
                patch_id=patch_id,
                path=input_data.path,
                diff=diff,
                validation=validation,
            )

        except Exception as e:
            logger.error(f"Patch proposal failed: {e}", exc_info=True)
            return ProposePatchOutput(
                success=False,
                path=input_data.path,
                error=str(e),
            )

    def _validate_patch(self, path: str, new_lines: list[str]) -> dict[str, Any]:
        """Validate the patched code."""
        validation: dict[str, Any] = {
            "syntax_valid": True,
            "warnings": [],
        }

        # Python syntax check
        if path.endswith(".py"):
            try:
                code = "".join(new_lines)
                ast.parse(code)
                validation["syntax_valid"] = True
            except SyntaxError as e:
                validation["syntax_valid"] = False
                validation["warnings"].append(f"Syntax error: {e}")

        return validation


class ApplyPatchTool(BaseTool[ApplyPatchInput, ApplyPatchOutput]):
    """
    패치 적용 도구.

    제안된 패치를 실제 파일에 적용합니다.
    파일이 변경된 경우 3-way merge를 시도합니다.
    """

    name = "apply_patch"
    description = "Apply a proposed patch to a file (with optional dry-run and conflict resolution)"
    input_schema = ApplyPatchInput
    output_schema = ApplyPatchOutput

    def __init__(self, base_path: str | Path = "."):
        """
        Initialize apply patch tool.

        Args:
            base_path: Base directory for file operations
        """
        super().__init__()
        self.base_path = Path(base_path)
        self.patch_store = _patch_store
        self.conflict_resolver = PatchConflictResolver()

    async def _execute(self, input_data: ApplyPatchInput) -> ApplyPatchOutput:
        """
        Execute patch application.

        Args:
            input_data: Patch application parameters

        Returns:
            Patch application result
        """
        try:
            # Get patch
            patch = self.patch_store.get_patch(input_data.patch_id)
            if not patch:
                return ApplyPatchOutput(
                    success=False,
                    patch_id=input_data.patch_id,
                    path="",
                    error=f"Patch not found: {input_data.patch_id}",
                )

            file_path = self.base_path / patch["path"]

            # Check file exists
            if not file_path.exists():
                return ApplyPatchOutput(
                    success=False,
                    patch_id=input_data.patch_id,
                    path=patch["path"],
                    error=f"File not found: {patch['path']}",
                )

            # Dry run - just validate
            if input_data.dry_run:
                return ApplyPatchOutput(
                    success=True,
                    patch_id=input_data.patch_id,
                    applied=False,
                    path=patch["path"],
                )

            # Read current file content
            try:
                current_content = file_path.read_text()
            except Exception as e:
                return ApplyPatchOutput(
                    success=False,
                    patch_id=input_data.patch_id,
                    path=patch["path"],
                    error=f"Failed to read file: {e}",
                )

            # Create backup
            backup_path = file_path.with_suffix(file_path.suffix + ".backup")
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")
                backup_path = None

            # Check if file was modified since patch creation
            base_content = patch.get("base_content")
            start_line = patch["start_line"]
            end_line = patch["end_line"]
            new_code = patch["new_code"]

            try:
                # Build proposed content (what the file would look like after patch)
                if base_content:
                    base_lines = base_content.splitlines(keepends=True)
                else:
                    # Fallback: use current content as base
                    base_lines = current_content.splitlines(keepends=True)

                new_code_lines = new_code.splitlines(keepends=True)
                if new_code_lines and not new_code_lines[-1].endswith("\n"):
                    new_code_lines[-1] += "\n"

                proposed_lines = base_lines[: start_line - 1] + new_code_lines + base_lines[end_line:]
                proposed_content = "".join(proposed_lines)

                # Check if file was modified
                if base_content and base_content != current_content:
                    # File was modified - need 3-way merge
                    logger.info(
                        "file_modified_since_patch",
                        path=patch["path"],
                        attempting="3-way merge",
                    )

                    merge_result = self.conflict_resolver.merge_3way(
                        base=base_content,
                        ours=current_content,
                        theirs=proposed_content,
                    )

                    if merge_result.success:
                        # Auto-merged successfully
                        final_content = merge_result.content
                        logger.info("auto_merge_successful", path=patch["path"])
                    else:
                        # Conflicts detected
                        logger.warning(
                            "merge_conflicts_detected",
                            path=patch["path"],
                            conflict_count=len(merge_result.conflicts),
                        )

                        # Check for conflict resolution strategy in input
                        strategy = getattr(input_data, "conflict_strategy", None)
                        if strategy in ("ours", "theirs"):
                            # Apply resolution strategy
                            resolved = self.conflict_resolver.resolve_conflicts(merge_result, strategy)
                            final_content = resolved.content
                        else:
                            # Return with conflict markers
                            file_path.write_text(merge_result.content)
                            return ApplyPatchOutput(
                                success=False,
                                patch_id=input_data.patch_id,
                                applied=False,
                                path=patch["path"],
                                backup_path=str(backup_path) if backup_path else None,
                                error=f"Merge conflicts detected ({len(merge_result.conflicts)} conflicts). "
                                "File saved with conflict markers.",
                                conflicts=[
                                    ConflictInfo(
                                        line_start=c.line_start,
                                        line_end=c.line_end,
                                        ours=c.ours[:200],
                                        theirs=c.theirs[:200],
                                    )
                                    for c in merge_result.conflicts
                                ],
                            )
                else:
                    # File not modified or no base_content - direct apply
                    final_content = proposed_content

                # Write file
                file_path.write_text(final_content)

                # Clean up patch
                self.patch_store.delete_patch(input_data.patch_id)

                return ApplyPatchOutput(
                    success=True,
                    patch_id=input_data.patch_id,
                    applied=True,
                    path=patch["path"],
                    backup_path=str(backup_path) if backup_path else None,
                )

            except Exception as e:
                # Restore backup if available
                if backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, file_path)
                        logger.info(f"Restored backup after error: {e}")
                    except Exception as restore_error:
                        logger.error(f"Failed to restore backup: {restore_error}")

                return ApplyPatchOutput(
                    success=False,
                    patch_id=input_data.patch_id,
                    path=patch["path"],
                    error=f"Failed to apply patch: {e}",
                )

        except Exception as e:
            logger.error(f"Patch application failed: {e}", exc_info=True)
            return ApplyPatchOutput(
                success=False,
                patch_id=input_data.patch_id,
                path="",
                error=str(e),
            )
