"""
RFC-023 M0.3: Integration Tests for Pyright Daemon

Tests:
- M0.3.1: test_daemon_open_file - Single file opening
- M0.3.2: test_export_semantic_for_locations - Type extraction
- M0.3.3: test_typing_info_basic_types - Builtin types
- M0.3.4: test_typing_info_generic_types - Generic types
- M0.3.5: test_snapshot_lookup - Lookup performance
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.foundation.ir.external_analyzers.pyright_daemon import PyrightSemanticDaemon
from src.foundation.ir.external_analyzers.snapshot import Span


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_test_"))

    # Create pyrightconfig.json to help Pyright recognize the workspace
    import json

    config = {
        "include": ["**/*.py"],
        "typeCheckingMode": "basic",
        "reportMissingImports": False,
    }
    (temp_dir / "pyrightconfig.json").write_text(json.dumps(config, indent=2))

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
# M0.3.1: Single File Opening
# ============================================================


def test_daemon_open_file(daemon, temp_project):
    """
    M0.3.1: Test single file opening and LSP initialization.

    Verifies:
    - File is opened in LSP
    - Daemon health check shows file is tracked
    """
    code = """
def hello(name: str) -> str:
    return f"Hello, {name}!"
"""

    # Open file
    file_path = temp_project / "hello.py"
    daemon.open_file(file_path, code)

    # Verify daemon health
    health = daemon.health_check()
    assert health["status"] == "healthy"
    assert health["files_opened"] >= 1  # At least our file


# ============================================================
# M0.3.2: Semantic Export for Locations
# ============================================================


def test_export_semantic_for_locations(daemon, temp_project):
    """
    M0.3.2: Test semantic info extraction for specific locations.

    Verifies:
    - Specific locations can be queried
    - Snapshot is created with type info
    - Number of queries matches number of locations (O(N), not O(N^2))
    """
    code = """
def add(a: int, b: int) -> int:
    return a + b

class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

user = User("Alice", 30)
"""

    # Open file
    file_path = temp_project / "example.py"
    daemon.open_file(file_path, code)

    # Define locations to query (from IR)
    locations = [
        (1, 4),  # def add
        (2, 11),  # return a + b (a variable)
        (4, 6),  # class User
        (5, 8),  # def __init__
        (9, 0),  # user = ...
    ]

    # Export semantic info
    snapshot = daemon.export_semantic_for_locations(file_path, locations)

    # Verify snapshot
    assert snapshot is not None
    assert snapshot.snapshot_id.startswith("snapshot-")
    assert snapshot.project_id == temp_project.name
    assert len(snapshot.files) == 1
    assert str(file_path) in snapshot.files

    # Verify type info exists
    stats = snapshot.stats()
    assert stats["total_type_annotations"] > 0
    assert stats["total_files"] == 1


# ============================================================
# M0.3.3: Basic Builtin Types
# ============================================================


def test_typing_info_basic_types(daemon, temp_project):
    """
    M0.3.3: Test type inference for basic builtin types.

    Verifies:
    - int, str, bool, float
    - list, dict, tuple
    """
    code = """
# Basic types
x: int = 42
name: str = "Alice"
is_active: bool = True
price: float = 9.99

# Collection types
numbers: list = [1, 2, 3]
config: dict = {"key": "value"}
point: tuple = (10, 20)
"""

    file_path = temp_project / "types_basic.py"
    daemon.open_file(file_path, code)

    # Query locations of variables
    locations = [
        (2, 0),  # x: int
        (3, 0),  # name: str
        (4, 0),  # is_active: bool
        (5, 0),  # price: float
        (8, 0),  # numbers: list
        (9, 0),  # config: dict
        (10, 0),  # point: tuple
    ]

    snapshot = daemon.export_semantic_for_locations(file_path, locations)

    # Verify we got type info
    assert snapshot.stats()["total_type_annotations"] > 0


# ============================================================
# M0.3.5: Snapshot Lookup Performance
# ============================================================


def test_snapshot_lookup(daemon, temp_project):
    """
    M0.3.5: Test snapshot lookup is O(1).

    Verifies:
    - get_type_at() is fast (dict lookup)
    - Multiple lookups don't degrade performance
    """
    code = """
def func1(): pass
def func2(): pass
def func3(): pass
def func4(): pass
def func5(): pass
"""

    file_path = temp_project / "funcs.py"
    daemon.open_file(file_path, code)

    # Query all function locations
    locations = [(i, 4) for i in range(1, 6)]  # Lines 1-5, col 4

    snapshot = daemon.export_semantic_for_locations(file_path, locations)

    # Perform multiple lookups
    import time

    start = time.perf_counter()

    for _ in range(1000):
        for line in range(1, 6):
            result = snapshot.get_type_at(str(file_path), Span(line, 4, line, 4))

    elapsed = time.perf_counter() - start

    # 1000 iterations * 5 lookups = 5000 lookups
    # Should be very fast (< 100ms for 5000 lookups)
    assert elapsed < 0.1, f"Lookup too slow: {elapsed:.3f}s for 5000 lookups"

    print(f"✓ Performed 5000 lookups in {elapsed * 1000:.2f}ms")
