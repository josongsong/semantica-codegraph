"""
IR Build Strategies (SOTA - Unified BuildConfig)

Single BuildConfig object replaces Mode + Strategy pattern.

RECOMMENDED (SOTA):
    from codegraph_engine.code_foundation.infrastructure.ir import (
        LayeredIRBuilder,
        BuildConfig,
    )

    builder = LayeredIRBuilder(project_root)

    # Use presets
    result = await builder.build(files, BuildConfig.for_pr_review())
    result = await builder.build(files, BuildConfig.for_ci())

    # Or fine-grained control
    config = BuildConfig(cfg=True, dfg=True, parallel_workers=4)
    result = await builder.build(files, config)

LEGACY (deprecated - still works):
    builder = LayeredIRBuilder(project_root, strategy=IncrementalStrategy())
    ir_docs, global_ctx, ... = await builder.build_full(files)

BuildConfig Presets:
    - for_editor(): LSP, autocomplete (~10ms/file)
    - for_pr_review(): Taint analysis on changed files (~50ms/file)
    - for_ci(): Full analysis for CI/CD (~90ms/file)
    - for_initial_index(): First-time indexing
    - for_security_audit(): Deep security analysis

Legacy Strategies (deprecated):
    - DefaultStrategy: Full 9-layer build
    - IncrementalStrategy: Delta-based updates
    - ParallelStrategy: Multi-process build
    - OverlayStrategy: Git uncommitted overlay
    - QuickStrategy: Layer 1 only
    - PRStrategy: PR review mode
"""

# SOTA: Unified BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

# Legacy: Strategy classes (deprecated)
from codegraph_engine.code_foundation.infrastructure.ir.strategies.default import DefaultStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.incremental import IncrementalStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.overlay import OverlayStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.parallel import ParallelStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.pr import PRStrategy
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)
from codegraph_engine.code_foundation.infrastructure.ir.strategies.quick import QuickStrategy

__all__ = [
    # SOTA (recommended)
    "BuildConfig",
    # Protocol
    "IRBuildStrategy",
    "IRBuildContext",
    "IRBuildResult",
    # Legacy Strategies (deprecated)
    "DefaultStrategy",
    "IncrementalStrategy",
    "ParallelStrategy",
    "OverlayStrategy",
    "QuickStrategy",
    "PRStrategy",
]
