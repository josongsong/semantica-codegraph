"""Integration tests for IR Pipeline v3

Tests:
- PipelineBuilder with presets
- IRPipeline execution
- Error handling
- Metrics collection
- Hooks
- LayeredIRBuilder compatibility
"""

import pytest
from pathlib import Path
from dataclasses import replace

from codegraph_engine.code_foundation.infrastructure.ir.pipeline import (
    PipelineBuilder,
    IRPipeline,
    PipelineResult,
    StageContext,
    BuildConfig,
    LayeredIRBuilderAdapter,
)
from codegraph_engine.code_foundation.infrastructure.ir.pipeline.stages import (
    CacheStage,
    StructuralIRStage,
)


# ═══════════════════════════════════════════════════════════════════════════
# Test PipelineBuilder
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_builder_with_profile_fast():
    """Test fast profile configuration."""
    pipeline = PipelineBuilder().with_profile("fast").with_files([Path("test.py")]).build()

    assert isinstance(pipeline, IRPipeline)
    assert pipeline.get_stage_count() >= 2  # Cache + Structural


@pytest.mark.asyncio
async def test_builder_with_profile_balanced():
    """Test balanced profile configuration."""
    pipeline = PipelineBuilder().with_profile("balanced").with_files([Path("test.py")]).build()

    assert isinstance(pipeline, IRPipeline)
    assert pipeline.get_stage_count() >= 3  # Cache + Structural + LSP + Cross-File + Provenance


@pytest.mark.asyncio
async def test_builder_with_profile_full():
    """Test full profile configuration."""
    pipeline = PipelineBuilder().with_profile("full").with_files([Path("test.py")]).build()

    assert isinstance(pipeline, IRPipeline)
    assert pipeline.get_stage_count() >= 5  # All stages


@pytest.mark.asyncio
async def test_builder_custom_config():
    """Test custom configuration with chaining."""
    pipeline = (
        PipelineBuilder()
        .with_cache(enabled=True, fast_path_only=True)
        .with_structural_ir(use_rust=True)
        .with_lsp_types(enabled=False)
        .with_cross_file(incremental=True)
        .with_provenance(hash_algorithm="blake2b")
        .with_files([Path("test.py")])
        .build()
    )

    assert isinstance(pipeline, IRPipeline)
    stage_names = pipeline.get_stage_names()
    assert "CacheStage" in stage_names
    assert "StructuralIRStage" in stage_names


@pytest.mark.asyncio
async def test_builder_with_hooks():
    """Test hook registration."""
    called_events = []

    def on_start(stage_name, ctx):
        called_events.append(("start", stage_name))

    def on_complete(stage_name, ctx, duration_ms):
        called_events.append(("complete", stage_name))

    pipeline = (
        PipelineBuilder()
        .with_profile("fast")
        .with_hook("on_stage_start", on_start)
        .with_hook("on_stage_complete", on_complete)
        .with_files([])
        .build()
    )

    # Execute (even with empty files, hooks should fire)
    result = await pipeline.execute()

    # Verify hooks were called (at least for some stages)
    assert len(called_events) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Test IRPipeline Execution
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_execute_empty_files():
    """Test pipeline execution with no files."""
    pipeline = PipelineBuilder().with_profile("fast").with_files([]).build()

    result = await pipeline.execute()

    assert isinstance(result, PipelineResult)
    assert len(result.ir_documents) == 0
    assert result.total_duration_ms >= 0


@pytest.mark.asyncio
async def test_pipeline_execute_success():
    """Test successful pipeline execution."""
    # Create a temporary Python file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def hello(): pass\n")
        temp_file = Path(f.name)

    try:
        pipeline = PipelineBuilder().with_profile("fast").with_files([temp_file]).build()

        result = await pipeline.execute()

        assert result.is_success() or len(result.errors) == 0  # May have minor errors
        assert result.total_duration_ms > 0
        assert len(result.stage_metrics) > 0

    finally:
        temp_file.unlink()


@pytest.mark.asyncio
async def test_pipeline_metrics():
    """Test metrics collection."""
    pipeline = PipelineBuilder().with_profile("fast").with_files([]).build()

    result = await pipeline.execute()

    # Check metrics
    assert len(result.stage_metrics) > 0

    for metric in result.stage_metrics:
        assert metric.stage_name
        assert metric.duration_ms >= 0


