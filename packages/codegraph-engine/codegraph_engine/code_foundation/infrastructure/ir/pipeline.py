"""
Unified IR Pipeline

Single entry point for all IR building use cases.
Uses Strategy pattern for flexible, pluggable build approaches.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                        IRPipeline                               │
    │                    (Unified Entry Point)                        │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                 │
    │  build()              - Build with configured strategy          │
    │  build_default()      - Full 9-layer build                      │
    │  build_incremental()  - Delta-based with change tracking        │
    │  build_parallel()     - Multi-process parallel                  │
    │  build_overlay()      - Git uncommitted overlay                 │
    │  build_quick()        - Layer 1 only (fast)                     │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import IRPipeline

    # Simple usage (default strategy)
    pipeline = IRPipeline(project_root)
    result = await pipeline.build(files)

    # With specific strategy
    result = await pipeline.build_incremental(files)
    result = await pipeline.build_parallel(files, workers=4)
    result = await pipeline.build_quick(files)

    # Custom strategy
    from codegraph_engine.code_foundation.infrastructure.ir.strategies import IncrementalStrategy
    pipeline = IRPipeline(project_root, strategy=IncrementalStrategy())
    result = await pipeline.build(files)

    # Sync API (for legacy code)
    result = pipeline.build_sync(files)
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode
from codegraph_engine.code_foundation.infrastructure.ir.strategies.default import DefaultStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.incremental import IncrementalStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.overlay import OverlayStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.parallel import ParallelStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)
from codegraph_engine.code_foundation.infrastructure.ir.strategies.quick import QuickStrategy

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import GlobalContext
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

logger = get_logger(__name__)


class IRPipeline:
    """
    Unified IR Pipeline - single entry point for all IR building.

    Combines the power of LayeredIRBuilder (9 layers) with flexible
    strategies for different use cases (incremental, parallel, etc.).

    This is the recommended way to build IR in codegraph.
    """

    def __init__(
        self,
        project_root: Path,
        strategy: IRBuildStrategy | None = None,
        repo_id: str = "default",
    ):
        """
        Initialize IR Pipeline.

        RFC-039: Now maintains a shared LayeredIRBuilder instance (stateful).

        Args:
            project_root: Project root directory
            strategy: Build strategy (default: DefaultStrategy)
            repo_id: Repository identifier
        """
        self.project_root = Path(project_root)
        self.repo_id = repo_id
        self._strategy = strategy or DefaultStrategy()

        # RFC-039: Shared LayeredIRBuilder (stateful, reused across builds)
        self._builder: "LayeredIRBuilder | None" = None

        # Cached strategies for convenience methods
        self._incremental_strategy: IncrementalStrategy | None = None
        self._parallel_strategy: ParallelStrategy | None = None

    @property
    def strategy(self) -> IRBuildStrategy:
        """Current build strategy."""
        return self._strategy

    @strategy.setter
    def strategy(self, value: IRBuildStrategy) -> None:
        """Set build strategy."""
        self._strategy = value

    def _get_builder(self) -> "LayeredIRBuilder":
        """
        RFC-039: Get or create shared LayeredIRBuilder.

        Builder is stateful and maintains L0 cache across builds.
        This enables watch mode with 274x speedup.

        Returns:
            Shared LayeredIRBuilder instance
        """
        if self._builder is None:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

            self._builder = LayeredIRBuilder(project_root=self.project_root)
            logger.debug("RFC-039: Created shared LayeredIRBuilder (stateful)")
        return self._builder

    def _create_context(
        self,
        enable_occurrences: bool = True,
        enable_lsp_enrichment: bool = True,
        enable_cross_file: bool = True,
        enable_retrieval_index: bool = True,
        enable_semantic_ir: bool = False,
        semantic_mode: SemanticIrBuildMode = SemanticIrBuildMode.FULL,
        enable_advanced_analysis: bool = False,
        collect_diagnostics: bool = True,
        analyze_packages: bool = True,
        **options,
    ) -> IRBuildContext:
        """Create build context with given options."""
        return IRBuildContext(
            project_root=self.project_root,
            repo_id=self.repo_id,
            enable_occurrences=enable_occurrences,
            enable_lsp_enrichment=enable_lsp_enrichment,
            enable_cross_file=enable_cross_file,
            enable_retrieval_index=enable_retrieval_index,
            enable_semantic_ir=enable_semantic_ir,
            semantic_mode=semantic_mode,
            enable_advanced_analysis=enable_advanced_analysis,
            collect_diagnostics=collect_diagnostics,
            analyze_packages=analyze_packages,
            options=options,
        )

    async def build(
        self,
        files: list[Path],
        **options,
    ) -> IRBuildResult:
        """
        Build IR using configured strategy.

        Args:
            files: Files to process
            **options: Layer toggle options (see IRBuildContext)

        Returns:
            IRBuildResult with IR documents and metadata
        """
        context = self._create_context(**options)
        logger.info(f"Building IR with {self._strategy.name} strategy for {len(files)} files")
        return await self._strategy.build(files, context)

    async def build_default(
        self,
        files: list[Path],
        **options,
    ) -> IRBuildResult:
        """
        Build full 9-layer IR (DefaultStrategy).

        Use for initial indexing or when you need all layers.
        """
        context = self._create_context(**options)
        return await DefaultStrategy().build(files, context)

    async def build_incremental(
        self,
        files: list[Path],
        **options,
    ) -> IRBuildResult:
        """
        Build IR incrementally with change tracking (IncrementalStrategy).

        Only rebuilds changed files and their dependents.
        Maintains internal cache across builds.
        """
        # RFC-039: Inject shared builder into strategy
        if self._incremental_strategy is None:
            builder = self._get_builder()  # Shared stateful builder
            self._incremental_strategy = IncrementalStrategy(builder=builder)

        context = self._create_context(**options)
        return await self._incremental_strategy.build(files, context)

    async def build_parallel(
        self,
        files: list[Path],
        workers: int | None = None,
        **options,
    ) -> IRBuildResult:
        """
        Build IR in parallel using multiple processes (ParallelStrategy).

        3x speedup on multi-core systems.
        Best for large batch processing.

        Args:
            files: Files to process
            workers: Number of worker processes (None = CPU count)
            **options: Layer toggle options
        """
        strategy = ParallelStrategy(max_workers=workers)
        context = self._create_context(**options)
        return await strategy.build(files, context)

    async def build_overlay(
        self,
        files: list[Path],
        include_untracked: bool = True,
        **options,
    ) -> IRBuildResult:
        """
        Build IR with git uncommitted changes overlay (OverlayStrategy).

        Detects and includes uncommitted changes in IR.
        Marks nodes from uncommitted files.

        Args:
            files: Base files to process
            include_untracked: Include untracked (?) files
            **options: Layer toggle options
        """
        strategy = OverlayStrategy(include_untracked=include_untracked)
        context = self._create_context(**options)
        return await strategy.build(files, context)

    async def build_quick(
        self,
        files: list[Path],
    ) -> IRBuildResult:
        """
        Build Layer 1 only IR for fast feedback (QuickStrategy).

        ~10-50ms per file. Use for LSP, autocomplete, etc.
        """
        context = self._create_context(
            enable_occurrences=False,
            enable_lsp_enrichment=False,
            enable_cross_file=False,
            enable_retrieval_index=False,
            enable_semantic_ir=False,
            enable_advanced_analysis=False,
            collect_diagnostics=False,
            analyze_packages=False,
        )
        return await QuickStrategy().build(files, context)

    # ========================================================================
    # Sync API (for legacy code)
    # ========================================================================

    def build_sync(self, files: list[Path], **options) -> IRBuildResult:
        """Sync wrapper for build()."""
        return asyncio.get_event_loop().run_until_complete(self.build(files, **options))

    def build_default_sync(self, files: list[Path], **options) -> IRBuildResult:
        """Sync wrapper for build_default()."""
        return asyncio.get_event_loop().run_until_complete(self.build_default(files, **options))

    def build_incremental_sync(self, files: list[Path], **options) -> IRBuildResult:
        """Sync wrapper for build_incremental()."""
        return asyncio.get_event_loop().run_until_complete(self.build_incremental(files, **options))

    def build_parallel_sync(self, files: list[Path], workers: int | None = None, **options) -> IRBuildResult:
        """Sync wrapper for build_parallel()."""
        return asyncio.get_event_loop().run_until_complete(self.build_parallel(files, workers=workers, **options))

    def build_overlay_sync(self, files: list[Path], include_untracked: bool = True, **options) -> IRBuildResult:
        """Sync wrapper for build_overlay()."""
        return asyncio.get_event_loop().run_until_complete(
            self.build_overlay(files, include_untracked=include_untracked, **options)
        )

    def build_quick_sync(self, files: list[Path]) -> IRBuildResult:
        """Sync wrapper for build_quick()."""
        return asyncio.get_event_loop().run_until_complete(self.build_quick(files))

    # ========================================================================
    # Cache Management
    # ========================================================================

    async def clear_incremental_cache(self) -> None:
        """
        RFC-039: Clear incremental cache (L0) - async.

        Clears Builder's L0 cache instead of strategy cache.
        CRITICAL: Must be async because builder.clear_l0() is async.
        """
        if self._builder:
            await self._builder.clear_l0()
            logger.debug("RFC-039: Cleared Builder L0 cache")

    async def get_cache_telemetry(self) -> dict[str, Any]:
        """
        RFC-039: Get cache telemetry from Builder - async.

        CRITICAL: Must be async because builder.get_l0_telemetry() is async.

        Returns:
            Dictionary with L0/L1/L2 cache stats
        """
        if self._builder:
            return await self._builder.get_l0_telemetry()
        return {}


# Convenience factory functions
def create_pipeline(
    project_root: Path,
    strategy: str = "default",
    **kwargs,
) -> IRPipeline:
    """
    Create IR pipeline with named strategy.

    Args:
        project_root: Project root directory
        strategy: Strategy name ("default", "incremental", "parallel", "overlay", "quick")
        **kwargs: Strategy-specific options

    Returns:
        Configured IRPipeline
    """
    strategies = {
        "default": DefaultStrategy,
        "incremental": IncrementalStrategy,
        "parallel": lambda: ParallelStrategy(**kwargs),
        "overlay": lambda: OverlayStrategy(**kwargs),
        "quick": QuickStrategy,
    }

    strategy_class = strategies.get(strategy, DefaultStrategy)
    strategy_instance = strategy_class() if callable(strategy_class) else strategy_class

    return IRPipeline(project_root, strategy=strategy_instance)
