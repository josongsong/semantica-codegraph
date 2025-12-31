"""
RFC-036/037 Large-Scale Benchmark (최적화됨)

Tests tier model with reduced scale for faster CI.
NOTE: 100K LOC → 10K LOC (10배 축소)
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


@pytest.mark.benchmark
@pytest.mark.slow
@pytest.mark.asyncio
class TestLargeScaleBenchmark:
    """Large-scale performance benchmarks (축소: 10K LOC)."""

    async def test_large_codebase_base_tier(self, tmp_path):
        """Benchmark BASE tier with ~10K LOC (축소)."""
        # Generate codebase (10배 축소)
        files = []
        total_loc = 0
        target_loc = 10_000  # 100K → 10K

        print(f"\n🔨 Generating codebase (target: {target_loc:,} LOC)...")

        # Create 10 files with 1000 LOC each (100 → 10)
        for file_idx in range(10):
            file_path = tmp_path / f"module_{file_idx}.py"

            # Generate 200 functions per file (5 LOC each)
            functions = []
            for func_idx in range(200):
                func = f"""
def function_{file_idx}_{func_idx}(x, y):
    result = x + y
    return result
"""
                functions.append(func)

            content = "\n".join(functions)
            file_path.write_text(content)
            files.append(file_path)
            total_loc += content.count("\n")

        print(f"✅ Generated {len(files)} files, {total_loc:,} LOC")

        # Benchmark BASE tier
        print(f"\n⏱️  Benchmarking BASE tier...")
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_editor()

        start = time.perf_counter()
        result = await builder.build(files, config)
        elapsed = time.perf_counter() - start

        # Verify
        assert len(result.ir_documents) == len(files)
        assert result.provenance

        # Calculate metrics
        loc_per_sec = total_loc / elapsed if elapsed > 0 else 0
        files_per_sec = len(files) / elapsed if elapsed > 0 else 0

        print(f"\n📊 BASE Tier Results:")
        print(f"   Files: {len(files)}")
        print(f"   LOC: {total_loc:,}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Throughput: {loc_per_sec:,.0f} LOC/s")
        print(f"   Throughput: {files_per_sec:.1f} files/s")

        # Reasonable performance expectation
        # BASE tier should process at least 1000 LOC/s
        assert loc_per_sec > 1000, f"Too slow: {loc_per_sec:.0f} LOC/s"

    async def test_large_codebase_extended_tier(self, tmp_path):
        """Benchmark EXTENDED tier with ~10K LOC (축소)."""
        # Generate codebase (10배 축소)
        files = []
        total_loc = 0

        print(f"\n🔨 Generating codebase (target: 10K LOC)...")

        for file_idx in range(10):  # 100 → 10
            file_path = tmp_path / f"module_{file_idx}.py"

            functions = []
            for func_idx in range(200):
                func = f"""
def function_{file_idx}_{func_idx}(x, y):
    temp = x + y
    result = temp * 2
    return result
"""
                functions.append(func)

            content = "\n".join(functions)
            file_path.write_text(content)
            files.append(file_path)
            total_loc += content.count("\n")

        print(f"✅ Generated {len(files)} files, {total_loc:,} LOC")

        # Benchmark EXTENDED tier
        print(f"\n⏱️  Benchmarking EXTENDED tier...")
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        start = time.perf_counter()
        result = await builder.build(files, config)
        elapsed = time.perf_counter() - start

        # Verify
        assert len(result.ir_documents) == len(files)

        # Calculate metrics
        loc_per_sec = total_loc / elapsed if elapsed > 0 else 0
        files_per_sec = len(files) / elapsed if elapsed > 0 else 0

        print(f"\n📊 EXTENDED Tier Results:")
        print(f"   Files: {len(files)}")
        print(f"   LOC: {total_loc:,}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Throughput: {loc_per_sec:,.0f} LOC/s")
        print(f"   Throughput: {files_per_sec:.1f} files/s")

        # EXTENDED should be fast
        assert loc_per_sec > 1000, f"Too slow: {loc_per_sec:.0f} LOC/s"

    async def test_large_codebase_full_tier(self, tmp_path):
        """Benchmark FULL tier with ~100K LOC."""
        # Generate large codebase
        files = []
        total_loc = 0

        print(f"\n🔨 Generating codebase (target: 100K LOC)...")

        for file_idx in range(100):
            file_path = tmp_path / f"module_{file_idx}.py"

            functions = []
            for func_idx in range(200):
                func = f"""
