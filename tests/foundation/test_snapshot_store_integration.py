"""
RFC-023 M1: SemanticSnapshotStore Integration Tests

Tests PostgreSQL persistence with real database connection.

Requirements:
- PostgreSQL running on port 7201
- Migration 005 applied (pyright_semantic_snapshots table)

Run with:
    SEMANTICA_DATABASE_URL="postgresql://codegraph:codegraph_dev@localhost:7201/codegraph" pytest tests/foundation/test_snapshot_store_integration.py -v
"""

import os

import pytest
import pytest_asyncio

from src.foundation.ir.external_analyzers import (
    PyrightSemanticSnapshot,
    SemanticSnapshotStore,
    Span,
)
from src.infra.storage.postgres import PostgresStore

# Check if PostgreSQL is available
DATABASE_URL = os.getenv(
    "SEMANTICA_DATABASE_URL",
    "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph",
)


@pytest_asyncio.fixture
async def postgres_store():
    """Create PostgresStore instance."""
    store = PostgresStore(connection_string=DATABASE_URL)
    await store.initialize()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def snapshot_store(postgres_store):
    """Create SemanticSnapshotStore instance."""
    store = SemanticSnapshotStore(postgres_store)
    yield store
    # Cleanup: clear cache after each test
    store.clear_cache()


@pytest.fixture
def sample_snapshot():
    """Create sample snapshot for testing."""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="test-snapshot-1",
        project_id="test-project",
        files=["main.py", "utils.py"],
    )

    # Add type info
    snapshot.add_type_info("main.py", Span(1, 0, 1, 0), "int")
    snapshot.add_type_info("main.py", Span(2, 0, 2, 0), "str")
    snapshot.add_type_info("main.py", Span(10, 5, 10, 20), "list[User]")
    snapshot.add_type_info("utils.py", Span(5, 0, 5, 0), "Dict[str, int]")

    return snapshot


# ============================================================
# M1.1: Save and Load Snapshots
# ============================================================


@pytest.mark.asyncio
async def test_save_and_load_latest(snapshot_store, sample_snapshot):
    """
    M1.1.1: Test save and load latest snapshot.

    Verifies:
    - Snapshot can be saved to PostgreSQL
    - Latest snapshot can be loaded by project_id
    - All typing info is preserved
    """
    # Save snapshot
    await snapshot_store.save_snapshot(sample_snapshot)

    # Load latest
    loaded = await snapshot_store.load_latest_snapshot("test-project")

    # Verify
    assert loaded is not None
    assert loaded.snapshot_id == "test-snapshot-1"
    assert loaded.project_id == "test-project"
    assert loaded.files == ["main.py", "utils.py"]
    assert len(loaded.typing_info) == 4

    # Verify typing info preserved
    assert loaded.get_type_at("main.py", Span(1, 0, 1, 0)) == "int"
    assert loaded.get_type_at("main.py", Span(2, 0, 2, 0)) == "str"
    assert loaded.get_type_at("main.py", Span(10, 5, 10, 20)) == "list[User]"
    assert loaded.get_type_at("utils.py", Span(5, 0, 5, 0)) == "Dict[str, int]"


@pytest.mark.asyncio
async def test_load_by_id(snapshot_store, sample_snapshot):
    """
    M1.1.2: Test load snapshot by ID.

    Verifies:
    - Snapshot can be loaded by specific snapshot_id
    """
    # Save
    await snapshot_store.save_snapshot(sample_snapshot)

    # Load by ID
    loaded = await snapshot_store.load_snapshot_by_id("test-snapshot-1")

    # Verify
    assert loaded is not None
    assert loaded.snapshot_id == "test-snapshot-1"
    assert len(loaded.typing_info) == 4


@pytest.mark.asyncio
async def test_load_nonexistent_snapshot(snapshot_store):
    """
    M1.1.3: Test loading non-existent snapshot returns None.
    """
    loaded = await snapshot_store.load_latest_snapshot("nonexistent-project")
    assert loaded is None

    loaded_by_id = await snapshot_store.load_snapshot_by_id("nonexistent-id")
    assert loaded_by_id is None


# ============================================================
# M1.2: Multiple Snapshots
# ============================================================


@pytest.mark.asyncio
async def test_multiple_snapshots_same_project(snapshot_store):
    """
    M1.2.1: Test multiple snapshots for same project.

    Verifies:
    - Multiple snapshots can be saved
    - load_latest_snapshot returns most recent
    """
    # Save 3 snapshots for same project
    for i in range(3):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"multi-test-{i}",
            project_id="multi-project",
            files=[f"file{i}.py"],
        )
        snapshot.add_type_info(f"file{i}.py", Span(1, 0, 1, 0), f"Type{i}")
        await snapshot_store.save_snapshot(snapshot)

    # Load latest should return most recent (multi-test-2)
    latest = await snapshot_store.load_latest_snapshot("multi-project")

    assert latest is not None
    assert latest.snapshot_id == "multi-test-2"


