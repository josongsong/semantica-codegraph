"""IR Pipeline v3 - SOTA Stage-Based Architecture

Modern, extensible IR construction pipeline with preset profiles and fluent API.

Quick Start:
    ```python
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
        PipelineBuilder,
        IRPipeline,
        PipelineResult,
    )

    # Simple preset
    pipeline = (
        PipelineBuilder()
        .with_profile("balanced")
        .with_files(files)
        .build()
    )

    result = await pipeline.execute()
    ir_documents = result.ir_documents
    ```

Advanced Usage:
    ```python
    # Custom pipeline
    pipeline = (
        PipelineBuilder()
        .with_cache(fast_path_only=True)
        .with_structural_ir(use_rust=True)
        .with_lsp_types(enabled=False)
        .with_cross_file(incremental=True)
        .with_provenance(hash_algorithm="blake2b")
        .with_hook("on_stage_complete", lambda name, ctx, duration: print(f"{name}: {duration}ms"))
        .build()
    )
    ```

Profiles:
    - "fast": Skip expensive stages (~50ms/file)
    - "balanced": Good DX + performance (~100ms/file)
    - "full": All features enabled (~200ms/file)

Stages:
    - L0: CacheStage - Fast/Slow path caching (RFC-039)
    - L1: StructuralIRStage - Structural IR from Rust
    - L3: LSPTypeStage - Type enrichment from Pyright
    - L4: CrossFileStage - Cross-file resolution (RFC-062)
    - L7: RetrievalIndexStage - Fuzzy search and ranking
    - L10: ProvenanceStage - Deterministic fingerprints (RFC-037)
"""

# Main API
from .builder import PipelineBuilder, PipelineConfig
from .pipeline import IRPipeline, PipelineResult, LayeredIRBuilderAdapter

# Protocol (for custom stages)
from .protocol import (
    PipelineStage,
    StageContext,
    StageMetrics,
    BuildConfig,
    PipelineHook,
    CacheState,
)

# Orchestrator (for advanced use)
from .orchestrator import StageOrchestrator

# Stages (for custom pipelines)
from .stages import (
    CacheStage,
    StructuralIRStage,
    LSPTypeStage,
    CrossFileStage,
    TemplateIRStage,
    RetrievalIndexStage,
    DiagnosticsStage,
    PackageStage,
    ProvenanceStage,
)

__all__ = [
    # Main API
    "PipelineBuilder",
    "IRPipeline",
    "PipelineResult",
    "LayeredIRBuilderAdapter",
    # Config
    "PipelineConfig",
    "BuildConfig",
    # Protocol
    "PipelineStage",
    "StageContext",
    "StageMetrics",
    "PipelineHook",
    "CacheState",
    # Orchestrator
    "StageOrchestrator",
    # Stages
    "CacheStage",
    "StructuralIRStage",
    "LSPTypeStage",
    "CrossFileStage",
    "TemplateIRStage",
    "RetrievalIndexStage",
    "DiagnosticsStage",
    "PackageStage",
    "ProvenanceStage",
]
