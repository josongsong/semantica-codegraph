# Migration Guide: LayeredIRBuilder → IRPipeline v3

## Executive Summary

The `LayeredIRBuilder` has been **deprecated** in favor of the new **IRPipeline v3** architecture. This migration guide helps you transition to the new SOTA-level pipeline system.

### Why Migrate?

| Metric | LayeredIRBuilder (Old) | IRPipeline v3 (New) | Improvement |
|--------|------------------------|---------------------|-------------|
| **Architecture** | Monolithic 9-layer class | Modular stage-based | Extensible |
| **Performance** | 122s for 100 files | 11s for 100 files | **11.4x faster** |
| **Testability** | Hard to test layers | Isolated stages | Easy to test |
| **DX** | Imperative, complex | Fluent API, presets | Excellent |
| **Observability** | Limited metrics | Hooks + metrics | Comprehensive |
| **Parallelism** | Sequential only | Parallel execution | 2-5x faster |

### Key Improvements

1. **11.4x Performance Boost**: Rust implementation for L1, L2, L4, L5, L6
2. **Stage-Based Architecture**: Modular, testable, extensible
3. **Fluent Builder API**: Excellent developer experience
4. **Preset Profiles**: Quick start with "fast", "balanced", "full"
5. **Comprehensive Metrics**: Per-stage timing, hooks, observability
6. **Parallel Execution**: Independent stages run in parallel
7. **Backward Compatibility**: `LayeredIRBuilderAdapter` for gradual migration

## Quick Migration

### 1. Replace Import

**Before:**
```python
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import (
    LayeredIRBuilder
)
```

**After:**
```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
    PipelineBuilder,
    IRPipeline,
)
```

### 2. Replace Build Code

**Before:**
```python
builder = LayeredIRBuilder(files, config)
ir_docs = builder.build()  # Synchronous
```

**After:**
```python
pipeline = (
    PipelineBuilder()
    .with_profile("balanced")
    .with_files(files)
    .with_build_config(config)
    .build()
)

result = await pipeline.execute()  # Async
ir_docs = result.ir_documents
```

### 3. Handle Async (if needed)

If your code is synchronous, wrap in `asyncio.run()`:

```python
import asyncio

result = asyncio.run(pipeline.execute())
ir_docs = result.ir_documents
```

## Detailed Migration Steps

### Step 1: Choose Profile

Select a profile based on your use case:

- **"fast"** (~50ms/file): CI/CD, quick iteration
  - L0: Cache (fast path only)
  - L1: Structural IR (Rust)
  - L4: Cross-File (incremental)

- **"balanced"** (~100ms/file): Default for most use cases
  - L0: Cache (fast + slow path)
  - L1: Structural IR (Rust)
  - L3: LSP Types (lightweight)
  - L4: Cross-File (incremental)
  - L10: Provenance

- **"full"** (~200ms/file): Offline analysis, research
  - All stages enabled
  - Maximum features

### Step 2: Update Configuration

Map old config to new builder methods:

**Before:**
```python
config = {
    "repo_id": "my-repo",
    "semantic_tier": "EXTENDED",
    "enable_cache": True,
    "enable_lsp": True,
}

builder = LayeredIRBuilder(files, config)
```

**After:**
```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import BuildConfig

build_config = BuildConfig(
    repo_id="my-repo",
    semantic_tier="EXTENDED",
)

pipeline = (
    PipelineBuilder()
    .with_profile("balanced")
    .with_build_config(build_config)
    .with_cache(enabled=True)
    .with_lsp_types(enabled=True)
    .with_files(files)
    .build()
)
```

### Step 3: Update Error Handling

**Before:**
```python
try:
    ir_docs = builder.build()
except Exception as e:
    print(f"Build failed: {e}")
```

**After:**
```python
result = await pipeline.execute()

if not result.is_success():
    print(f"Build failed with {len(result.errors)} errors:")
    for error in result.errors:
        print(f"  - {error}")
else:
    ir_docs = result.ir_documents
```

### Step 4: Add Metrics (Optional)

**New capability:**
```python
result = await pipeline.execute()

print(f"Total: {result.total_duration_ms:.1f}ms")
for metric in result.stage_metrics:
    print(f"  {metric.stage_name}: {metric.duration_ms:.1f}ms")
```

## Gradual Migration with Adapter

If you can't migrate immediately, use the compatibility adapter:

```python
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
    LayeredIRBuilderAdapter
)

# Drop-in replacement (shows deprecation warning)
builder = LayeredIRBuilderAdapter(files, config)
ir_docs = builder.build()  # Still synchronous
```

**Timeline:**
- **Now - 3 months**: Adapter available, deprecation warnings
- **3-6 months**: Adapter still works, louder warnings
- **6+ months**: Adapter may be removed, must migrate

## Common Patterns

### Pattern 1: Simple Build

**Before:**
```python
builder = LayeredIRBuilder([Path("main.py")], {"repo_id": "test"})
ir_docs = builder.build()
```

**After:**
```python
pipeline = PipelineBuilder().with_profile("fast").with_files([Path("main.py")]).build()
result = await pipeline.execute()
ir_docs = result.ir_documents
```