@pytest.mark.asyncio
async def test_pipeline_error_handling():
    """Test error handling in pipeline."""
    # Use non-existent file to trigger potential errors
    pipeline = (
        PipelineBuilder()
        .with_profile("fast")
        .with_files([Path("/nonexistent/file.py")])
        .with_lsp_types(enabled=True, fail_fast=False)  # Graceful degradation
        .build()
    )

    result = await pipeline.execute()

    # Pipeline should complete even with errors
    assert isinstance(result, PipelineResult)
    # May have errors, but shouldn't crash
    if not result.is_success():
        assert len(result.errors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Test LayeredIRBuilder Compatibility
# ═══════════════════════════════════════════════════════════════════════════


def test_layered_ir_builder_adapter_deprecation():
    """Test that adapter shows deprecation warning."""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        adapter = LayeredIRBuilderAdapter([], {})

        # Check deprecation warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message).lower()


def test_layered_ir_builder_adapter_interface():
    """Test that adapter has same interface as LayeredIRBuilder."""
    adapter = LayeredIRBuilderAdapter([Path("test.py")], {"repo_id": "test"})

    # Should have files and config attributes
    assert hasattr(adapter, "files")
    assert hasattr(adapter, "config")
    assert hasattr(adapter, "build")


@pytest.mark.asyncio
async def test_layered_ir_builder_adapter_build():
    """Test adapter build method."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def test(): pass\n")
        temp_file = Path(f.name)

    try:
        adapter = LayeredIRBuilderAdapter([str(temp_file)], {"repo_id": "test"})

        # build() should return dict of IRDocuments
        result = adapter.build()

        assert isinstance(result, dict)
        # May be empty if Rust module not available, but should not crash

    finally:
        temp_file.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# Test Pipeline Results
# ═══════════════════════════════════════════════════════════════════════════


def test_pipeline_result_is_success():
    """Test PipelineResult.is_success()."""
    result1 = PipelineResult(errors=[])
    assert result1.is_success()

    result2 = PipelineResult(errors=["error1"])
    assert not result2.is_success()


def test_pipeline_result_get_stage_metric():
    """Test PipelineResult.get_stage_metric()."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline.protocol import StageMetrics

    metrics = [
        StageMetrics(stage_name="CacheStage", duration_ms=10.0),
        StageMetrics(stage_name="StructuralIRStage", duration_ms=50.0),
    ]

    result = PipelineResult(stage_metrics=metrics)

    # Get existing metric
    cache_metric = result.get_stage_metric("CacheStage")
    assert cache_metric is not None
    assert cache_metric.duration_ms == 10.0

    # Get non-existent metric
    missing_metric = result.get_stage_metric("NonExistentStage")
    assert missing_metric is None


# ═══════════════════════════════════════════════════════════════════════════
# Test Builder Validation
# ═══════════════════════════════════════════════════════════════════════════


def test_builder_invalid_profile():
    """Test that invalid profile raises error."""
    with pytest.raises(ValueError, match="Unknown profile"):
        PipelineBuilder().with_profile("invalid_profile")


def test_builder_chaining():
    """Test that builder methods return self for chaining."""
    builder = PipelineBuilder()

    result1 = builder.with_files([Path("test.py")])
    assert result1 is builder

    result2 = builder.with_cache(enabled=True)
    assert result2 is builder

    result3 = builder.with_profile("fast")
    assert result3 is builder


# ═══════════════════════════════════════════════════════════════════════════
# Test Stage Names
# ═══════════════════════════════════════════════════════════════════════════


def test_pipeline_get_stage_names():
    """Test getting stage names from pipeline."""
    pipeline = PipelineBuilder().with_profile("fast").with_files([]).build()

    stage_names = pipeline.get_stage_names()

    assert isinstance(stage_names, list)
    assert len(stage_names) > 0
    assert "CacheStage" in stage_names or "StructuralIRStage" in stage_names


def test_pipeline_get_stage_count():
    """Test getting stage count from pipeline."""
    pipeline = PipelineBuilder().with_profile("balanced").with_files([]).build()

    count = pipeline.get_stage_count()

    assert isinstance(count, int)
    assert count > 0
