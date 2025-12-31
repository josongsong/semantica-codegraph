# IR Pipeline v3 - SOTA Stage-Based Architecture

Modern, extensible IR construction pipeline replacing deprecated `LayeredIRBuilder`.

## Overview

The IR Pipeline v3 provides:
- **Stage-based architecture** for extensibility and testability
- **Preset profiles** for quick start (fast, balanced, full)
- **Fluent API** for excellent developer experience
- **Rust integration** for 11.4x performance improvement
- **Comprehensive metrics** for observability
- **Backward compatibility** with `LayeredIRBuilder`

## Quick Start

```python
from pathlib import Path
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

# Simple usage with preset
pipeline = (
    PipelineBuilder()
    .with_profile("balanced")
    .with_files([Path("src/main.py"), Path("src/utils.py")])
    .build()
)

result = await pipeline.execute()

# Access results
ir_documents = result.ir_documents  # file_path → IRDocument
global_ctx = result.global_ctx      # Cross-file resolution result

# Check metrics
print(f"Total: {result.total_duration_ms}ms")
for metric in result.stage_metrics:
    print(f"  {metric.stage_name}: {metric.duration_ms}ms")
```

## Profiles

### Fast Profile (~50ms/file)
Minimal stages for maximum speed:
- L0: Cache (fast path only: mtime+size)
- L1: Structural IR (Rust)
- L4: Cross-File (incremental)

```python
.with_profile("fast")
```

### Balanced Profile (~100ms/file)
Good balance of features and performance:
- L0: Cache (fast + slow path)
- L1: Structural IR (Rust)
- L3: LSP Types (lightweight)
- L4: Cross-File (incremental)
- L10: Provenance

```python
.with_profile("balanced")
```

### Full Profile (~200ms/file)
All features enabled:
- L0: Cache
- L1: Structural IR (Rust)
- L3: LSP Types
- L4: Cross-File (msgpack)
- L7: Retrieval Index (fuzzy search)
- L10: Provenance (blake2b)

```python
.with_profile("full")
```

## Advanced Customization

```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

pipeline = (
    PipelineBuilder()
    # Cache configuration
    .with_cache(
        enabled=True,
        fast_path_only=False,  # Use both fast (mtime) and slow (content hash)
        ttl_seconds=3600,
        max_size=10000,
    )
    # Structural IR (Rust)
    .with_structural_ir(
        enabled=True,
        use_rust=True,        # Use Rust implementation (11.4x faster)
        use_msgpack=True,     # Zero-copy serialization
    )
    # LSP Type Enrichment
    .with_lsp_types(
        enabled=True,
        max_concurrent=10,    # Max concurrent Pyright requests
        lsp_timeout=30.0,
        fail_fast=False,      # Continue on errors
    )
    # Cross-File Resolution (RFC-062)
    .with_cross_file(
        enabled=True,
        use_msgpack=True,     # 25x faster than PyDict
        incremental=True,     # Only changed files + dependents
    )
    # Retrieval Index
    .with_retrieval(
        enabled=True,
        min_score=0.7,        # Fuzzy match threshold
        max_results=50,
        enable_fuzzy=True,
        enable_tfidf=True,
    )
    # Provenance (RFC-037)
    .with_provenance(
        enabled=True,
        hash_algorithm="blake2b",
        include_comments=False,
        include_docstrings=True,
    )
    # Hooks for observability
    .with_hook("on_stage_complete", lambda name, ctx, duration:
        logger.info(f"{name} completed in {duration}ms")
    )
    .build()
)
```

## Stage Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     PipelineBuilder                     │
│  Fluent API for constructing pipelines with presets    │
└────────────────────┬────────────────────────────────────┘
                     │ .build()
                     ▼
┌─────────────────────────────────────────────────────────┐
│                      IRPipeline                         │
│  Main entry point for pipeline execution               │
└────────────────────┬────────────────────────────────────┘
                     │ .execute()
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  StageOrchestrator                      │
│  Executes stages sequentially or in parallel           │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┬─────────────┐
        ▼                         ▼             ▼
