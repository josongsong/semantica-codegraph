"""
Tests for Pyright Semantic Snapshot (M1)

RFC-023 M1: JSON serialization tests

Test scope:
- JSON serialization/deserialization
- SemanticSnapshotStore (PostgreSQL)
- Multi-file snapshots
"""

import pytest
from src.foundation.ir.external_analyzers import (
    PyrightSemanticSnapshot,
    SemanticSnapshotStore,
    Span,
)

# M1: JSON Serialization Tests


def test_span_to_dict():
    """Test Span to_dict() serialization"""
    span = Span(10, 5, 12, 8)
    data = span.to_dict()

    assert data == {
        "start_line": 10,
        "start_col": 5,
        "end_line": 12,
        "end_col": 8,
    }


def test_span_from_dict():
    """Test Span from_dict() deserialization"""
    data = {
        "start_line": 10,
        "start_col": 5,
        "end_line": 12,
        "end_col": 8,
    }
    span = Span.from_dict(data)

    assert span.start_line == 10
    assert span.start_col == 5
    assert span.end_line == 12
    assert span.end_col == 8


def test_span_roundtrip():
    """Test Span serialization roundtrip"""
    original = Span(15, 10, 15, 20)
    data = original.to_dict()
    restored = Span.from_dict(data)

    assert original == restored


def test_snapshot_to_dict():
    """Test PyrightSemanticSnapshot to_dict()"""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="test-1",
        project_id="test-project",
        files=["a.py", "b.py"],
    )

    # Add type info
    snapshot.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    snapshot.add_type_info("a.py", Span(2, 0, 2, 0), "str")
    snapshot.add_type_info("b.py", Span(1, 0, 1, 0), "list[int]")

    data = snapshot.to_dict()

    # Verify structure
    assert data["snapshot_id"] == "test-1"
    assert data["project_id"] == "test-project"
    assert data["files"] == ["a.py", "b.py"]
    assert data["version"] == "1.0"
    assert "timestamp" in data
    assert "typing_info" in data
    assert len(data["typing_info"]) == 3

    # Verify typing_info structure
    for entry in data["typing_info"]:
        assert "file_path" in entry
        assert "span" in entry
        assert "type" in entry
        assert isinstance(entry["span"], dict)


def test_snapshot_from_dict():
    """Test PyrightSemanticSnapshot from_dict()"""
    data = {
        "snapshot_id": "test-2",
        "project_id": "test-project",
        "files": ["main.py"],
        "typing_info": [
            {
                "file_path": "main.py",
                "span": {"start_line": 1, "start_col": 0, "end_line": 1, "end_col": 0},
                "type": "int",
            },
            {
                "file_path": "main.py",
                "span": {"start_line": 2, "start_col": 0, "end_line": 2, "end_col": 0},
                "type": "str",
            },
        ],
    }

    snapshot = PyrightSemanticSnapshot.from_dict(data)

    assert snapshot.snapshot_id == "test-2"
    assert snapshot.project_id == "test-project"
    assert snapshot.files == ["main.py"]
    assert len(snapshot.typing_info) == 2

    # Verify type lookups work
    assert snapshot.get_type_at("main.py", Span(1, 0, 1, 0)) == "int"
    assert snapshot.get_type_at("main.py", Span(2, 0, 2, 0)) == "str"


def test_snapshot_to_json():
    """Test PyrightSemanticSnapshot to_json()"""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="test-3",
        project_id="test-project",
        files=["test.py"],
    )
    snapshot.add_type_info("test.py", Span(1, 0, 1, 0), "int")

    json_str = snapshot.to_json()

    # Verify it's valid JSON
    import json

    data = json.loads(json_str)
    assert data["snapshot_id"] == "test-3"


def test_snapshot_from_json():
    """Test PyrightSemanticSnapshot from_json()"""
    import json

    json_data = {
        "snapshot_id": "test-4",
        "project_id": "test-project",
        "files": ["example.py"],
        "typing_info": [
            {
                "file_path": "example.py",
                "span": {"start_line": 5, "start_col": 0, "end_line": 5, "end_col": 0},
                "type": "list[User]",
            }
        ],
    }
    json_str = json.dumps(json_data)

    snapshot = PyrightSemanticSnapshot.from_json(json_str)

    assert snapshot.snapshot_id == "test-4"
    assert snapshot.get_type_at("example.py", Span(5, 0, 5, 0)) == "list[User]"


