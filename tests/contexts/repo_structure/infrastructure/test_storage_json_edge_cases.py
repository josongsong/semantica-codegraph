"""
Edge Case / Corner Case / Extreme Scenario Tests for JsonFileRepoMapStore.

Tests cover:
1. Concurrent writes (race conditions)
2. Corrupted JSON files
3. Very large snapshots
4. Unicode/special characters in data
5. Disk full / permission errors
6. Cache consistency under stress
7. Symlink attacks
8. Empty/null edge cases
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codegraph_engine.repo_structure.infrastructure.models import (
    RepoMapMetrics,
    RepoMapNode,
    RepoMapSnapshot,
)
from codegraph_engine.repo_structure.infrastructure.storage_json import (
    JsonFileRepoMapStore,
    _FileLock,
    _validate_identifier,
)

# =============================================================================
# Extreme Input Tests
# =============================================================================


class TestExtremeInputs:
    """Test handling of extreme/unusual inputs."""

    @pytest.fixture
    def store(self):
        """Create temporary store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield JsonFileRepoMapStore(base_dir=tmpdir)

    def test_very_long_repo_id(self, store):
        """Very long repo_id should work within filesystem limits."""
        # Most filesystems allow 255 chars
        long_id = "a" * 200
        node = RepoMapNode(
            id=f"repomap:{long_id}:snap1:file:main",
            kind="file",
            name="main.py",
            repo_id=long_id,
            snapshot_id="snap1",
            path="main.py",
            fqn="main",
            depth=1,
            children_ids=[],
            metrics=RepoMapMetrics(),
        )
        snapshot = RepoMapSnapshot(
            repo_id=long_id,
            snapshot_id="snap1",
            root_node_id=node.id,
            nodes=[node],
        )

        store.save_snapshot(snapshot)
        loaded = store.get_snapshot(long_id, "snap1")

        assert loaded is not None
        assert loaded.repo_id == long_id

    def test_unicode_in_node_content(self, store):
        """Unicode characters in node data should be preserved."""
        node = RepoMapNode(
            id="repomap:test:snap1:file:main",
            kind="file",
            name="파일명.py",  # Korean
            repo_id="test",
            snapshot_id="snap1",
            path="src/日本語/中文.py",  # Mixed Asian
            fqn="модуль.функция",  # Russian
            depth=1,
            children_ids=[],
            metrics=RepoMapMetrics(),
            attrs={"description": "🎉 Emoji support 🚀"},
        )
        snapshot = RepoMapSnapshot(
            repo_id="test",
            snapshot_id="snap1",
            root_node_id=node.id,
            nodes=[node],
        )

        store.save_snapshot(snapshot)
        loaded = store.get_snapshot("test", "snap1")

        assert loaded is not None
        assert loaded.nodes[0].name == "파일명.py"
        assert "日本語" in loaded.nodes[0].path
        assert "🎉" in loaded.nodes[0].attrs["description"]

    def test_special_characters_in_fqn(self, store):
        """Special characters in FQN should be handled."""
        node = RepoMapNode(
            id="repomap:test:snap1:func:main",
            kind="function",
            name="__init__",
            repo_id="test",
            snapshot_id="snap1",
            path="main.py",
            fqn="module.<locals>.ClassName.__init__",
            depth=2,
            children_ids=[],
            metrics=RepoMapMetrics(),
        )
        snapshot = RepoMapSnapshot(
            repo_id="test",
            snapshot_id="snap1",
            root_node_id=node.id,
            nodes=[node],
        )

        store.save_snapshot(snapshot)
        loaded = store.get_snapshot("test", "snap1")

        assert loaded is not None
        assert "<locals>" in loaded.nodes[0].fqn

    def test_large_snapshot_1000_nodes(self, store):
        """Large snapshot with 1000 nodes should work."""
        nodes = []
        for i in range(1000):
            nodes.append(
                RepoMapNode(
                    id=f"repomap:test:snap1:file:file_{i}",
                    kind="file",
                    name=f"file_{i}.py",
                    repo_id="test",
                    snapshot_id="snap1",
                    path=f"src/module_{i // 100}/file_{i}.py",
                    fqn=f"module_{i // 100}.file_{i}",
                    depth=2,
                    children_ids=[],
                    metrics=RepoMapMetrics(importance=i / 1000),
                )
            )

        snapshot = RepoMapSnapshot(
            repo_id="test",
            snapshot_id="snap1",
            root_node_id=nodes[0].id,
            nodes=nodes,
        )

        store.save_snapshot(snapshot)
        loaded = store.get_snapshot("test", "snap1")

        assert loaded is not None
        assert len(loaded.nodes) == 1000

    def test_deeply_nested_children(self, store):
        """Deep nesting (100 levels) should work."""
        nodes = []
        for i in range(100):
            node = RepoMapNode(
                id=f"repomap:test:snap1:dir:level_{i}",
                kind="dir",
                name=f"level_{i}",
                repo_id="test",
                snapshot_id="snap1",
                path="/".join([f"level_{j}" for j in range(i + 1)]),
                fqn=".".join([f"level_{j}" for j in range(i + 1)]),
                depth=i,
                children_ids=[f"repomap:test:snap1:dir:level_{i + 1}"] if i < 99 else [],
                metrics=RepoMapMetrics(),
            )
            nodes.append(node)

        snapshot = RepoMapSnapshot(
            repo_id="test",
            snapshot_id="snap1",
            root_node_id=nodes[0].id,
            nodes=nodes,
        )

        store.save_snapshot(snapshot)
        loaded = store.get_snapshot("test", "snap1")

        assert loaded is not None
        assert len(loaded.nodes) == 100
        assert loaded.nodes[99].depth == 99