@pytest.mark.asyncio
async def test_list_snapshots(snapshot_store):
    """
    M1.2.2: Test listing snapshots for a project.

    Verifies:
    - list_snapshots returns all snapshots
    - Snapshots ordered by timestamp DESC (most recent first)
    """
    project_id = "list-test-project"

    # Save 5 snapshots
    for i in range(5):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"list-{i}",
            project_id=project_id,
            files=["test.py"],
        )
        await snapshot_store.save_snapshot(snapshot)

    # List all
    snapshots = await snapshot_store.list_snapshots(project_id, limit=10)

    # Verify
    assert len(snapshots) >= 5
    assert all("snapshot_id" in s for s in snapshots)
    assert all("timestamp" in s for s in snapshots)
    assert all("project_id" in s for s in snapshots)
    assert all(s["project_id"] == project_id for s in snapshots)

    # First one should be most recent (list-4)
    assert snapshots[0]["snapshot_id"] == "list-4"


@pytest.mark.asyncio
async def test_list_snapshots_with_limit(snapshot_store):
    """
    M1.2.3: Test list_snapshots respects limit parameter.
    """
    project_id = "limit-test-project"

    # Save 10 snapshots
    for i in range(10):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"limit-{i}",
            project_id=project_id,
            files=["test.py"],
        )
        await snapshot_store.save_snapshot(snapshot)

    # List with limit=3
    snapshots = await snapshot_store.list_snapshots(project_id, limit=3)

    # Should return exactly 3 (or fewer if less exist)
    assert len(snapshots) <= 3


# ============================================================
# M1.3: Delete Old Snapshots
# ============================================================


@pytest.mark.asyncio
async def test_delete_old_snapshots(snapshot_store):
    """
    M1.3.1: Test deleting old snapshots.

    Verifies:
    - delete_old_snapshots keeps only N most recent
    - Returns count of deleted snapshots
    """
    project_id = "delete-test-project"

    # Save 10 snapshots
    for i in range(10):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"delete-{i}",
            project_id=project_id,
            files=["test.py"],
        )
        await snapshot_store.save_snapshot(snapshot)

    # Keep only 3 most recent
    deleted_count = await snapshot_store.delete_old_snapshots(project_id, keep_count=3)

    # Should delete 7 (10 - 3)
    assert deleted_count == 7

    # List remaining
    remaining = await snapshot_store.list_snapshots(project_id, limit=10)
    assert len(remaining) == 3

    # Should keep most recent (delete-9, delete-8, delete-7)
    snapshot_ids = [s["snapshot_id"] for s in remaining]
    assert "delete-9" in snapshot_ids
    assert "delete-8" in snapshot_ids
    assert "delete-7" in snapshot_ids


@pytest.mark.asyncio
async def test_delete_old_snapshots_no_extras(snapshot_store):
    """
    M1.3.2: Test delete when there are fewer snapshots than keep_count.
    """
    project_id = "delete-few-project"

    # Save only 2 snapshots
    for i in range(2):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"few-{i}",
            project_id=project_id,
            files=["test.py"],
        )
        await snapshot_store.save_snapshot(snapshot)

    # Try to keep 5 (more than exist)
    deleted_count = await snapshot_store.delete_old_snapshots(project_id, keep_count=5)

    # Should delete 0
    assert deleted_count == 0

    # All 2 should remain
    remaining = await snapshot_store.list_snapshots(project_id, limit=10)
    assert len(remaining) == 2


# ============================================================
# M1.4: Caching
# ============================================================


@pytest.mark.asyncio
async def test_cache_hit_for_latest(snapshot_store, sample_snapshot):
    """
    M1.4.1: Test cache works for load_latest_snapshot.

    Verifies:
    - First load populates cache
    - Second load uses cache (no DB query)
    """
    # Save snapshot
    await snapshot_store.save_snapshot(sample_snapshot)

    # First load (should hit DB)
    loaded1 = await snapshot_store.load_latest_snapshot("test-project")

    # Second load (should hit cache)
    loaded2 = await snapshot_store.load_latest_snapshot("test-project")

    # Should be same object from cache
    assert loaded1 is loaded2


@pytest.mark.asyncio
async def test_cache_hit_for_id(snapshot_store, sample_snapshot):
    """
    M1.4.2: Test cache works for load_snapshot_by_id.
    """
    # Save
    await snapshot_store.save_snapshot(sample_snapshot)

    # Load by ID twice
    loaded1 = await snapshot_store.load_snapshot_by_id("test-snapshot-1")
    loaded2 = await snapshot_store.load_snapshot_by_id("test-snapshot-1")

    # Should be same object
    assert loaded1 is loaded2