┌───────────────┐      ┌───────────────┐   ┌──────────┐
│  L0: Cache    │      │ L1: Structural│   │ L3: LSP  │
│  (RFC-039)    │      │ IR (Rust)     │   │ Types    │
└───────────────┘      └───────────────┘   └──────────┘
        │                         │             │
        └────────────┬────────────┴─────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│              L4: Cross-File (RFC-062)                   │
│  Global context with lock-free symbol resolution       │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌───────────────┐      ┌───────────────────┐
│ L7: Retrieval │      │ L10: Provenance   │
│ Index         │      │ (RFC-037)         │
└───────────────┘      └───────────────────┘
```

## Stage Details

### L0: CacheStage (RFC-039)
Fast/Slow path caching for incremental builds.

**Fast Path**: mtime + size check (0.001ms/file)
**Slow Path**: Content hash (1-5ms/file)

```python
.with_cache(
    fast_path_only=False,  # Use both paths
    cache_dir=".cache/ir",
    ttl_seconds=3600,
)
```

### L1: StructuralIRStage
Structural IR generation using Rust.

**Performance**: 11.4x faster than Python (122s → 11s)

```python
.with_structural_ir(
    use_rust=True,
    use_msgpack=True,  # Zero-copy serialization
)
```

### L3: LSPTypeStage
Type enrichment from Pyright LSP server.

**Performance**: ~50ms/file (parallel with max_concurrent)

```python
.with_lsp_types(
    enabled=True,
    max_concurrent=10,
    lsp_timeout=30.0,
)
```

### L4: CrossFileStage (RFC-062)
Cross-file symbol resolution with dependency graph.

**Performance**: 12x faster (62s → 5s), 3.8M symbols/sec

```python
.with_cross_file(
    use_msgpack=True,  # 25x faster than PyDict
    incremental=True,
)
```

### L7: RetrievalIndexStage
Fuzzy search and ranking for symbol retrieval.

**Performance**: 0.1ms/query (RapidFuzz + TF-IDF)

```python
.with_retrieval(
    min_score=0.7,
    enable_fuzzy=True,
    enable_tfidf=True,
)
```

### L10: ProvenanceStage (RFC-037)
Deterministic fingerprints for code tracking.

**Performance**: ~2ms/file (AST-based hashing)

```python
.with_provenance(
    hash_algorithm="blake2b",
    include_comments=False,
    normalize_whitespace=True,
)
```

## Migration Guide

### From LayeredIRBuilder

**Old code (deprecated):**
```python
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

builder = LayeredIRBuilder(files, config)
ir_docs = builder.build()
```

**New code (recommended):**
```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

pipeline = (
    PipelineBuilder()
    .with_profile("balanced")
    .with_files(files)
    .with_build_config(config)
    .build()
)

result = await pipeline.execute()
ir_docs = result.ir_documents
```

**Compatibility adapter (for gradual migration):**
```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import LayeredIRBuilderAdapter

# Drop-in replacement (synchronous, deprecated)
builder = LayeredIRBuilderAdapter(files, config)
ir_docs = builder.build()
```

### Migration Checklist

- [ ] Replace `LayeredIRBuilder` imports with `PipelineBuilder`
- [ ] Convert synchronous `.build()` to async `await .execute()`
- [ ] Choose appropriate profile (fast/balanced/full)
- [ ] Add error handling for `PipelineResult.errors`
- [ ] Update tests to use async context
- [ ] Add metrics logging with hooks
- [ ] Remove deprecated imports

## Custom Stages

You can create custom stages by implementing the `PipelineStage` protocol:

```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
    PipelineStage,
    StageContext,
)

