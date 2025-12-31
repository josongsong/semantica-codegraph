"""
Default IR Build Strategy

Full 9-layer sequential build - the standard SOTA pipeline.
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


class DefaultStrategy(IRBuildStrategy):
    """
    Default IR build strategy - full 9-layer pipeline.

    This is the standard SOTA build that runs all enabled layers sequentially.
    Use this for:
    - Initial full repository indexing
    - When you need all layers (CFG, DFG, taint, etc.)
    - When parallelism isn't needed

    Layers:
        1. Structural IR (Tree-sitter) - Always on
        2. Occurrence (SCIP-compatible) - Optional
        3. LSP Type Enrichment - Optional
        4. Cross-file Resolution - Optional
        5. Semantic IR (CFG/DFG/BFG) - Optional
        6. Analysis Indexes (PDG/Taint/Slicing indexes) - Optional
        7. Retrieval Indexes - Optional
        8. Diagnostics - Optional
        9. Package Analysis - Optional
    """

    @property
    def name(self) -> str:
        return "default"

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build full 9-layer IR.

        Delegates to LayeredIRBuilder's new build() method with BuildConfig.
        """
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

        start = time.perf_counter()

        # Create builder instance
        builder = LayeredIRBuilder(project_root=context.project_root)

        # Convert IRBuildContext to BuildConfig
        # Determine semantic tier from semantic_mode
        if context.semantic_mode == SemanticIrBuildMode.QUICK:
            semantic_tier = SemanticTier.BASE
        elif context.semantic_mode == SemanticIrBuildMode.PR:
            semantic_tier = SemanticTier.EXTENDED
        else:  # FULL
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

        # Build using new async method
        result = await builder.build(files=files, config=config)

        elapsed = time.perf_counter() - start

        # Return with updated elapsed time
        return IRBuildResult(
            ir_documents=result.ir_documents,
            global_ctx=result.global_ctx,
            retrieval_index=result.retrieval_index,
            diagnostic_index=result.diagnostic_index,
            package_index=result.package_index,
            provenance=result.provenance,
            files_processed=result.files_processed,
            files_skipped=result.files_failed,
            elapsed_seconds=elapsed,
            extra=result.extra,
            layer_stats=result.layer_stats,
        )