@pytest.mark.asyncio
async def test_clear_cache(snapshot_store, sample_snapshot):
    """
    M1.4.3: Test cache can be cleared.
    """
    # Save and load (populate cache)
    await snapshot_store.save_snapshot(sample_snapshot)
    loaded1 = await snapshot_store.load_latest_snapshot("test-project")

    # Clear cache
    snapshot_store.clear_cache()

    # Load again (should hit DB, different object)
    loaded2 = await snapshot_store.load_latest_snapshot("test-project")

    # Should be different objects
    assert loaded1 is not loaded2
    # But content should be same
    assert loaded1.snapshot_id == loaded2.snapshot_id


# ============================================================
# M1.5: Update Existing Snapshot
# ============================================================


@pytest.mark.asyncio
async def test_update_existing_snapshot(snapshot_store):
    """
    M1.5.1: Test updating existing snapshot (ON CONFLICT DO UPDATE).

    Verifies:
    - Saving with same snapshot_id updates existing record
    """
    project_id = "update-project"
    snapshot_id = "update-1"

    # Create and save initial snapshot
    snapshot1 = PyrightSemanticSnapshot(
        snapshot_id=snapshot_id,
        project_id=project_id,
        files=["old.py"],
    )
    snapshot1.add_type_info("old.py", Span(1, 0, 1, 0), "OldType")
    await snapshot_store.save_snapshot(snapshot1)

    # Create updated snapshot with same ID
    snapshot2 = PyrightSemanticSnapshot(
        snapshot_id=snapshot_id,
        project_id=project_id,
        files=["new.py"],
    )
    snapshot2.add_type_info("new.py", Span(1, 0, 1, 0), "NewType")
    await snapshot_store.save_snapshot(snapshot2)

    # Load - should get updated version
    loaded = await snapshot_store.load_snapshot_by_id(snapshot_id)

    assert loaded is not None
    assert loaded.files == ["new.py"]
    assert loaded.get_type_at("new.py", Span(1, 0, 1, 0)) == "NewType"
    assert loaded.get_type_at("old.py", Span(1, 0, 1, 0)) is None


# ============================================================
# M1.6: Complex Type Preservation
# ============================================================


@pytest.mark.asyncio
async def test_complex_types_preserved(snapshot_store):
    """
    M1.6.1: Test complex Python types are preserved.

    Verifies:
    - Generic types: List[T], Dict[K, V], Optional[T]
    - Callable types
    - Union types
    - Nested generics
    """
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="complex-types-1",
        project_id="complex-project",
        files=["types.py"],
    )

    # Add complex types
    complex_types = [
        ("List[User]", Span(1, 0, 1, 0)),
        ("Dict[str, int]", Span(2, 0, 2, 0)),
        ("Optional[str]", Span(3, 0, 3, 0)),
        ("Callable[[int, str], bool]", Span(4, 0, 4, 0)),
        ("Union[int, str, None]", Span(5, 0, 5, 0)),
        ("Dict[str, List[Optional[User]]]", Span(6, 0, 6, 0)),
    ]

    for type_str, span in complex_types:
        snapshot.add_type_info("types.py", span, type_str)

    # Save and load
    await snapshot_store.save_snapshot(snapshot)
    loaded = await snapshot_store.load_snapshot_by_id("complex-types-1")

    # Verify all types preserved exactly
    for type_str, span in complex_types:
        assert loaded.get_type_at("types.py", span) == type_str


# ============================================================
# M1.7: Multi-file Snapshots
# ============================================================


@pytest.mark.asyncio
async def test_large_multi_file_snapshot(snapshot_store):
    """
    M1.7.1: Test large snapshot with many files and types.

    Verifies:
    - Can handle realistic project size
    - Performance is acceptable
    """
    import time

    snapshot = PyrightSemanticSnapshot(
        snapshot_id="large-1",
        project_id="large-project",
        files=[f"file{i}.py" for i in range(50)],
    )

    # Add 1000 type annotations across 50 files
    for file_idx in range(50):
        file_path = f"file{file_idx}.py"
        for line in range(20):
            snapshot.add_type_info(
                file_path,
                Span(line, 0, line, 0),
                f"Type{file_idx}_{line}",
            )

    # Save (measure time)
    start = time.perf_counter()
    await snapshot_store.save_snapshot(snapshot)
    save_time = (time.perf_counter() - start) * 1000

    # Load (measure time)
    start = time.perf_counter()
    loaded = await snapshot_store.load_snapshot_by_id("large-1")
    load_time = (time.perf_counter() - start) * 1000

    # Verify
    assert loaded is not None
    assert len(loaded.files) == 50
    assert len(loaded.typing_info) == 1000

    # Performance check (should be < 1 second for save/load)
    assert save_time < 1000, f"Save too slow: {save_time:.2f}ms"
    assert load_time < 1000, f"Load too slow: {load_time:.2f}ms"

    print(f"\n  ✓ Large snapshot: Save={save_time:.2f}ms, Load={load_time:.2f}ms")
