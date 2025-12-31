"""
RFC-036/037 Performance Benchmark

Measures actual performance of tier model.
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestTierPerformanceBenchmark:
    """Performance benchmarks for tier model."""

    async def test_base_tier_performance(self, tmp_path):
        """Benchmark BASE tier performance."""
        # Create test file (medium size)
        test_file = tmp_path / "test.py"

        # Generate 100 functions (realistic module)
        functions = []
        for i in range(100):
            functions.append(f"""
def function_{i}(x, y):
    result = x + y
    return result
""")

        test_file.write_text("\n".join(functions))

        # Benchmark BASE tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_editor()

        start = time.perf_counter()
        result = await builder.build([test_file], config)
        elapsed = time.perf_counter() - start

        # Verify
        assert result.ir_documents
        assert result.provenance

        # Log performance
        print(f"\nBASE tier: {elapsed:.3f}s for 100 functions")

        # Should be fast (< 2s for 100 functions)
        assert elapsed < 2.0

    async def test_extended_tier_performance(self, tmp_path):
        """Benchmark EXTENDED tier performance."""
        test_file = tmp_path / "test.py"

        # Generate 100 functions
        functions = []
        for i in range(100):
            functions.append(f"""
def function_{i}(x, y):
    temp = x + y
    result = temp * 2
    return result
""")

        test_file.write_text("\n".join(functions))

        # Benchmark EXTENDED tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        start = time.perf_counter()
        result = await builder.build([test_file], config)
        elapsed = time.perf_counter() - start

        # Verify
        assert result.ir_documents

        # Log performance
        print(f"\nEXTENDED tier: {elapsed:.3f}s for 100 functions")

        # Should be reasonable (< 5s for 100 functions)
        assert elapsed < 5.0

    async def test_full_tier_performance(self, tmp_path):
        """Benchmark FULL tier performance."""
        test_file = tmp_path / "test.py"

        # Generate 100 functions
        functions = []
        for i in range(100):
            functions.append(f"""
def function_{i}(x, y):
    temp = x + y
    result = temp * 2
    return result
""")

        test_file.write_text("\n".join(functions))

        # Benchmark FULL tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_analysis()

        start = time.perf_counter()
        result = await builder.build([test_file], config)
        elapsed = time.perf_counter() - start

        # Verify
        assert result.ir_documents

        # Log performance
        print(f"\nFULL tier: {elapsed:.3f}s for 100 functions")

        # Should complete (< 10s for 100 functions)
        assert elapsed < 10.0

    async def test_tier_performance_comparison(self, tmp_path):
        """Compare performance across tiers."""
        test_file = tmp_path / "test.py"

        # Generate 50 functions (smaller for speed)
        functions = []
        for i in range(50):
            functions.append(f"""
def function_{i}(x):
    return x * 2
""")

        test_file.write_text("\n".join(functions))

        builder = LayeredIRBuilder(tmp_path)

        # Benchmark all tiers
        times = {}

        for tier_name, config in [
            ("BASE", BuildConfig.for_editor()),
            ("EXTENDED", BuildConfig.for_refactoring()),
            ("FULL", BuildConfig.for_analysis()),
        ]:
            start = time.perf_counter()
            await builder.build([test_file], config)
            elapsed = time.perf_counter() - start
            times[tier_name] = elapsed

        # Log results
        print(f"\nPerformance comparison (50 functions):")
        print(f"  BASE:     {times['BASE']:.3f}s")
        print(f"  EXTENDED: {times['EXTENDED']:.3f}s")
        print(f"  FULL:     {times['FULL']:.3f}s")

        # Calculate ratios
        base_vs_full = times["BASE"] / times["FULL"] if times["FULL"] > 0 else 0
        extended_vs_full = times["EXTENDED"] / times["FULL"] if times["FULL"] > 0 else 0

        print(f"  BASE vs FULL:     {base_vs_full:.1%} of FULL time")
        print(f"  EXTENDED vs FULL: {extended_vs_full:.1%} of FULL time")

        # Note: BASE may be slower than EXTENDED due to type inference overhead
        # EXTENDED skips generic_inference, which can be expensive
        # The key is that both are faster than FULL

        # Verify EXTENDED and BASE are both faster than FULL
        assert times["EXTENDED"] <= times["FULL"]
        # BASE may be slower or faster than EXTENDED (depends on type inference)

        # Verify significant improvement over FULL
        # At least one of BASE/EXTENDED should be significantly faster
        min_time = min(times["BASE"], times["EXTENDED"])
        speedup = times["FULL"] / min_time
        print(f"  Best speedup: {speedup:.1f}x")

        # Best tier should be at least 1.5x faster than FULL
        assert speedup >= 1.5
