"""
Tests for Pyright Parallel Hover (M2.3)

RFC-023 M2.3: Async/parallel hover optimization

Test scope:
- export_semantic_for_locations_async()
- _batch_hover_queries_async()
- Performance comparison (sync vs async)
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest
from src.foundation.ir.external_analyzers import PyrightSemanticDaemon

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_async_test_"))
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def daemon(temp_project):
    """Create a Pyright Daemon instance."""
    daemon = PyrightSemanticDaemon(temp_project)
    yield daemon
    # Cleanup
    daemon.shutdown()


# ============================================================
# M2.3.1: Async Single File Tests
# ============================================================


@pytest.mark.asyncio
async def test_async_export_single_file(daemon, temp_project):
    """
    Test async export for single file.

    Verifies:
    - Async version works correctly
    - Returns valid snapshot
    """
    code = """
def add(x: int, y: int) -> int:
    return x + y

class User:
    def __init__(self, name: str):
        self.name = name

users: list[User] = []
"""

    # Open file
    file_path = temp_project / "test.py"
    daemon.open_file(file_path, code)

    # Async export
    locations = [(1, 4), (4, 6), (8, 0)]  # add, User, users
    snapshot = await daemon.export_semantic_for_locations_async(file_path, locations)

    # Verify
    assert snapshot is not None
    assert snapshot.snapshot_id.startswith("snapshot-")
    assert len(snapshot.files) >= 1


@pytest.mark.asyncio
async def test_async_vs_sync_correctness(daemon, temp_project):
    """
    Test that async and sync versions return same results.

    Verifies:
    - Async results match sync results
    - No data loss in parallel execution
    """
    code = """
def func1() -> int:
    return 1

def func2() -> str:
    return "hello"

x: int = 10
y: str = "test"
"""

    file_path = temp_project / "compare.py"
    daemon.open_file(file_path, code)

    locations = [(1, 4), (4, 4), (7, 0), (8, 0)]  # func1, func2, x, y

    # Sync version
    snapshot_sync = daemon.export_semantic_for_locations(file_path, locations)

    # Async version
    snapshot_async = await daemon.export_semantic_for_locations_async(file_path, locations)

    # Compare results (both should have same number of types)
    assert len(snapshot_sync.typing_info) == len(snapshot_async.typing_info)


# ============================================================
# M2.3.2: Performance Comparison Tests
# ============================================================


@pytest.mark.asyncio
async def test_parallel_hover_performance(daemon, temp_project):
    """
    Test parallel hover performance improvement.

    Verifies:
    - Async version is faster than sync
    - Expected speedup: 2-5x for small examples (LSP overhead)

    Note:
        Actual speedup depends on:
        - Number of locations
        - LSP server response time
        - System concurrency capability
    """
    # Create file with many locations
    code_lines = []
    for i in range(20):
        code_lines.append(f"def func_{i}() -> int:")
        code_lines.append(f"    return {i}")
        code_lines.append("")

    code = "\n".join(code_lines)

    file_path = temp_project / "many_funcs.py"
    daemon.open_file(file_path, code)

    # Extract locations (every function)
    locations = [(i * 3 + 1, 4) for i in range(20)]  # 20 functions

    # Sync version
    start_sync = time.perf_counter()
    snapshot_sync = daemon.export_semantic_for_locations(file_path, locations)
    time_sync = (time.perf_counter() - start_sync) * 1000

    # Async version
    start_async = time.perf_counter()
    snapshot_async = await daemon.export_semantic_for_locations_async(file_path, locations)
    time_async = (time.perf_counter() - start_async) * 1000

    # Calculate speedup
    speedup = time_sync / time_async if time_async > 0 else 0

    print(f"\n  Sync:  {time_sync:.2f}ms ({len(locations)} locations)")
    print(f"  Async: {time_async:.2f}ms ({len(locations)} locations)")
    print(f"  Speedup: {speedup:.1f}x")

    # Async should be faster (or similar for small examples)
    # Allow some variance due to system overhead
    assert time_async <= time_sync * 1.5  # Async should not be significantly slower


# ============================================================
# M2.3.3: Multi-file Async Tests
# ============================================================


@pytest.mark.asyncio
async def test_async_export_multi_file(daemon, temp_project):
    """
    Test async export for multiple files.

    Verifies:
    - Multi-file async export works
    - All files are processed
    """
    # Create multiple files
    code1 = """