def function_{file_idx}_{func_idx}(x, y):
    temp = x + y
    result = temp * 2
    return result
"""
                functions.append(func)

            content = "\n".join(functions)
            file_path.write_text(content)
            files.append(file_path)
            total_loc += content.count("\n")

        print(f"✅ Generated {len(files)} files, {total_loc:,} LOC")

        # Benchmark FULL tier
        print(f"\n⏱️  Benchmarking FULL tier...")
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_analysis()

        start = time.perf_counter()
        result = await builder.build(files, config)
        elapsed = time.perf_counter() - start

        # Verify
        assert len(result.ir_documents) == len(files)

        # Calculate metrics
        loc_per_sec = total_loc / elapsed if elapsed > 0 else 0
        files_per_sec = len(files) / elapsed if elapsed > 0 else 0

        print(f"\n📊 FULL Tier Results:")
        print(f"   Files: {len(files)}")
        print(f"   LOC: {total_loc:,}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Throughput: {loc_per_sec:,.0f} LOC/s")
        print(f"   Throughput: {files_per_sec:.1f} files/s")

        # FULL is slower but should still be reasonable
        assert loc_per_sec > 500, f"Too slow: {loc_per_sec:.0f} LOC/s"

    async def test_tier_comparison_large_scale(self, tmp_path):
        """Compare all tiers with large codebase."""
        # Generate codebase
        files = []
        total_loc = 0

        print(f"\n🔨 Generating large codebase...")

        # 100 files, ~100K LOC total
        for file_idx in range(100):
            file_path = tmp_path / f"module_{file_idx}.py"

            functions = []
            for func_idx in range(200):
                func = f"""
def func_{file_idx}_{func_idx}(x):
    return x * 2
"""
                functions.append(func)

            content = "\n".join(functions)
            file_path.write_text(content)
            files.append(file_path)
            total_loc += content.count("\n")

        print(f"✅ Generated {len(files)} files, {total_loc:,} LOC")

        # Benchmark all tiers
        builder = LayeredIRBuilder(tmp_path)
        times = {}

        for tier_name, config in [
            ("BASE", BuildConfig.for_editor()),
            ("EXTENDED", BuildConfig.for_refactoring()),
            ("FULL", BuildConfig.for_analysis()),
        ]:
            print(f"\n⏱️  Benchmarking {tier_name} tier...")

            start = time.perf_counter()
            result = await builder.build(files, config)
            elapsed = time.perf_counter() - start

            times[tier_name] = elapsed

            # Verify
            assert len(result.ir_documents) == len(files)

            loc_per_sec = total_loc / elapsed if elapsed > 0 else 0
            print(f"   Time: {elapsed:.2f}s ({loc_per_sec:,.0f} LOC/s)")

        # Print comparison
        print(f"\n📊 Large-Scale Performance Comparison ({total_loc:,} LOC):")
        print(f"   BASE:     {times['BASE']:.2f}s")
        print(f"   EXTENDED: {times['EXTENDED']:.2f}s")
        print(f"   FULL:     {times['FULL']:.2f}s")
        print(f"\n   Speedup:")
        print(f"   BASE vs FULL:     {times['FULL'] / times['BASE']:.1f}x")
        print(f"   EXTENDED vs FULL: {times['FULL'] / times['EXTENDED']:.1f}x")

        # Verify improvements
        best_time = min(times["BASE"], times["EXTENDED"])
        speedup = times["FULL"] / best_time

        print(f"   Best speedup:     {speedup:.1f}x")

        # Should have significant speedup
        assert speedup >= 2.0, f"Insufficient speedup: {speedup:.1f}x"