# =============================================================================
# Corrupted Data Tests
# =============================================================================


class TestCorruptedData:
    """Test handling of corrupted/invalid data."""

    def test_corrupted_json_file(self):
        """Corrupted JSON file should return None with warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            # Create corrupted JSON file
            repo_dir = Path(tmpdir) / "test"
            repo_dir.mkdir()
            corrupt_file = repo_dir / "snap1.json"
            corrupt_file.write_text("{invalid json content")

            # Should return None, not crash
            import warnings

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = store.get_snapshot("test", "snap1")

                assert result is None
                assert len(w) == 1
                assert "Failed to load snapshot" in str(w[0].message)

    def test_empty_json_file(self):
        """Empty JSON file should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            repo_dir = Path(tmpdir) / "test"
            repo_dir.mkdir()
            empty_file = repo_dir / "snap1.json"
            empty_file.write_text("")

            import warnings

            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = store.get_snapshot("test", "snap1")
                assert result is None

    def test_valid_json_invalid_schema(self):
        """Valid JSON but invalid schema should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            repo_dir = Path(tmpdir) / "test"
            repo_dir.mkdir()
            invalid_file = repo_dir / "snap1.json"
            invalid_file.write_text('{"random": "data", "not": "snapshot"}')

            import warnings

            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = store.get_snapshot("test", "snap1")
                assert result is None

    def test_partial_json_write(self):
        """Simulate partial write (power failure)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            repo_dir = Path(tmpdir) / "test"
            repo_dir.mkdir()
            partial_file = repo_dir / "snap1.json"
            # Write partial valid JSON (truncated)
            partial_file.write_text('{"repo_id": "test", "snapshot_id": "snap1", "nodes": [')

            import warnings

            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                result = store.get_snapshot("test", "snap1")
                assert result is None


# =============================================================================
# Concurrent Access Tests
# =============================================================================


