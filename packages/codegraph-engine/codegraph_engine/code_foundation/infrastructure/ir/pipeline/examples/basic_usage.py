"""Basic Usage Examples for IR Pipeline v3

Demonstrates:
- Quick start with presets
- Advanced customization
- Metrics and observability
- Error handling
- Migration from LayeredIRBuilder
"""

import asyncio
from pathlib import Path
from codegraph_shared.infra.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Example 1: Quick Start with Preset
# ═══════════════════════════════════════════════════════════════════════════


async def example_quick_start():
    """Quick start with balanced preset."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    print("\n=== Example 1: Quick Start ===")

    # Get some Python files
    files = list(Path(".").glob("*.py"))[:5]  # First 5 .py files

    # Build pipeline with preset
    pipeline = PipelineBuilder().with_profile("balanced").with_files(files).build()

    # Execute
    result = await pipeline.execute()

    # Check results
    if result.is_success():
        print(f"✅ Successfully built {len(result.ir_documents)} files")
        print(f"   Total time: {result.total_duration_ms:.1f}ms")
    else:
        print(f"❌ Failed with {len(result.errors)} errors")
        for error in result.errors:
            print(f"   - {error}")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Example 2: Advanced Customization
# ═══════════════════════════════════════════════════════════════════════════


async def example_custom_pipeline():
    """Advanced pipeline with custom configuration."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    print("\n=== Example 2: Custom Pipeline ===")

    files = list(Path(".").glob("*.py"))[:5]

    # Build custom pipeline
    pipeline = (
        PipelineBuilder()
        # Fast cache (mtime only)
        .with_cache(fast_path_only=True, ttl_seconds=3600)
        # Rust IR with msgpack
        .with_structural_ir(use_rust=True, use_msgpack=True)
        # Skip LSP (faster)
        .with_lsp_types(enabled=False)
        # Cross-file with incremental updates
        .with_cross_file(use_msgpack=True, incremental=True)
        # Enable provenance tracking
        .with_provenance(hash_algorithm="blake2b", include_comments=False)
        .with_files(files)
        .build()
    )

    result = await pipeline.execute()

    print(f"Pipeline stages: {pipeline.get_stage_names()}")
    print(f"Results: {len(result.ir_documents)} files, {result.total_duration_ms:.1f}ms")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Example 3: Metrics and Observability
# ═══════════════════════════════════════════════════════════════════════════


async def example_with_metrics():
    """Pipeline with detailed metrics and hooks."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    print("\n=== Example 3: Metrics and Observability ===")

    files = list(Path(".").glob("*.py"))[:5]

    # Hook callbacks
    def on_stage_start(stage_name: str, ctx):
        print(f"▶️  Starting {stage_name}...")

    def on_stage_complete(stage_name: str, ctx, duration_ms: float):
        print(f"✅ {stage_name} completed in {duration_ms:.1f}ms")

    def on_stage_error(stage_name: str, ctx, error: Exception):
        print(f"❌ {stage_name} failed: {error}")

    # Build pipeline with hooks
    pipeline = (
        PipelineBuilder()
        .with_profile("balanced")
        .with_files(files)
        .with_hook("on_stage_start", on_stage_start)
        .with_hook("on_stage_complete", on_stage_complete)
        .with_hook("on_stage_error", on_stage_error)
        .build()
    )

    result = await pipeline.execute()

    # Print detailed metrics
    print("\n📊 Stage Metrics:")
    for metric in result.stage_metrics:
        status = "✅" if not metric.error else "❌"
        print(f"   {status} {metric.stage_name:20s} {metric.duration_ms:6.1f}ms")

    print(f"\n   Total: {result.total_duration_ms:.1f}ms")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Example 4: Error Handling
# ═══════════════════════════════════════════════════════════════════════════


async def example_error_handling():
    """Demonstrate error handling and graceful degradation."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    print("\n=== Example 4: Error Handling ===")

    # Include both valid and invalid files
    files = [
        Path("valid_file.py"),  # May not exist
        Path("another_file.py"),
    ]

    # Build pipeline with fail_fast=False (graceful degradation)
    pipeline = (
        PipelineBuilder()
        .with_profile("fast")
        .with_files(files)
        .with_lsp_types(enabled=True, fail_fast=False)  # Continue on errors
        .build()
    )

    result = await pipeline.execute()

    # Check for partial success
    if result.is_success():
        print(f"✅ All files processed successfully")
    else:
        print(f"⚠️  Partial success: {len(result.ir_documents)} files, {len(result.errors)} errors")
        print("\nErrors:")
        for error in result.errors:
            print(f"   - {error}")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Example 5: Migration from LayeredIRBuilder
# ═══════════════════════════════════════════════════════════════════════════


async def example_migration():
    """Show migration from LayeredIRBuilder."""
    print("\n=== Example 5: Migration Guide ===")

    files = list(Path(".").glob("*.py"))[:3]

    # OLD WAY (deprecated, but still works with adapter)
    print("\n📜 Old way (deprecated):")
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import LayeredIRBuilderAdapter

    builder = LayeredIRBuilderAdapter(files, {"repo_id": "test"})
    old_result = builder.build()  # Synchronous
    print(f"   Built {len(old_result)} files (synchronous, deprecated)")

    # NEW WAY (recommended)
    print("\n🚀 New way (recommended):")
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    pipeline = PipelineBuilder().with_profile("balanced").with_files(files).build()

    new_result = await pipeline.execute()  # Async
    print(f"   Built {len(new_result.ir_documents)} files in {new_result.total_duration_ms:.1f}ms")
    print(f"   Metrics: {len(new_result.stage_metrics)} stages tracked")

    return new_result


# ═══════════════════════════════════════════════════════════════════════════
# Example 6: Profile Comparison
# ═══════════════════════════════════════════════════════════════════════════


async def example_profile_comparison():
    """Compare performance of different profiles."""
    from codegraph_engine.code_foundation.infrastructure.ir.pipeline import PipelineBuilder

    print("\n=== Example 6: Profile Comparison ===")

    files = list(Path(".").glob("*.py"))[:10]  # 10 files

    profiles = ["fast", "balanced", "full"]
    results = {}

    for profile in profiles:
        pipeline = PipelineBuilder().with_profile(profile).with_files(files).build()

        result = await pipeline.execute()
        results[profile] = result

        print(f"\n{profile.upper()} Profile:")
        print(f"   Files: {len(result.ir_documents)}")
        print(f"   Time: {result.total_duration_ms:.1f}ms")
        print(f"   Avg: {result.total_duration_ms / len(files):.1f}ms/file")
        print(f"   Stages: {[m.stage_name for m in result.stage_metrics]}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    """Run all examples."""
    print("=" * 70)
    print("IR Pipeline v3 - Examples")
    print("=" * 70)

    # Run examples
    try:
        await example_quick_start()
        await example_custom_pipeline()
        await example_with_metrics()
        await example_error_handling()
        await example_migration()
        await example_profile_comparison()

    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)

    print("\n" + "=" * 70)
    print("Examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
