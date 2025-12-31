"""
Slow Test Profiler (SOTA: Performance tracking)

자동으로 느린 테스트를 찾고 로깅.
"""

import subprocess
import sys
from pathlib import Path


def profile_tests(test_dir: str = "tests/", threshold_seconds: float = 1.0):
    """
    Run tests and profile slow ones.

    Args:
        test_dir: Test directory
        threshold_seconds: Threshold for "slow" test (default: 1.0s)
    """
    print(f"=== Profiling tests in {test_dir} ===\n")

    # Run pytest with durations
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        test_dir,
        "--durations=0",  # All tests
        "--tb=no",
        "-q",
        "--collect-only",  # First collect only
    ]

    # Collect test count
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = result.stdout.split("\n")
    test_count = 0
    for line in lines:
        if "test" in line and "::" in line:
            test_count += 1

    print(f"Total tests found: {test_count}\n")

    # Now run with timing
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        test_dir,
        "--durations=50",  # Top 50
        "--tb=no",
        "-v",
    ]

    print("Running tests...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # Parse durations
    slow_tests = []
    in_durations = False

    for line in result.stdout.split("\n"):
        if "slowest" in line.lower():
            in_durations = True
            continue

        if in_durations and "::" in line:
            # Format: "0.50s call tests/unit/test_something.py::test_case"
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    time_str = parts[0]
                    time_val = float(time_str.rstrip("s"))
                    test_name = parts[2]

                    if time_val >= threshold_seconds:
                        slow_tests.append((test_name, time_val))
                except:
                    pass

    # Log slow tests
    if slow_tests:
        print(f"\n=== SLOW TESTS (>= {threshold_seconds}s) ===")
        for test, time_val in sorted(slow_tests, key=lambda x: x[1], reverse=True):
            print(f"{time_val:6.2f}s: {test}")

        # Write to log
        log_path = Path("benchmark/artifacts/reports/slow_tests.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "w") as f:
            f.write(f"# Slow Tests Report (>= {threshold_seconds}s)\n\n")
            for test, time_val in sorted(slow_tests, key=lambda x: x[1], reverse=True):
                f.write(f"{time_val:6.2f}s: {test}\n")

        print(f"\n✅ Logged to {log_path}")
    else:
        print(f"\n✅ No slow tests found (all < {threshold_seconds}s)")


if __name__ == "__main__":
    profile_tests()
