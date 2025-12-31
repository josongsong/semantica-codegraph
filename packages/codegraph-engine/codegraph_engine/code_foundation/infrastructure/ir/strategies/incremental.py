"""
Incremental IR Build Strategy

Delta-based updates with change tracking.
Only rebuilds changed files and their dependents.

Uses shared ChangeTracker from infrastructure/incremental/ to avoid duplication.
"""

import time
from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode
from codegraph_engine.code_foundation.infrastructure.incremental.change_tracker import (
    ChangeTracker,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


class IncrementalStrategy(IRBuildStrategy):
    """
    Incremental IR build strategy.

    RFC-039: Refactored to use LayeredIRBuilder's L0 cache.

    Only rebuilds changed files and their dependents.
    Uses shared ChangeTracker and LayeredIRBuilder's stateful L0 cache.

    Use this for:
    - File watcher triggered rebuilds
    - IDE integration (on-save rebuilds)
    - Large repositories where full rebuild is expensive

    Features:
    - Content-based change detection (via Builder's L0 Fast Path)
    - Dependency-aware affected file calculation
    - Preserves unchanged IRs in Builder's L0 cache
    - Automatic LRU eviction (handled by Builder)

    RFC-039 Changes:
    - Removed: _ir_cache, _max_cache_size, _cache_access_order
    - Removed: _update_cache(), clear_cache() methods
    - Now reuses LayeredIRBuilder instance (stateful)
    - Builder instance injected by IRPipeline
    """

    def __init__(self, builder: "LayeredIRBuilder | None" = None):
        """
        Initialize incremental strategy.

        RFC-039: Builder instance can be injected by IRPipeline.

        Args:
            builder: Shared LayeredIRBuilder instance (optional)
        """
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

        self._builder = builder  # RFC-039: Injected by IRPipeline

    @property
    def name(self) -> str:
        return "incremental"

    def pre_process(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> list[Path]:
        """
        RFC-039: Pre-process is now a no-op.

        Change detection is handled by LayeredIRBuilder's L0 cache.
        This method is kept for protocol compatibility.
        """
        # RFC-039: Builder handles change detection internally
        logger.debug("IncrementalStrategy.pre_process: Delegating to Builder's L0 cache")
        return files  # Return all files, Builder will filter

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        RFC-039: Build IR incrementally using Builder's L0 cache.

        Builder now handles all caching internally via L0 cache.
        This strategy is now a thin wrapper that configures the builder.
        """
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier

        start = time.perf_counter()

        # RFC-039: Reuse injected Builder or create new one
        # IRPipeline injects builder for stateful caching
        if self._builder is None:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

            builder = LayeredIRBuilder(project_root=context.project_root)
        else:
            builder = self._builder

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

        # RFC-039: Builder handles L0 check + build + update internally
        result = await builder.build(files=files, config=config)

        elapsed = time.perf_counter() - start

        # Get L0 telemetry for reporting (async)
        l0_stats = await builder.get_l0_telemetry()

        return IRBuildResult(
            ir_documents=result.ir_documents,
            global_ctx=result.global_ctx,
            retrieval_index=result.retrieval_index,
            diagnostic_index=result.diagnostic_index,
            package_index=result.package_index,
            files_processed=len(result.ir_documents),
            files_skipped=0,  # Builder reports this internally
            elapsed_seconds=elapsed,
            extra={
                "l0_cache": l0_stats,  # RFC-039: Include L0 stats
            },
        )

    # RFC-039: Removed _update_cache() - handled by Builder's L0
    # RFC-039: Removed clear_cache() - use builder.clear_l0() instead
    # RFC-039: Removed _extract_dependencies() - moved to Builder
