"""
Tests for Pyright Incremental Updates (M2)

RFC-023 M2: Incremental semantic analysis

Test scope:
- ChangeDetector (Git diff)
- SnapshotDelta (compute/merge)
- export_semantic_incremental()
- Performance comparison (Full vs Incremental)
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.foundation.ir.external_analyzers import (
    ChangeDetector,
    PyrightSemanticDaemon,
    PyrightSemanticSnapshot,
    SnapshotDelta,
    Span,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def git_repo():
    """Create a temporary Git repository for testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="pyright_git_test_"))

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_dir,
        check=True,
        capture_output=True,
    )

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
def daemon(git_repo):
    """Create a Pyright Daemon instance."""
    daemon = PyrightSemanticDaemon(git_repo)
    yield daemon
    daemon.shutdown()


# ============================================================
# M2.1: ChangeDetector Tests
# ============================================================


def test_change_detector_init(git_repo):
    """Test ChangeDetector initialization."""
    detector = ChangeDetector(git_repo)
    assert detector.project_root == git_repo


def test_change_detector_not_git_repo():
    """Test ChangeDetector fails on non-Git directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="not_git_"))
    try:
        with pytest.raises(ValueError, match="Not a Git repository"):
            ChangeDetector(temp_dir)
    finally:
        shutil.rmtree(temp_dir)


def test_change_detector_detect_new_file(git_repo):
    """Test detection of newly added file."""
    # Create initial commit
    file1 = git_repo / "file1.py"
    file1.write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # Add new file (uncommitted)
    file2 = git_repo / "file2.py"
    file2.write_text("y = 2")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)

    # Detect changes
    detector = ChangeDetector(git_repo)
    changed, deleted = detector.detect_changed_files()

    # Should detect file2.py as changed
    assert len(changed) >= 1
    assert any("file2.py" in str(f) for f in changed)


def test_change_detector_detect_modified_file(git_repo):
    """Test detection of modified file."""
    # Create initial commit
    file1 = git_repo / "file1.py"
    file1.write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # Modify file
    file1.write_text("x = 2")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)

    # Detect changes
    detector = ChangeDetector(git_repo)
    changed, deleted = detector.detect_changed_files()

    # Should detect file1.py as modified
    assert len(changed) >= 1
    assert any("file1.py" in str(f) for f in changed)


def test_change_detector_get_current_commit(git_repo):
    """Test getting current Git commit hash."""
    # Create initial commit
    file1 = git_repo / "file1.py"
    file1.write_text("x = 1")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )

    # Get commit hash
    detector = ChangeDetector(git_repo)
    commit_hash = detector.get_current_commit()

    # Should be a valid commit hash (40 chars)
    assert len(commit_hash) == 40
    assert commit_hash.isalnum()


# ============================================================
# M2.2: SnapshotDelta Tests
# ============================================================


def test_snapshot_delta_empty():
    """Test SnapshotDelta with no changes."""
    snapshot1 = PyrightSemanticSnapshot(
        snapshot_id="s1", project_id="test", files=["a.py"]
    )
    snapshot1.add_type_info("a.py", Span(1, 0, 1, 0), "int")

    snapshot2 = PyrightSemanticSnapshot(
        snapshot_id="s2", project_id="test", files=["a.py"]
    )
    snapshot2.add_type_info("a.py", Span(1, 0, 1, 0), "int")

    # No changes
    delta = snapshot2.compute_delta(snapshot1)

    assert len(delta.added) == 0
    assert len(delta.removed) == 0
    assert len(delta.modified) == 0


def test_snapshot_delta_added():
    """Test SnapshotDelta with added types."""
    snapshot1 = PyrightSemanticSnapshot(
        snapshot_id="s1", project_id="test", files=["a.py"]
    )
    snapshot1.add_type_info("a.py", Span(1, 0, 1, 0), "int")

    snapshot2 = PyrightSemanticSnapshot(
        snapshot_id="s2", project_id="test", files=["a.py"]
    )
    snapshot2.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    snapshot2.add_type_info("a.py", Span(2, 0, 2, 0), "str")  # Added

    delta = snapshot2.compute_delta(snapshot1)

    assert len(delta.added) == 1
    assert len(delta.removed) == 0
    assert len(delta.modified) == 0
    assert delta.added[("a.py", Span(2, 0, 2, 0))] == "str"


def test_snapshot_delta_removed():
    """Test SnapshotDelta with removed types."""
    snapshot1 = PyrightSemanticSnapshot(
        snapshot_id="s1", project_id="test", files=["a.py"]
    )
    snapshot1.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    snapshot1.add_type_info("a.py", Span(2, 0, 2, 0), "str")

    snapshot2 = PyrightSemanticSnapshot(
        snapshot_id="s2", project_id="test", files=["a.py"]
    )
    snapshot2.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    # Removed Span(2, 0)

    delta = snapshot2.compute_delta(snapshot1)

    assert len(delta.added) == 0
    assert len(delta.removed) == 1
    assert len(delta.modified) == 0
    assert delta.removed[("a.py", Span(2, 0, 2, 0))] == "str"


def test_snapshot_delta_modified():
    """Test SnapshotDelta with modified types."""
    snapshot1 = PyrightSemanticSnapshot(
        snapshot_id="s1", project_id="test", files=["a.py"]
    )
    snapshot1.add_type_info("a.py", Span(1, 0, 1, 0), "int")

    snapshot2 = PyrightSemanticSnapshot(
        snapshot_id="s2", project_id="test", files=["a.py"]
    )
    snapshot2.add_type_info("a.py", Span(1, 0, 1, 0), "str")  # Modified

    delta = snapshot2.compute_delta(snapshot1)

    assert len(delta.added) == 0
    assert len(delta.removed) == 0
    assert len(delta.modified) == 1
    assert delta.modified[("a.py", Span(1, 0, 1, 0))] == ("int", "str")


def test_snapshot_delta_stats():
    """Test SnapshotDelta statistics."""
    delta = SnapshotDelta()
    delta.added[("a.py", Span(1, 0, 1, 0))] = "int"
    delta.removed[("b.py", Span(2, 0, 2, 0))] = "str"
    delta.modified[("c.py", Span(3, 0, 3, 0))] = ("int", "str")

    stats = delta.stats()
    assert stats["added"] == 1
    assert stats["removed"] == 1
    assert stats["modified"] == 1
    assert stats["total_changes"] == 3


# ============================================================
# M2.3: Snapshot Merge Tests
# ============================================================


def test_snapshot_merge_with_delta():
    """Test merging snapshot with delta."""
    # Old snapshot
    old = PyrightSemanticSnapshot(snapshot_id="s1", project_id="test", files=["a.py"])
    old.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    old.add_type_info("a.py", Span(2, 0, 2, 0), "str")

    # New snapshot (with changes)
    new = PyrightSemanticSnapshot(snapshot_id="s2", project_id="test", files=["a.py"])
    new.add_type_info("a.py", Span(1, 0, 1, 0), "float")  # Modified
    new.add_type_info("a.py", Span(3, 0, 3, 0), "bool")  # Added
    # Removed Span(2, 0)

    # Compute delta
    delta = new.compute_delta(old)

    # Merge
    merged = old.merge_with(delta)

    # Verify merged snapshot
    assert merged.get_type_at("a.py", Span(1, 0, 1, 0)) == "float"  # Modified
    assert merged.get_type_at("a.py", Span(2, 0, 2, 0)) is None  # Removed
    assert merged.get_type_at("a.py", Span(3, 0, 3, 0)) == "bool"  # Added


def test_snapshot_filter_by_files():
    """Test filtering snapshot by files."""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="s1", project_id="test", files=["a.py", "b.py", "c.py"]
    )
    snapshot.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    snapshot.add_type_info("b.py", Span(1, 0, 1, 0), "str")
    snapshot.add_type_info("c.py", Span(1, 0, 1, 0), "bool")

    # Filter to keep only a.py and b.py
    filtered = snapshot.filter_by_files(["a.py", "b.py"])

    assert "a.py" in filtered.files
    assert "b.py" in filtered.files
    assert "c.py" not in filtered.files
    assert len(filtered.typing_info) == 2
    assert filtered.get_type_at("a.py", Span(1, 0, 1, 0)) == "int"
    assert filtered.get_type_at("b.py", Span(1, 0, 1, 0)) == "str"
    assert filtered.get_type_at("c.py", Span(1, 0, 1, 0)) is None


# ============================================================
# M2.4: Incremental Export Tests
# ============================================================


def test_incremental_export_no_previous(daemon, git_repo):
    """Test incremental export with no previous snapshot."""
    code = """
