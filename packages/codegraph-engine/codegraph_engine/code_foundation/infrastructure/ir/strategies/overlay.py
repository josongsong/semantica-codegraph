"""
Overlay IR Build Strategy

Git uncommitted changes overlay for live editing support.
Prioritizes working directory content over committed content.
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)

logger = get_logger(__name__)


@dataclass
class LocalChange:
    """Represents a local (uncommitted) file change."""

    file_path: str
    change_type: str  # "modified", "added", "deleted"
    content: str | None
    is_staged: bool


class OverlayStrategy(IRBuildStrategy):
    """
    Overlay IR build strategy for uncommitted changes.

    Detects git uncommitted changes and builds IR with working directory
    content overlaid on committed content.

    Use this for:
    - IDE integration (show uncommitted changes in analysis)
    - Pre-commit hooks (analyze what's about to be committed)
    - Live editing feedback

    Features:
    - Git status detection (modified, added, untracked)
    - Working directory content priority
    - Marks IR nodes with "uncommitted" attribute
    """

    def __init__(self, include_untracked: bool = True):
        """
        Args:
            include_untracked: Include untracked (?) files
        """
        self.include_untracked = include_untracked
        self._local_changes: dict[str, LocalChange] = {}

    @property
    def name(self) -> str:
        return "overlay"

    def _detect_local_changes(self, repo_root: Path) -> dict[str, LocalChange]:
        """
        Detect uncommitted changes using git status.

        Returns:
            {file_path: LocalChange}
        """
        changes: dict[str, LocalChange] = {}

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.warning("git status failed, returning empty changes")
                return changes

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                # Format: XY filename
                status = line[:2]
                filepath = line[3:].strip()

                # Handle renamed files (R status)
                if " -> " in filepath:
                    filepath = filepath.split(" -> ")[1]

                full_path = repo_root / filepath

                # Determine change type
                index_status = status[0]
                worktree_status = status[1]

                # Skip untracked if not included
                if index_status == "?" and not self.include_untracked:
                    continue

                if index_status in ["M", "A", "?"] or worktree_status in ["M", "A", "?"]:
                    if full_path.exists():
                        try:
                            content = full_path.read_text(encoding="utf-8")
                        except Exception:
                            content = None

                        if index_status == "?" or worktree_status == "?":
                            change_type = "added"
                        else:
                            change_type = "modified"
                    else:
                        content = None
                        change_type = "deleted"

                    is_staged = index_status != " " and index_status != "?"

                    changes[str(full_path)] = LocalChange(
                        file_path=str(full_path),
                        change_type=change_type,
                        content=content,
                        is_staged=is_staged,
                    )

                elif index_status == "D" or worktree_status == "D":
                    changes[str(full_path)] = LocalChange(
                        file_path=str(full_path),
                        change_type="deleted",
                        content=None,
                        is_staged=index_status == "D",
                    )

        except subprocess.TimeoutExpired:
            logger.warning("git status timed out")
        except FileNotFoundError:
            logger.warning("git not found")
        except Exception as e:
            logger.error(f"Failed to detect local changes: {e}")

        return changes

    def pre_process(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> list[Path]:
        """
        Detect local changes and merge with file list.
        """
        # Detect local changes
        self._local_changes = self._detect_local_changes(context.project_root)

        # Add uncommitted files to the list
        uncommitted_paths = {
            Path(change.file_path) for change in self._local_changes.values() if change.change_type != "deleted"
        }

        # Merge with input files
        all_files = set(files) | uncommitted_paths

        # Remove deleted files
        deleted_paths = {
            Path(change.file_path) for change in self._local_changes.values() if change.change_type == "deleted"
        }
        all_files -= deleted_paths

        logger.info(
            f"Overlay: {len(self._local_changes)} uncommitted changes "
            f"({len(uncommitted_paths)} added/modified, {len(deleted_paths)} deleted)"
        )

        # Store for post-processing
        context.options["local_changes"] = self._local_changes

        return list(all_files)

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build IR with uncommitted changes overlay.
        """
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

        start = time.perf_counter()

        # Pre-process to merge with local changes
        merged_files = self.pre_process(files, context)

        # Build using standard pipeline
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier

        builder = LayeredIRBuilder(project_root=context.project_root)

        # Convert IRBuildContext to BuildConfig
        if context.semantic_mode == SemanticIrBuildMode.QUICK:
            semantic_tier = SemanticTier.BASE
        elif context.semantic_mode == SemanticIrBuildMode.PR:
            semantic_tier = SemanticTier.EXTENDED
        else:
            semantic_tier = SemanticTier.FULL

        config = BuildConfig(
            semantic_tier=semantic_tier,
            occurrences=context.enable_occurrences,
            lsp_enrichment=context.enable_lsp_enrichment,
            cross_file=context.enable_cross_file,
            retrieval_index=context.enable_retrieval_index,
            heap_analysis=context.enable_advanced_analysis,
            diagnostics=context.collect_diagnostics,
            packages=context.analyze_packages,
        )

        result = await builder.build(files=merged_files, config=config)

        ir_docs = result.ir_documents
        global_ctx = result.global_ctx
        retrieval_index = result.retrieval_index
        diag_index = result.diagnostic_index
        pkg_index = result.package_index

        # Post-process: mark uncommitted nodes
        result = IRBuildResult(
            ir_documents=ir_docs,
            global_ctx=global_ctx,
            retrieval_index=retrieval_index,
            diagnostic_index=diag_index,
            package_index=pkg_index,
            files_processed=len(ir_docs),
            elapsed_seconds=time.perf_counter() - start,
        )

        return self.post_process(result, context)

    def post_process(
        self,
        result: IRBuildResult,
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Mark IR nodes from uncommitted files.
        """
        local_changes = context.options.get("local_changes", {})
        uncommitted_count = 0

        for file_path, ir_doc in result.ir_documents.items():
            if file_path in local_changes:
                change = local_changes[file_path]

                # Mark all nodes as uncommitted
                for node in ir_doc.nodes:
                    if not hasattr(node, "attrs") or node.attrs is None:
                        node.attrs = {}
                    node.attrs["uncommitted"] = True
                    node.attrs["change_type"] = change.change_type
                    node.attrs["is_staged"] = change.is_staged

                uncommitted_count += 1

        result.extra["uncommitted_files"] = uncommitted_count
        result.extra["total_local_changes"] = len(local_changes)

        logger.info(f"Overlay: marked {uncommitted_count} files as uncommitted")

        return result