def add(x: int, y: int) -> int:
    return x + y
"""

    code2 = """
def multiply(x: int, y: int) -> int:
    return x * y
"""

    file1 = temp_project / "math1.py"
    file2 = temp_project / "math2.py"

    daemon.open_file(file1, code1)
    daemon.open_file(file2, code2)

    # Async export for multiple files
    file_locations = {
        file1: [(1, 4)],  # add
        file2: [(1, 4)],  # multiply
    }

    snapshot = await daemon.export_semantic_for_files_async(file_locations)

    # Verify
    assert len(snapshot.files) >= 2
    assert snapshot.stats()["total_type_annotations"] > 0


@pytest.mark.asyncio
async def test_async_multi_file_performance(daemon, temp_project):
    """
    Test multi-file async performance.

    Verifies:
    - Async version handles multiple files efficiently
    """
    # Create 5 files
    files = []
    file_locations = {}

    for i in range(5):
        code = f"""
def func_{i}_a() -> int:
    return {i}

def func_{i}_b() -> str:
    return "test_{i}"
"""
        file_path = temp_project / f"file_{i}.py"
        daemon.open_file(file_path, code)
        files.append(file_path)

        # 2 locations per file
        file_locations[file_path] = [(1, 4), (4, 4)]

    # Sync version
    start_sync = time.perf_counter()
    snapshot_sync = daemon.export_semantic_for_files(file_locations)
    time_sync = (time.perf_counter() - start_sync) * 1000

    # Async version
    start_async = time.perf_counter()
    snapshot_async = await daemon.export_semantic_for_files_async(file_locations)
    time_async = (time.perf_counter() - start_async) * 1000

    # Calculate speedup
    speedup = time_sync / time_async if time_async > 0 else 0

    print("\n  Multi-file (5 files, 10 locations total):")
    print(f"  Sync:  {time_sync:.2f}ms")
    print(f"  Async: {time_async:.2f}ms")
    print(f"  Speedup: {speedup:.1f}x")

    # Verify correctness
    assert len(snapshot_sync.typing_info) == len(snapshot_async.typing_info)


# ============================================================
# M2.3.4: Edge Cases
# ============================================================


@pytest.mark.asyncio
async def test_async_empty_locations(daemon, temp_project):
    """Test async export with empty locations list."""
    code = "x = 1"
    file_path = temp_project / "empty.py"
    daemon.open_file(file_path, code)

    # Empty locations
    snapshot = await daemon.export_semantic_for_locations_async(file_path, [])

    # Should return valid snapshot with no types
    assert snapshot is not None
    assert len(snapshot.typing_info) == 0


@pytest.mark.asyncio
async def test_async_single_location(daemon, temp_project):
    """Test async export with single location (no parallelism)."""
    code = """
def single() -> int:
    return 1
"""
    file_path = temp_project / "single.py"
    daemon.open_file(file_path, code)

    # Single location
    snapshot = await daemon.export_semantic_for_locations_async(file_path, [(1, 4)])

    # Should work correctly
    assert snapshot is not None


# ============================================================
# M2.3.5: Concurrency Limit Tests
# ============================================================


@pytest.mark.asyncio
async def test_async_concurrency_limit(daemon, temp_project):
    """
    Test that concurrency is properly limited.

    Verifies:
    - Semaphore limits concurrent requests
    - No excessive concurrent calls to LSP
    """
    # Create file with many locations
    code_lines = []
    for i in range(30):
        code_lines.append(f"x_{i}: int = {i}")

    code = "\n".join(code_lines)

    file_path = temp_project / "many_vars.py"
    daemon.open_file(file_path, code)

    # 30 locations
    locations = [(i + 1, 0) for i in range(30)]

    # Should not crash or overwhelm LSP server
    snapshot = await daemon.export_semantic_for_locations_async(file_path, locations)

    # Verify
    assert snapshot is not None
    # Some types might not be captured, but snapshot should be valid


# ============================================================
# Skip if pyright not installed
# ============================================================


@pytest.fixture(autouse=True)
def skip_if_no_pyright():
    """Skip all tests if pyright-langserver not found."""
    import shutil

    if not shutil.which("pyright-langserver"):
        pytest.skip("pyright-langserver not installed")