### Pattern 2: Batch Processing

**Before:**
```python
for batch in file_batches:
    builder = LayeredIRBuilder(batch, config)
    batch_results = builder.build()
    all_results.update(batch_results)
```

**After:**
```python
for batch in file_batches:
    pipeline = PipelineBuilder().with_profile("fast").with_files(batch).build()
    result = await pipeline.execute()
    all_results.update(result.ir_documents)
```

### Pattern 3: Custom Configuration

**Before:**
```python
config = {
    "repo_id": "test",
    "enable_cache": True,
    "enable_lsp": False,
    "enable_provenance": True,
}

builder = LayeredIRBuilder(files, config)
ir_docs = builder.build()
```

**After:**
```python
pipeline = (
    PipelineBuilder()
    .with_cache(enabled=True)
    .with_lsp_types(enabled=False)
    .with_provenance(enabled=True)
    .with_files(files)
    .build()
)

result = await pipeline.execute()
ir_docs = result.ir_documents
```

### Pattern 4: Incremental Builds

**Before:**
```python
# Not well supported in LayeredIRBuilder
builder = LayeredIRBuilder(changed_files, config)
ir_docs = builder.build()  # Re-builds everything
```

**After:**
```python
# Efficient incremental updates
pipeline = (
    PipelineBuilder()
    .with_profile("fast")
    .with_files(changed_files)
    .with_cached_irs(previous_ir_docs)  # Reuse unchanged
    .with_cross_file(incremental=True)
    .build()
)

result = await pipeline.execute()
# Only changed files + dependents rebuilt
```

## Testing Migration

### Update Test Cases

**Before:**
```python
def test_ir_builder():
    builder = LayeredIRBuilder([Path("test.py")], {})
    result = builder.build()
    assert len(result) > 0
```

**After:**
```python
@pytest.mark.asyncio
async def test_ir_pipeline():
    pipeline = PipelineBuilder().with_profile("fast").with_files([Path("test.py")]).build()
    result = await pipeline.execute()
    assert len(result.ir_documents) > 0
```

### Update Fixtures

**Before:**
```python
@pytest.fixture
def ir_builder():
    return LayeredIRBuilder([Path("test.py")], {"repo_id": "test"})
```

**After:**
```python
@pytest.fixture
def ir_pipeline():
    return PipelineBuilder().with_profile("fast").with_files([Path("test.py")]).build()
```

## Troubleshooting

### Issue: Async/Await Required

**Problem**: Old code is synchronous, new code is async.

**Solution**: Wrap in `asyncio.run()`:
```python
import asyncio

def my_sync_function():
    pipeline = PipelineBuilder().with_profile("fast").with_files(files).build()
    result = asyncio.run(pipeline.execute())
    return result.ir_documents
```

### Issue: Missing Stage

**Problem**: Need a stage not in preset profiles.

**Solution**: Customize with builder:
```python
pipeline = (
    PipelineBuilder()
    .with_profile("balanced")
    .with_retrieval(enabled=True)  # Add retrieval index
    .build()
)
```

### Issue: Performance Regression

**Problem**: New pipeline slower than expected.

**Solution**: Use "fast" profile and disable expensive stages:
```python
pipeline = (
    PipelineBuilder()
    .with_profile("fast")
    .with_lsp_types(enabled=False)  # Skip LSP
    .build()
)
```

### Issue: Rust Module Not Available

**Problem**: `codegraph_ir` Rust module not installed.

**Solution**:
```bash
# Install Rust dependencies
cd packages/codegraph-rust/codegraph-ir
maturin develop --release
```

## Rollback Plan

If you encounter critical issues:

1. **Use Adapter**: Switch to `LayeredIRBuilderAdapter` temporarily
2. **Report Issue**: File bug at GitHub Issues
3. **Stay on Old Version**: Pin to last stable version

```python
# Temporary rollback
from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
    LayeredIRBuilderAdapter
)

builder = LayeredIRBuilderAdapter(files, config)
ir_docs = builder.build()
```

## Migration Checklist

- [ ] Replace `LayeredIRBuilder` imports with `PipelineBuilder`
- [ ] Convert `.build()` to `await .execute()`
- [ ] Choose appropriate profile (fast/balanced/full)
- [ ] Update config mapping
- [ ] Update error handling
- [ ] Add metrics logging (optional)
- [ ] Update tests to async
- [ ] Update fixtures
- [ ] Test in staging environment
- [ ] Monitor performance metrics
- [ ] Remove deprecation warnings
- [ ] Update documentation

## Support

- **Documentation**: See [README.md](./README.md)
- **Examples**: See [examples/basic_usage.py](./examples/basic_usage.py)
- **Tests**: See [tests/test_pipeline.py](./tests/test_pipeline.py)
- **Issues**: File at GitHub Issues

## Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| **Phase 1**: New pipeline available | 0-3 months | ✅ DONE |
| **Phase 2**: Deprecation warnings | 3-6 months | ⏳ CURRENT |
| **Phase 3**: Adapter removal | 6+ months | 📋 PLANNED |

**Recommendation**: Migrate within 3 months to avoid disruption.
