"""
RFC-023 M2.3: Parallel Hover Performance Benchmark

Compares:
1. Sequential hover (M0/M1/M2)
2. Parallel hover (M2.3)

Scenarios:
- 20 locations → Expected: 2-5x speedup
- 50 locations → Expected: 5-10x speedup
- 100 locations → Expected: 8-10x speedup

Note: Actual speedup depends on LSP server response time and system capability.
"""

import asyncio
import shutil
import tempfile
import time
from pathlib import Path

from src.foundation.ir.external_analyzers import PyrightSemanticDaemon

# ============================================================
# Benchmark Configuration
# ============================================================

SCENARIOS = [
    {"num_functions": 10, "name": "Small (10 functions)"},
    {"num_functions": 20, "name": "Medium (20 functions)"},
    {"num_functions": 50, "name": "Large (50 functions)"},
]


# ============================================================
# Helper Functions
# ============================================================


def create_test_file(num_functions: int) -> tuple[Path, str, list[tuple[int, int]]]:
    """
    Create a test file with N functions.

    Args:
        num_functions: Number of functions to generate

    Returns:
        (file_path, code, locations)
    """
    # Generate code
    code_lines = []
    locations = []

    for i in range(num_functions):
        line_no = len(code_lines) + 1
        code_lines.append(f"def func_{i}(x: int) -> int:")
        code_lines.append(f"    '''Function {i}'''")
        code_lines.append(f"    return x * {i}")
        code_lines.append("")

        # Location of function def
        locations.append((line_no, 4))

    code = "\n".join(code_lines)

    # Create temp file
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_bench_"))
    file_path = temp_dir / "benchmark.py"

    return file_path, code, locations


# ============================================================
# Benchmark Functions
# ============================================================


def benchmark_sequential(
    daemon: PyrightSemanticDaemon, file_path: Path, locations: list[tuple[int, int]]
):
    """
    Benchmark: Sequential hover (M0/M1/M2).

    Args:
        daemon: Pyright daemon
        file_path: File to analyze
        locations: Locations to query

    Returns:
        (snapshot, elapsed_time_ms)
    """
    start = time.perf_counter()
    snapshot = daemon.export_semantic_for_locations(file_path, locations)
    elapsed = (time.perf_counter() - start) * 1000

    return snapshot, elapsed


async def benchmark_parallel(
    daemon: PyrightSemanticDaemon, file_path: Path, locations: list[tuple[int, int]]
):
    """
    Benchmark: Parallel hover (M2.3).

    Args:
        daemon: Pyright daemon
        file_path: File to analyze
        locations: Locations to query

    Returns:
        (snapshot, elapsed_time_ms)
    """
    start = time.perf_counter()
    snapshot = await daemon.export_semantic_for_locations_async(file_path, locations)
    elapsed = (time.perf_counter() - start) * 1000

    return snapshot, elapsed


# ============================================================
# Main Benchmark
# ============================================================


async def run_scenario(scenario: dict):
    """
    Run benchmark for a scenario.

    Args:
        scenario: Scenario config

    Returns:
        Benchmark results dict
    """
    num_functions = scenario["num_functions"]
    name = scenario["name"]

    print(f"\n{'=' * 80}")
    print(f"Scenario: {name}")
    print(f"  Number of functions: {num_functions}")
    print(f"  Locations to query: {num_functions}")
    print(f"{'=' * 80}")

    # Create test file
    print("Creating test file...")
    file_path, code, locations = create_test_file(num_functions)
    project_root = file_path.parent

    try:
        # Initialize daemon
        print("Initializing Pyright daemon...")
        daemon = PyrightSemanticDaemon(project_root)
        daemon.open_file(file_path, code)

        # Warm-up (first query is slow due to LSP initialization)
        print("Warming up...")
        _ = daemon.export_semantic_for_locations(file_path, locations[:1])

        # Benchmark 1: Sequential
        print(f"\n[1/2] Running sequential hover ({num_functions} locations)...")
        snapshot_seq, time_seq = benchmark_sequential(daemon, file_path, locations)
        print(f"  ✓ Sequential: {time_seq:.2f}ms")
        print(f"  ✓ Types captured: {len(snapshot_seq.typing_info)}")

        # Benchmark 2: Parallel
        print(f"\n[2/2] Running parallel hover ({num_functions} locations)...")
        snapshot_par, time_par = await benchmark_parallel(daemon, file_path, locations)
        print(f"  ✓ Parallel: {time_par:.2f}ms")
        print(f"  ✓ Types captured: {len(snapshot_par.typing_info)}")

        # Calculate metrics
        speedup = time_seq / time_par if time_par > 0 else 0
        time_per_loc_seq = time_seq / num_functions if num_functions > 0 else 0
        time_per_loc_par = time_par / num_functions if num_functions > 0 else 0

        # Print summary
        print(f"\n{'─' * 80}")
        print("Performance Summary:")
        print(f"  Sequential:    {time_seq:8.2f}ms  ({time_per_loc_seq:.1f}ms/loc)")
        print(f"  Parallel:      {time_par:8.2f}ms  ({time_per_loc_par:.1f}ms/loc)")
        print(f"  Speedup:       {speedup:8.1f}x")
        print(f"  Improvement:   {((1 - time_par/time_seq) * 100):6.1f}%")
        print(f"{'─' * 80}")

        # Cleanup
        daemon.shutdown()

        return {
            "name": name,
            "num_functions": num_functions,
            "sequential_ms": time_seq,
            "parallel_ms": time_par,
            "speedup": speedup,
            "types_captured_seq": len(snapshot_seq.typing_info),
            "types_captured_par": len(snapshot_par.typing_info),
        }

    finally:
        # Cleanup project
        shutil.rmtree(project_root)


async def main():
    """Run all benchmarks."""
    print("=" * 80)
    print("RFC-023 M2.3: Parallel Hover Performance Benchmark")
    print("=" * 80)
    print()
    print("Comparing:")
    print("  1. Sequential hover (M0/M1/M2)")
    print("  2. Parallel hover (M2.3)")
    print()

    results = []

    for scenario in SCENARIOS:
        try:
            result = await run_scenario(scenario)
            results.append(result)
        except Exception as e:
            print(f"\n❌ Scenario failed: {e}")
            import traceback

            traceback.print_exc()
            continue

    # Print summary table
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print()
    print(
        f"{'Scenario':<25} {'Sequential (ms)':>15} {'Parallel (ms)':>15} {'Speedup':>10}"
    )
    print("─" * 80)

    for result in results:
        print(
            f"{result['name']:<25} "
            f"{result['sequential_ms']:>15.2f} "
            f"{result['parallel_ms']:>15.2f} "
            f"{result['speedup']:>10.1f}x"
        )

    print()
    print("=" * 80)
    print("Key Insights:")
    print("=" * 80)

    if results:
        avg_speedup = sum(r["speedup"] for r in results) / len(results)
        max_speedup = max(r["speedup"] for r in results)
        print(f"  Average speedup: {avg_speedup:.1f}x")
        print(f"  Maximum speedup: {max_speedup:.1f}x")
        print()
        print("  Parallel hover optimization (M2.3):")
        print("  - Uses asyncio.to_thread() with Semaphore")
        print("  - Max concurrent: 10 (configurable)")
        print("  - Actual speedup depends on:")
        print("    • Number of locations")
        print("    • LSP server response time (~20-50ms per hover)")
        print("    • System threading capability")

    print()
    print("=" * 80)
    print("✅ Benchmark Complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
