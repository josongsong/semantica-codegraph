"""
Tests for RepoMap Incremental Updater

Verifies incremental update logic for RepoMap.
"""

from src.foundation.chunk.incremental import ChunkRefreshResult
from src.foundation.chunk.models import Chunk
from src.repomap import (
    InMemoryRepoMapStore,
    RepoMapBuildConfig,
    RepoMapBuilder,
    RepoMapIncrementalUpdater,
)


def create_test_chunk(**overrides):
    """Helper to create test Chunk with all required fields."""
    defaults = {
        "chunk_id": "chunk:test:1",
        "repo_id": "test_repo",
        "project_id": None,
        "module_path": None,
        "file_path": "src/test.py",
        "kind": "function",
        "fqn": "test_func",
        "start_line": 1,
        "end_line": 10,
        "original_start_line": 1,
        "original_end_line": 10,
        "content_hash": "abc123",
        "parent_id": None,
        "children": [],
        "language": "python",
        "symbol_visibility": "public",
        "symbol_id": None,
        "symbol_owner_id": None,
        "summary": None,
        "importance": None,
        "attrs": {},
    }
    defaults.update(overrides)
    return Chunk(**defaults)


def test_incremental_updater_initialization():
    """Test incremental updater can be initialized."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig()

    updater = RepoMapIncrementalUpdater(store=store, config=config)

    assert updater.store == store
    assert updater.config == config


def test_should_rebuild_full_threshold():
    """Test full rebuild decision based on change threshold."""
    store = InMemoryRepoMapStore()
    updater = RepoMapIncrementalUpdater(store=store)

    # Create initial snapshot
    chunks = [
        create_test_chunk(
            chunk_id=f"chunk:test:{i}",
            file_path=f"src/file{i}.py",
            fqn=f"func{i}",
        )
        for i in range(10)
    ]

    builder = RepoMapBuilder(store=store)
    snapshot = builder.build("test_repo", "snapshot:1", chunks)

    # Small change (10% of nodes) → incremental
    small_refresh = ChunkRefreshResult(
        added_chunks=[],
        updated_chunks=[chunks[0]],  # 1 out of 10
        deleted_chunks=[],
        renamed_chunks=[],
        drifted_chunks=[],
    )

    assert not updater._should_rebuild_full(small_refresh, snapshot)

    # Large change (60% of nodes) → full rebuild
    large_refresh = ChunkRefreshResult(
        added_chunks=[],
        updated_chunks=chunks[:6],  # 6 out of 10
        deleted_chunks=[],
        renamed_chunks=[],
        drifted_chunks=[],
    )

    assert updater._should_rebuild_full(large_refresh, snapshot)


def test_get_affected_files():
    """Test extraction of affected files from refresh result."""
    store = InMemoryRepoMapStore()
    updater = RepoMapIncrementalUpdater(store=store)

    refresh = ChunkRefreshResult(
        added_chunks=[
            create_test_chunk(chunk_id="c1", file_path="src/new.py"),
        ],
        updated_chunks=[
            create_test_chunk(chunk_id="c2", file_path="src/updated.py"),
        ],
        deleted_chunks=[
            create_test_chunk(chunk_id="c3", file_path="src/deleted.py"),
        ],
        renamed_chunks=[],
        drifted_chunks=[],
    )

    affected = updater._get_affected_files(refresh)

    assert affected == {"src/new.py", "src/updated.py", "src/deleted.py"}


def test_incremental_update_full_rebuild():
    """Test incremental updater falls back to full rebuild when needed."""
    store = InMemoryRepoMapStore()
    updater = RepoMapIncrementalUpdater(store=store)

    # No previous snapshot → full rebuild
    chunks = [
        create_test_chunk(
            chunk_id=f"chunk:test:{i}",
            file_path=f"src/file{i}.py",
        )
        for i in range(5)
    ]

    refresh = ChunkRefreshResult(
        added_chunks=chunks,
        updated_chunks=[],
        deleted_chunks=[],
        renamed_chunks=[],
        drifted_chunks=[],
    )

    snapshot = updater.update(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        refresh_result=refresh,
        all_chunks=chunks,
    )

    assert snapshot.repo_id == "test_repo"
    assert snapshot.snapshot_id == "snapshot:1"
    assert len(snapshot.nodes) > 0


def test_incremental_update_small_change():
    """Test incremental update with small file change."""
    store = InMemoryRepoMapStore()

    # Build initial snapshot
    initial_chunks = [
        create_test_chunk(
            chunk_id=f"chunk:test:{i}",
            file_path=f"src/file{i}.py",
            fqn=f"func{i}",
        )
        for i in range(5)
    ]

    builder = RepoMapBuilder(store=store)
    builder.build("test_repo", "snapshot:1", initial_chunks)

    # Update one file
    updated_chunk = create_test_chunk(
        chunk_id="chunk:test:0",
        file_path="src/file0.py",
        fqn="func0_updated",
        content_hash="new_hash",
    )

    all_chunks = initial_chunks[1:] + [updated_chunk]

    refresh = ChunkRefreshResult(
        added_chunks=[],
        updated_chunks=[updated_chunk],
        deleted_chunks=[],
        renamed_chunks=[],
        drifted_chunks=[],
    )

    # Incremental update
    updater = RepoMapIncrementalUpdater(store=store)
    new_snapshot = updater.update(
        repo_id="test_repo",
        snapshot_id="snapshot:2",
        refresh_result=refresh,
        all_chunks=all_chunks,
    )

    assert new_snapshot.snapshot_id == "snapshot:2"
    assert len(new_snapshot.nodes) > 0

    # Verify updated file is in new snapshot
    file_nodes = [n for n in new_snapshot.nodes if n.path == "src/file0.py"]
    assert len(file_nodes) > 0