class MyCustomStage(PipelineStage[dict]):
    """Custom stage implementation."""

    async def execute(self, ctx: StageContext) -> StageContext:
        """Execute stage logic."""
        # Your custom logic here
        return ctx

    def should_skip(self, ctx: StageContext) -> tuple[bool, str | None]:
        """Determine if stage should be skipped."""
        return False, None

# Use in pipeline
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import StageOrchestrator

stages = [CacheStage(), StructuralIRStage(), MyCustomStage()]
orchestrator = StageOrchestrator(stages)
```

## Hooks and Observability

Register hooks for pipeline events:

```python
def on_stage_start(stage_name: str, ctx: StageContext):
    print(f"Starting {stage_name}")

def on_stage_complete(stage_name: str, ctx: StageContext, duration_ms: float):
    print(f"{stage_name} completed in {duration_ms}ms")

def on_stage_error(stage_name: str, ctx: StageContext, error: Exception):
    print(f"{stage_name} failed: {error}")

pipeline = (
    PipelineBuilder()
    .with_hook("on_stage_start", on_stage_start)
    .with_hook("on_stage_complete", on_stage_complete)
    .with_hook("on_stage_error", on_stage_error)
    .build()
)
```

## Performance Benchmarks

| Profile   | Files | Avg Time/File | Total Time | Speedup vs Old |
|-----------|-------|---------------|------------|----------------|
| Fast      | 100   | 50ms          | 5s         | 24x            |
| Balanced  | 100   | 100ms         | 10s        | 12x            |
| Full      | 100   | 200ms         | 20s        | 6x             |

*Benchmarked on M1 MacBook Pro with 100 Python files (~500 LOC each)*

## Error Handling

```python
result = await pipeline.execute()

if not result.is_success():
    print(f"Pipeline failed with {len(result.errors)} errors:")
    for error in result.errors:
        print(f"  - {error}")
else:
    print(f"Successfully built {len(result.ir_documents)} files")
```

## Parallel Execution

Some stages can run in parallel:

```python
pipeline = (
    PipelineBuilder()
    .with_parallel([
        [0],        # L0: Cache (must run first)
        [1, 2],     # L1: Structural IR + L3: LSP Types (parallel)
        [3],        # L4: Cross-File (must run after L1)
    ])
    .build()
)
```

## Testing

```python
import pytest
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

@pytest.mark.asyncio
async def test_pipeline_execution():
    pipeline = (
        PipelineBuilder()
        .with_profile("fast")
        .with_files([Path("test.py")])
        .build()
    )

    result = await pipeline.execute()

    assert result.is_success()
    assert len(result.ir_documents) == 1
    assert result.total_duration_ms > 0
```

## FAQ

**Q: Why is LayeredIRBuilder deprecated?**
A: It's a monolithic 9-layer class that's hard to extend, test, and optimize. The new pipeline is modular, testable, and 11.4x faster.

**Q: Can I still use LayeredIRBuilder?**
A: Yes, but you'll see deprecation warnings. Use `LayeredIRBuilderAdapter` for gradual migration.

**Q: What's the recommended profile?**
A: "balanced" for most use cases. Use "fast" for CI/CD, "full" for offline analysis.

**Q: How do I skip a stage?**
A: Configure with `enabled=False`:
```python
.with_lsp_types(enabled=False)
```

**Q: Can I add custom stages?**
A: Yes! Implement `PipelineStage` protocol and add to orchestrator.

**Q: Why async instead of sync?**
A: Enables true parallelism (LSP requests, I/O), proper GIL release for Rust calls, and better resource management.

## References

- [RFC-039: Cache Layer](../../../../../docs/rfcs/rfc-039-cache-layer.md)
- [RFC-062: Cross-File Resolution](../../../../../docs/rfcs/rfc-062-cross-file-resolution.md)
- [RFC-037: Provenance](../../../../../docs/rfcs/rfc-037-provenance.md)
- [Rust IR Module](../../../../../packages/codegraph-rust/codegraph-ir/)