class TestConcurrentAccess:
    """Test thread safety and concurrent access."""

    def test_concurrent_reads_same_snapshot(self):
        """Multiple threads reading same snapshot should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            # Create snapshot
            node = RepoMapNode(
                id="repomap:test:snap1:file:main",
                kind="file",
                name="main.py",
                repo_id="test",
                snapshot_id="snap1",
                path="main.py",
                fqn="main",
                depth=1,
                children_ids=[],
                metrics=RepoMapMetrics(),
            )
            snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=node.id,
                nodes=[node],
            )
            store.save_snapshot(snapshot)

            results = []
            errors = []

            def read_snapshot():
                try:
                    for _ in range(10):
                        s = store.get_snapshot("test", "snap1")
                        results.append(s is not None)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=read_snapshot) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
            assert all(results)

    def test_concurrent_writes_different_snapshots(self):
        """Concurrent writes to different snapshots should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)
            errors = []

            def write_snapshot(snap_id):
                try:
                    node = RepoMapNode(
                        id=f"repomap:test:{snap_id}:file:main",
                        kind="file",
                        name="main.py",
                        repo_id="test",
                        snapshot_id=snap_id,
                        path="main.py",
                        fqn="main",
                        depth=1,
                        children_ids=[],
                        metrics=RepoMapMetrics(),
                    )
                    snapshot = RepoMapSnapshot(
                        repo_id="test",
                        snapshot_id=snap_id,
                        root_node_id=node.id,
                        nodes=[node],
                    )
                    store.save_snapshot(snapshot)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=write_snapshot, args=(f"snap{i}",)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0

            # Verify all snapshots exist
            snapshots = store.list_snapshots("test")
            assert len(snapshots) == 10

    def test_concurrent_write_same_snapshot(self):
        """Concurrent writes to same snapshot - last write wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)
            write_times = []

            def write_snapshot(thread_id):
                node = RepoMapNode(
                    id="repomap:test:snap1:file:main",
                    kind="file",
                    name=f"main_thread_{thread_id}.py",
                    repo_id="test",
                    snapshot_id="snap1",
                    path="main.py",
                    fqn="main",
                    depth=1,
                    children_ids=[],
                    metrics=RepoMapMetrics(),
                )
                snapshot = RepoMapSnapshot(
                    repo_id="test",
                    snapshot_id="snap1",
                    root_node_id=node.id,
                    nodes=[node],
                )
                store.save_snapshot(snapshot)
                write_times.append((thread_id, time.time()))

            threads = [threading.Thread(target=write_snapshot, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should have valid snapshot (one of the writes should win)
            store.clear_cache()  # Force reload from disk
            result = store.get_snapshot("test", "snap1")
            assert result is not None
            assert "main_thread_" in result.nodes[0].name


# =============================================================================
# Cache Edge Cases
# =============================================================================


class TestCacheEdgeCases:
    """Test cache behavior edge cases."""

    def test_cache_after_external_delete(self):
        """Cache should handle external file deletion gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir, enable_mtime_check=True)

            # Create and cache snapshot
            node = RepoMapNode(
                id="repomap:test:snap1:file:main",
                kind="file",
                name="main.py",
                repo_id="test",
                snapshot_id="snap1",
                path="main.py",
                fqn="main",
                depth=1,
                children_ids=[],
                metrics=RepoMapMetrics(),
            )
            snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=node.id,
                nodes=[node],
            )
            store.save_snapshot(snapshot)
            store.get_snapshot("test", "snap1")  # Populate cache

            # Delete file externally
            file_path = Path(tmpdir) / "test" / "snap1.json"
            file_path.unlink()

            # Should return None (file deleted)
            result = store.get_snapshot("test", "snap1")
            assert result is None

    def test_cache_after_external_modification(self):
        """Cache should detect external file modification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir, enable_mtime_check=True)

            # Create and cache snapshot
            node = RepoMapNode(
                id="repomap:test:snap1:file:main",
                kind="file",
                name="original.py",
                repo_id="test",
                snapshot_id="snap1",
                path="main.py",
                fqn="main",
                depth=1,
                children_ids=[],
                metrics=RepoMapMetrics(),
            )
            snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=node.id,
                nodes=[node],
            )
            store.save_snapshot(snapshot)
            store.get_snapshot("test", "snap1")  # Populate cache

            # Modify file externally
            time.sleep(0.1)  # Ensure mtime changes
            file_path = Path(tmpdir) / "test" / "snap1.json"
            modified_node = RepoMapNode(
                id="repomap:test:snap1:file:main",
                kind="file",
                name="modified.py",
                repo_id="test",
                snapshot_id="snap1",
                path="main.py",
                fqn="main",
                depth=1,
                children_ids=[],
                metrics=RepoMapMetrics(),
            )
            modified_snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=modified_node.id,
                nodes=[modified_node],
            )
            file_path.write_text(json.dumps(modified_snapshot.model_dump()))

            # Should detect modification and reload
            result = store.get_snapshot("test", "snap1")
            assert result is not None
            assert result.nodes[0].name == "modified.py"

    def test_node_index_consistency_after_delete(self):
        """Node index should be updated after snapshot deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            node = RepoMapNode(
                id="repomap:test:snap1:file:unique_node",
                kind="file",
                name="unique.py",
                repo_id="test",
                snapshot_id="snap1",
                path="unique.py",
                fqn="unique",
                depth=1,
                children_ids=[],
                metrics=RepoMapMetrics(),
            )
            snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=node.id,
                nodes=[node],
            )
            store.save_snapshot(snapshot)

            # Node should be in index
            assert store.get_node("repomap:test:snap1:file:unique_node") is not None

            # Delete snapshot
            store.delete_snapshot("test", "snap1")

            # Node should be removed from index
            assert store.get_node("repomap:test:snap1:file:unique_node") is None


