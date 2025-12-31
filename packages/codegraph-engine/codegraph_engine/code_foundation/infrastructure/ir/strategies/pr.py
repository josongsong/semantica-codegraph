"""
PR (Pull Request) IR Build Strategy

Optimized for code review and PR checks:
- Full DFG/CFG for taint analysis on changed files
- Skip BFG and advanced heap analysis (not needed for PR review)
- ~50ms/function (vs 90ms for FULL mode)

Use Cases:
- PR review with security checks
- Incremental taint analysis on changed files
- Pre-commit hooks with SAST
"""

import time
from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)

logger = get_logger(__name__)


class PRStrategy(IRBuildStrategy):
    """
    PR (Pull Request) build strategy.

    Optimized for code review with security analysis:
    - Builds CFG + DFG + Expression (for taint analysis)
    - Skips BFG + advanced heap analysis (not needed for PR)
    - Focuses on changed files + direct dependents

    Performance:
    - ~50ms/function (vs 90ms for FULL, 10ms for QUICK)
    - Supports taint analysis (unlike QUICK)
    - Faster than FULL (skips BFG, heap analysis)

    What you get:
    - Structural IR (nodes + edges)
    - Control Flow Graph (CFG)
    - Data Flow Graph (DFG)
    - Expression analysis with type info
    - Taint tracking capability
    - Cross-file resolution (for imports)

    What you don't get:
    - Basic Block Flow Graph (BFG)
    - Advanced heap/points-to analysis
    - Full project-wide analysis

    Use this for:
    - PR reviews with security checks
    - Pre-commit SAST hooks
    - Incremental security analysis
    - Code review bots
    """

    def __init__(self, changed_files: list[str] | None = None):
        """
        Args:
            changed_files: Optional list of changed file paths (for filtering)
        """
        self._changed_files = set(changed_files) if changed_files else None

    @property
    def name(self) -> str:
        return "pr"

    def pre_process(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> list[Path]:
        """
        Filter to changed files if specified.
        """
        if self._changed_files is None:
            return files

        filtered = [f for f in files if str(f) in self._changed_files]
        logger.info(f"PR mode: filtering to {len(filtered)}/{len(files)} changed files")
        return filtered

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build IR with PR mode settings.

        Uses LayeredIRBuilder with PR-optimized settings:
        - semantic_mode=PR (CFG + DFG, skip BFG)
        - enable_semantic_ir=True
        - enable_advanced_analysis=False (skip analysis indexes for speed)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import GlobalContext
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        start = time.perf_counter()

        # Filter files if changed_files specified
        target_files = self.pre_process(files, context)

        if not target_files:
            logger.info("No files to process in PR mode")
            return IRBuildResult(
                ir_documents={},
                global_ctx=GlobalContext(),
                retrieval_index=RetrievalOptimizedIndex(),
                files_processed=0,
                files_skipped=len(files),
                elapsed_seconds=time.perf_counter() - start,
                extra={"pr_mode": True, "no_files": True},
            )

        # Build with PR mode settings
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

        builder = LayeredIRBuilder(project_root=context.project_root)

        # Use BuildConfig.for_pr_review() preset
        config = BuildConfig.for_pr_review(changed_files={str(f) for f in target_files})
        config.retrieval_index = context.enable_retrieval_index
        config.diagnostics = context.collect_diagnostics

        result = await builder.build(files=target_files, config=config)

        ir_docs = result.ir_documents
        global_ctx = result.global_ctx
        retrieval_index = result.retrieval_index
        diag_index = result.diagnostic_index
        pkg_index = result.package_index

        elapsed = time.perf_counter() - start

        logger.info(
            f"🔍 PR build: {len(ir_docs)}/{len(target_files)} files "
            f"in {elapsed * 1000:.0f}ms ({len(ir_docs) / max(elapsed, 0.001):.0f} files/sec)"
        )

        return IRBuildResult(
            ir_documents=ir_docs,
            global_ctx=global_ctx,
            retrieval_index=retrieval_index,
            diagnostic_index=diag_index,
            package_index=pkg_index,
            files_processed=len(ir_docs),
            files_skipped=len(files) - len(target_files),
            elapsed_seconds=elapsed,
            extra={
                "pr_mode": True,
                "semantic_mode": "pr",
                "taint_capable": True,
                "changed_files_count": len(self._changed_files) if self._changed_files else 0,
            },
        )
