"""
Foundation: Intermediate Representation (IR) v5.0

This module provides the core data models, utilities, and build pipeline for the IR layer.

Key components:
- models: Core IR entities (Node, Edge, IRDocument)
- id_strategy: ID generation strategies (logical_id, stable_id, content_hash)
- pipeline: Unified IR build pipeline with pluggable strategies
- strategies: Build strategies (Default, Incremental, Parallel, Overlay, Quick)

Usage (recommended):
    from codegraph_engine.code_foundation.infrastructure.ir import IRPipeline

    # Build IR with default (full 9-layer) strategy
    pipeline = IRPipeline(project_root)
    result = await pipeline.build(files)

    # Build incrementally (only changed files)
    result = await pipeline.build_incremental(files)

    # Build in parallel (3x speedup)
    result = await pipeline.build_parallel(files, workers=4)

    # Build quick (Layer 1 only, <100ms)
    result = await pipeline.build_quick(files)

Note: Uses lazy imports to avoid circular import issues with pipeline module.
"""

# Eagerly import stable, low-dependency modules
from codegraph_engine.code_foundation.infrastructure.ir.id_strategy import (
    generate_cfg_block_id,
    generate_cfg_id,
    generate_content_hash,
    generate_edge_id,
    generate_logical_id,
    generate_signature_hash,
    generate_signature_id,
    generate_stable_id,
    generate_type_id,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    ControlFlowSummary,
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Span,
)


def __getattr__(name: str):
    """Lazy import for pipeline and strategies to avoid circular imports."""
    # Pipeline imports (may have complex dependencies)
    if name in ("IRPipeline", "create_pipeline"):
        from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
            IRPipeline,
            create_pipeline,
        )

        return locals()[name]

    # Strategy imports
    if name in (
        "DefaultStrategy",
        "IncrementalStrategy",
        "IRBuildContext",
        "IRBuildResult",
        "IRBuildStrategy",
        "OverlayStrategy",
        "ParallelStrategy",
        "QuickStrategy",
    ):
        from codegraph_engine.code_foundation.infrastructure.ir.strategies import (
            DefaultStrategy,
            IncrementalStrategy,
            IRBuildContext,
            IRBuildResult,
            IRBuildStrategy,
            OverlayStrategy,
            ParallelStrategy,
            QuickStrategy,
        )

        return locals()[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models
    "Node",
    "Edge",
    "ControlFlowSummary",
    "Span",
    "IRDocument",
    # Enums
    "NodeKind",
    "EdgeKind",
    # ID Strategy
    "generate_logical_id",
    "generate_stable_id",
    "generate_content_hash",
    "generate_edge_id",
    "generate_type_id",
    "generate_signature_id",
    "generate_signature_hash",
    "generate_cfg_id",
    "generate_cfg_block_id",
    # Pipeline (v5.0) - lazy
    "IRPipeline",
    "create_pipeline",
    # Strategies (v5.0) - lazy
    "IRBuildStrategy",
    "IRBuildContext",
    "IRBuildResult",
    "DefaultStrategy",
    "IncrementalStrategy",
    "ParallelStrategy",
    "OverlayStrategy",
    "QuickStrategy",
]
