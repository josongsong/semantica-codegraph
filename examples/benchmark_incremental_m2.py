"""
RFC-023 M2: Incremental Update Performance Benchmark

Compares:
1. Full analysis (M1): Analyze all files
2. Incremental analysis (M2): Analyze only changed files

Scenarios:
- 10 files, 1 changed → Expected: 10x speedup
- 100 files, 10 changed → Expected: 10x speedup
- 100 files, 1 changed → Expected: 100x speedup
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from src.foundation.ir.external_analyzers import (
    PyrightSemanticDaemon,
)

# ============================================================
# Benchmark Configuration
# ============================================================

SCENARIOS = [
    {"total_files": 10, "changed_files": 1, "name": "Small project, 1 file changed"},
    {"total_files": 10, "changed_files": 5, "name": "Small project, 5 files changed"},
    {"total_files": 20, "changed_files": 1, "name": "Medium project, 1 file changed"},
    {"total_files": 20, "changed_files": 10, "name": "Medium project, 10 files changed"},
]


# ============================================================
# Helper Functions
# ============================================================


def create_test_project(num_files: int) -> Path:
    """
    Create a temporary Git project with N Python files.

    Args:
        num_files: Number of files to create

    Returns:
        Path to project root
    """
    project_root = Path(tempfile.mkdtemp(prefix="pyright_bench_"))

    # Initialize git
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "bench@example.com"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Benchmark"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    # Create files
    for i in range(num_files):
        code = f"""
from typing import List

def func_{i}(x: int) -> int:
    return x * {i}

def helper_{i}(items: List[int]) -> int:
    return sum(items) + {i}

class Class_{i}:
    def __init__(self, value: int):
        self.value = value

    def process(self) -> int:
        return self.value + {i}

# Module variable
result_{i}: int = func_{i}(10)
"""
        file_path = project_root / f"module_{i}.py"
        file_path.write_text(code)

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )

    return project_root


def extract_ir_locations(file_path: Path, code: str) -> list[tuple[int, int]]:
    """
    Extract IR locations from code (simulated).

    In real usage, this would use IR generation.
    For benchmark, we use fixed positions.

    Returns:
        List of (line, col) tuples
    """
    # Simulate IR extraction: functions at lines 3, 6, class at line 9
    # In real usage: parse → generate IR → extract locations
    return [
        (3, 4),  # func_X
        (6, 4),  # helper_X
        (9, 6),  # Class_X
        (10, 8),  # __init__
        (13, 8),  # process
        (17, 0),  # result_X
    ]


# ============================================================
# Benchmark Functions
# ============================================================


def benchmark_full_analysis(daemon: PyrightSemanticDaemon, project_root: Path, num_files: int):
    """
    Benchmark: Full analysis (all files).

    Args:
        daemon: Pyright daemon
        project_root: Project root
        num_files: Number of files

    Returns:
        (snapshot, elapsed_time_ms)
    """
    # Collect all file locations
    all_locations = {}
    for i in range(num_files):
        file_path = project_root / f"module_{i}.py"
        code = file_path.read_text()
        locations = extract_ir_locations(file_path, code)
        all_locations[file_path] = locations

        # Open file in daemon
        daemon.open_file(file_path, code)

    # Time full analysis
    start = time.perf_counter()
    snapshot = daemon.export_semantic_for_files(all_locations)
    elapsed = (time.perf_counter() - start) * 1000

    return snapshot, elapsed


def benchmark_incremental_analysis(
    daemon: PyrightSemanticDaemon,
    project_root: Path,
    previous_snapshot,
    changed_file_indices: list[int],
):
    """
    Benchmark: Incremental analysis (only changed files).

    Args:
        daemon: Pyright daemon
        project_root: Project root
        previous_snapshot: Previous snapshot
        changed_file_indices: Indices of changed files

    Returns:
        (snapshot, elapsed_time_ms)
    """
    # Collect changed file locations
    changed_locations = {}
    for i in changed_file_indices:
        file_path = project_root / f"module_{i}.py"
        code = file_path.read_text()
        locations = extract_ir_locations(file_path, code)
        changed_locations[file_path] = locations

    # Time incremental analysis
    start = time.perf_counter()
    snapshot = daemon.export_semantic_incremental(changed_files=changed_locations, previous_snapshot=previous_snapshot)
    elapsed = (time.perf_counter() - start) * 1000

    return snapshot, elapsed


# ============================================================
# Main Benchmark
# ============================================================


def run_benchmark(scenario: dict):
    """
    Run benchmark for a scenario.

    Args:
        scenario: Scenario config (total_files, changed_files, name)

    Returns:
        Benchmark results dict
    """
    total_files = scenario["total_files"]
    changed_files = scenario["changed_files"]
    name = scenario["name"]

    print(f"\n{'=' * 80}")
    print(f"Scenario: {name}")
    print(f"  Total files: {total_files}")
    print(f"  Changed files: {changed_files}")
    print(f"{'=' * 80}")

    # Create test project
    print(f"Creating test project with {total_files} files...")
    project_root = create_test_project(total_files)

    try:
        # Initialize daemon
        print("Initializing Pyright daemon...")
        daemon = PyrightSemanticDaemon(project_root)

        # Benchmark 1: Full analysis
        print(f"\n[1/2] Running full analysis ({total_files} files)...")
        full_snapshot, full_time = benchmark_full_analysis(daemon, project_root, total_files)
        print(f"  ✓ Full analysis: {full_time:.2f}ms")
        print(f"  ✓ Snapshot: {full_snapshot.stats()}")

        # Benchmark 2: Incremental analysis
        print(f"\n[2/2] Running incremental analysis ({changed_files} files)...")
        changed_indices = list(range(changed_files))
        inc_snapshot, inc_time = benchmark_incremental_analysis(daemon, project_root, full_snapshot, changed_indices)
        print(f"  ✓ Incremental analysis: {inc_time:.2f}ms")
        print(f"  ✓ Snapshot: {inc_snapshot.stats()}")

        # Calculate speedup
        speedup = full_time / inc_time if inc_time > 0 else 0
        print(f"\n{'─' * 80}")
        print("Performance Summary:")
        print(f"  Full:        {full_time:8.2f}ms")
        print(f"  Incremental: {inc_time:8.2f}ms")
        print(f"  Speedup:     {speedup:8.1f}x")
        print(f"{'─' * 80}")

        # Cleanup
        daemon.shutdown()

        return {
            "name": name,
            "total_files": total_files,
            "changed_files": changed_files,
            "full_time_ms": full_time,
            "incremental_time_ms": inc_time,
            "speedup": speedup,
        }

    finally:
        # Cleanup project
        shutil.rmtree(project_root)


def main():
    """Run all benchmarks."""
    print("=" * 80)
    print("RFC-023 M2: Incremental Update Performance Benchmark")
    print("=" * 80)

    results = []

    for scenario in SCENARIOS:
        try:
            result = run_benchmark(scenario)
            results.append(result)
        except Exception as e:
            print(f"\n❌ Scenario failed: {e}")
            continue

    # Print summary
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Scenario':<40} {'Full (ms)':>12} {'Incr (ms)':>12} {'Speedup':>10}")
    print("─" * 80)

    for result in results:
        print(
            f"{result['name']:<40} "
            f"{result['full_time_ms']:>12.2f} "
            f"{result['incremental_time_ms']:>12.2f} "
            f"{result['speedup']:>10.1f}x"
        )

    print()
    print("=" * 80)
    print("✅ Benchmark Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