def hello() -> str:
    return "Hello"
"""

    # Open file
    file_path = git_repo / "hello.py"
    daemon.open_file(file_path, code)

    # Incremental export (no previous snapshot)
    changed_files = {file_path: [(1, 4)]}  # def hello
    snapshot = daemon.export_semantic_incremental(
        changed_files=changed_files, previous_snapshot=None
    )

    # Should return snapshot with just changed files
    assert snapshot is not None
    assert len(snapshot.files) >= 1


def test_incremental_export_with_previous(daemon, git_repo):
    """Test incremental export with previous snapshot."""
    # Create previous snapshot
    code1 = """
def func1() -> int:
    return 1
"""
    file1 = git_repo / "file1.py"
    daemon.open_file(file1, code1)
    previous = daemon.export_semantic_for_locations(file1, [(1, 4)])

    # Add new file
    code2 = """
def func2() -> str:
    return "hello"
"""
    file2 = git_repo / "file2.py"
    daemon.open_file(file2, code2)

    # Incremental export (only file2 changed)
    changed_files = {file2: [(1, 4)]}
    new_snapshot = daemon.export_semantic_incremental(
        changed_files=changed_files, previous_snapshot=previous
    )

    # Should contain both files
    assert len(new_snapshot.files) >= 2


def test_incremental_export_with_deleted_files(daemon, git_repo):
    """Test incremental export with deleted files."""
    # Create previous snapshot with 2 files
    code1 = "x = 1"
    code2 = "y = 2"

    file1 = git_repo / "file1.py"
    file2 = git_repo / "file2.py"

    daemon.open_file(file1, code1)
    daemon.open_file(file2, code2)

    previous = daemon.export_semantic_for_files({file1: [(1, 0)], file2: [(1, 0)]})

    # Now file2 is deleted
    # Incremental export
    changed_files = {}  # No changes, just deletion
    deleted_files = [file2]

    new_snapshot = daemon.export_semantic_incremental(
        changed_files=changed_files,
        previous_snapshot=previous,
        deleted_files=deleted_files,
    )

    # Should only contain file1
    assert str(file1) in new_snapshot.files
    assert str(file2) not in new_snapshot.files


# ============================================================
# M2.5: Performance Comparison Tests
# ============================================================


def test_incremental_vs_full_performance(daemon, git_repo):
    """Test performance: incremental vs full analysis."""
    import time

    # Create 5 files
    files = []
    for i in range(5):
        code = f"""