# =============================================================================
# File System Edge Cases
# =============================================================================


class TestFileSystemEdgeCases:
    """Test file system edge cases."""

    def test_readonly_base_directory(self):
        """Should handle read-only directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Make directory read-only
            os.chmod(tmpdir, 0o444)

            try:
                with pytest.raises((PermissionError, OSError)):
                    store = JsonFileRepoMapStore(base_dir=tmpdir)
                    node = RepoMapNode(
                        id="repomap:test:snap1:file:main",
                        kind="file",
                        name="main.py",
                        repo_id="test",
                        snapshot_id="snap1",
                        path="main.py",
                        fqn="main",
                        depth=1,
                        children_ids=[],
                        metrics=RepoMapMetrics(),
                    )
                    snapshot = RepoMapSnapshot(
                        repo_id="test",
                        snapshot_id="snap1",
                        root_node_id=node.id,
                        nodes=[node],
                    )
                    store.save_snapshot(snapshot)
            finally:
                # Restore permissions for cleanup
                os.chmod(tmpdir, 0o755)

    def test_nonexistent_snapshot(self):
        """Getting nonexistent snapshot should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            result = store.get_snapshot("nonexistent", "snap1")
            assert result is None

    def test_list_snapshots_empty_repo(self):
        """Listing snapshots for empty repo should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            result = store.list_snapshots("empty_repo")
            assert result == []

    def test_delete_nonexistent_snapshot(self):
        """Deleting nonexistent snapshot should not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            # Should not raise
            store.delete_snapshot("nonexistent", "snap1")


# =============================================================================
# FileLock Edge Cases
# =============================================================================


class TestFileLockEdgeCases:
    """Test _FileLock edge cases."""

    def test_lock_creates_parent_directory(self):
        """Lock should create parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "deep" / "nested" / "file.json"

            with _FileLock(nested_path):
                assert nested_path.parent.exists()

    def test_lock_cleanup_on_exit(self):
        """Lock file should be cleaned up on exit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.json"
            lock_path = file_path.parent / f".{file_path.name}.lock"

            with _FileLock(file_path):
                assert lock_path.exists()

            # Lock file should be cleaned up
            assert not lock_path.exists()


# =============================================================================
# Query Edge Cases
# =============================================================================


class TestQueryEdgeCases:
    """Test query method edge cases."""

    @pytest.fixture
    def store_with_data(self):
        """Create store with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonFileRepoMapStore(base_dir=tmpdir)

            nodes = [
                RepoMapNode(
                    id="repomap:test:snap1:file:main",
                    kind="file",
                    name="main.py",
                    repo_id="test",
                    snapshot_id="snap1",
                    path="src/main.py",
                    fqn="src.main",
                    depth=1,
                    children_ids=[],
                    metrics=RepoMapMetrics(importance=0.5),
                ),
            ]
            snapshot = RepoMapSnapshot(
                repo_id="test",
                snapshot_id="snap1",
                root_node_id=nodes[0].id,
                nodes=nodes,
            )
            store.save_snapshot(snapshot)
            yield store

    def test_get_nodes_by_path_nonexistent_snapshot(self, store_with_data):
        """Query with nonexistent snapshot should return empty list."""
        result = store_with_data.get_nodes_by_path("test", "nonexistent", "main.py")
        assert result == []

    def test_get_nodes_by_path_no_match(self, store_with_data):
        """Query with no matching path should return empty list."""
        result = store_with_data.get_nodes_by_path("test", "snap1", "nonexistent.py")
        assert result == []

    def test_get_topk_zero(self, store_with_data):
        """get_topk with k=0 should return empty list."""
        result = store_with_data.get_topk_by_importance("test", "snap1", k=0)
        assert result == []

    def test_get_topk_larger_than_nodes(self, store_with_data):
        """get_topk with k larger than node count should return all nodes."""
        result = store_with_data.get_topk_by_importance("test", "snap1", k=1000)
        assert len(result) == 1  # Only 1 node exists

    def test_get_subtree_nonexistent_node(self, store_with_data):
        """get_subtree with nonexistent node should return empty list."""
        result = store_with_data.get_subtree("nonexistent:node:id")
        assert result == []