def test_snapshot_roundtrip():
    """Test full JSON serialization roundtrip"""
    original = PyrightSemanticSnapshot(
        snapshot_id="roundtrip-1",
        project_id="roundtrip-project",
        files=["a.py", "b.py", "c.py"],
    )

    # Add various type info
    original.add_type_info("a.py", Span(1, 0, 1, 0), "int")
    original.add_type_info("a.py", Span(2, 0, 2, 0), "str")
    original.add_type_info("b.py", Span(10, 5, 10, 5), "list[User]")
    original.add_type_info("c.py", Span(20, 0, 22, 0), "Dict[str, int]")

    # Serialize
    json_str = original.to_json()

    # Deserialize
    restored = PyrightSemanticSnapshot.from_json(json_str)

    # Verify
    assert restored.snapshot_id == original.snapshot_id
    assert restored.project_id == original.project_id
    assert restored.files == original.files
    assert len(restored.typing_info) == len(original.typing_info)

    # Verify all type lookups work
    assert restored.get_type_at("a.py", Span(1, 0, 1, 0)) == "int"
    assert restored.get_type_at("a.py", Span(2, 0, 2, 0)) == "str"
    assert restored.get_type_at("b.py", Span(10, 5, 10, 5)) == "list[User]"
    assert restored.get_type_at("c.py", Span(20, 0, 22, 0)) == "Dict[str, int]"


# M1: SemanticSnapshotStore Tests (require PostgreSQL)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires PostgreSQL setup")
async def test_snapshot_store_save_load():
    """Test SemanticSnapshotStore save/load"""
    from src.infra.storage.postgres import PostgresStore

    # Setup
    postgres = PostgresStore(connection_string="postgresql://localhost/test")
    store = SemanticSnapshotStore(postgres)

    # Create snapshot
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="store-test-1",
        project_id="test-project",
        files=["main.py"],
    )
    snapshot.add_type_info("main.py", Span(1, 0, 1, 0), "int")

    # Save
    await store.save_snapshot(snapshot)

    # Load latest
    loaded = await store.load_latest_snapshot("test-project")

    assert loaded is not None
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert loaded.project_id == snapshot.project_id
    assert loaded.get_type_at("main.py", Span(1, 0, 1, 0)) == "int"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires PostgreSQL setup")
async def test_snapshot_store_load_by_id():
    """Test SemanticSnapshotStore load by ID"""
    from src.infra.storage.postgres import PostgresStore

    postgres = PostgresStore(connection_string="postgresql://localhost/test")
    store = SemanticSnapshotStore(postgres)

    # Save snapshot
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="store-test-2",
        project_id="test-project",
        files=["test.py"],
    )
    await store.save_snapshot(snapshot)

    # Load by ID
    loaded = await store.load_snapshot_by_id("store-test-2")

    assert loaded is not None
    assert loaded.snapshot_id == "store-test-2"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires PostgreSQL setup")
async def test_snapshot_store_list():
    """Test SemanticSnapshotStore list snapshots"""
    from src.infra.storage.postgres import PostgresStore

    postgres = PostgresStore(connection_string="postgresql://localhost/test")
    store = SemanticSnapshotStore(postgres)

    # Save multiple snapshots
    for i in range(3):
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"list-test-{i}",
            project_id="list-project",
            files=["test.py"],
        )
        await store.save_snapshot(snapshot)

    # List
    snapshots = await store.list_snapshots("list-project", limit=10)

    assert len(snapshots) >= 3
    assert all("snapshot_id" in s for s in snapshots)
    assert all("timestamp" in s for s in snapshots)


# Edge cases


def test_snapshot_empty_typing_info():
    """Test snapshot with no typing info"""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="empty-1",
        project_id="empty-project",
        files=["empty.py"],
    )

    # Serialize/deserialize
    json_str = snapshot.to_json()
    restored = PyrightSemanticSnapshot.from_json(json_str)

    assert restored.snapshot_id == "empty-1"
    assert len(restored.typing_info) == 0


def test_snapshot_no_files():
    """Test snapshot with no files"""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="nofiles-1",
        project_id="nofiles-project",
        files=[],
    )

    json_str = snapshot.to_json()
    restored = PyrightSemanticSnapshot.from_json(json_str)

    assert restored.snapshot_id == "nofiles-1"
    assert len(restored.files) == 0


def test_snapshot_complex_types():
    """Test snapshot with complex type strings"""
    snapshot = PyrightSemanticSnapshot(
        snapshot_id="complex-1",
        project_id="complex-project",
        files=["complex.py"],
    )

    # Add complex types
    snapshot.add_type_info(
        "complex.py",
        Span(1, 0, 1, 0),
        "Callable[[int, str], Optional[Dict[str, List[User]]]]",
    )

    # Roundtrip
    json_str = snapshot.to_json()
    restored = PyrightSemanticSnapshot.from_json(json_str)

    type_str = restored.get_type_at("complex.py", Span(1, 0, 1, 0))
    assert "Callable" in type_str
    assert "Optional" in type_str