def func{i}() -> int:
    return {i}
"""
        file_path = git_repo / f"file{i}.py"
        daemon.open_file(file_path, code)
        files.append(file_path)

    # Full analysis (all 5 files)
    start = time.perf_counter()
    all_locations = {f: [(1, 4)] for f in files}
    full_snapshot = daemon.export_semantic_for_files(all_locations)
    full_time = time.perf_counter() - start

    # Incremental analysis (1 file changed)
    start = time.perf_counter()
    changed_locations = {files[0]: [(1, 4)]}  # Only file0 changed
    inc_snapshot = daemon.export_semantic_incremental(
        changed_files=changed_locations, previous_snapshot=full_snapshot
    )
    inc_time = time.perf_counter() - start

    # Incremental should be faster (or similar for small examples)
    print(f"\nFull: {full_time*1000:.2f}ms, Incremental: {inc_time*1000:.2f}ms")
    print(f"Speedup: {full_time/inc_time:.1f}x")

    # Both snapshots should be valid
    assert full_snapshot.stats()["total_files"] >= 5
    assert inc_snapshot.stats()["total_files"] >= 5


# ============================================================
# Skip if pyright not installed
# ============================================================


@pytest.fixture(autouse=True)
def skip_if_no_pyright():
    """Skip all tests if pyright-langserver not found."""
    import shutil

    if not shutil.which("pyright-langserver"):
        pytest.skip("pyright-langserver not installed")
