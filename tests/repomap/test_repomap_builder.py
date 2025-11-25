"""
Tests for RepoMap TreeBuilder and Builder orchestrator.
"""

import pytest

from src.foundation.chunk.models import Chunk
from src.repomap import (
    InMemoryRepoMapStore,
    RepoMapBuildConfig,
    RepoMapBuilder,
    RepoMapQuery,
)


@pytest.fixture
def sample_chunks():
    """Create sample chunk hierarchy for testing."""
    return [
        # Repo root
        Chunk(
            chunk_id="chunk:myrepo:repo:myrepo",
            repo_id="myrepo",
            snapshot_id="test_snapshot",
            project_id=None,
            module_path=None,
            file_path=None,
            kind="repo",
            fqn="myrepo",
            start_line=None,
            end_line=None,
            original_start_line=None,
            original_end_line=None,
            content_hash=None,
            parent_id=None,
            children=["chunk:myrepo:file:src/main.py", "chunk:myrepo:file:tests/test_main.py"],
            language=None,
            symbol_visibility=None,
            symbol_id=None,
            symbol_owner_id=None,
            summary=None,
            importance=None,
        ),
        # Main file
        Chunk(
            chunk_id="chunk:myrepo:file:src/main.py",
            repo_id="myrepo",
            snapshot_id="test_snapshot",
            project_id=None,
            module_path="src",
            file_path="src/main.py",
            kind="file",
            fqn="src.main",
            start_line=1,
            end_line=50,
            original_start_line=1,
            original_end_line=50,
            content_hash="abc123",
            parent_id="chunk:myrepo:repo:myrepo",
            children=["chunk:myrepo:function:src.main.main"],
            language="python",
            symbol_visibility="public",
            symbol_id="py:myrepo:file:src/main.py",
            symbol_owner_id=None,
            summary=None,
            importance=None,
        ),
        # Main function
        Chunk(
            chunk_id="chunk:myrepo:function:src.main.main",
            repo_id="myrepo",
            snapshot_id="test_snapshot",
            project_id=None,
            module_path="src",
            file_path="src/main.py",
            kind="function",
            fqn="src.main.main",
            start_line=10,
            end_line=20,
            original_start_line=10,
            original_end_line=20,
            content_hash="def456",
            parent_id="chunk:myrepo:file:src/main.py",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="py:myrepo:function:src.main.main",
            symbol_owner_id=None,
            summary=None,
            importance=None,
        ),
        # Test file
        Chunk(
            chunk_id="chunk:myrepo:file:tests/test_main.py",
            repo_id="myrepo",
            snapshot_id="test_snapshot",
            project_id=None,
            module_path="tests",
            file_path="tests/test_main.py",
            kind="file",
            fqn="tests.test_main",
            start_line=1,
            end_line=30,
            original_start_line=1,
            original_end_line=30,
            content_hash="test123",
            parent_id="chunk:myrepo:repo:myrepo",
            children=["chunk:myrepo:function:tests.test_main.test_run"],
            language="python",
            symbol_visibility="public",
            symbol_id="py:myrepo:file:tests/test_main.py",
            symbol_owner_id=None,
            summary=None,
            importance=None,
        ),
        # Test function
        Chunk(
            chunk_id="chunk:myrepo:function:tests.test_main.test_run",
            repo_id="myrepo",
            snapshot_id="test_snapshot",
            project_id=None,
            module_path="tests",
            file_path="tests/test_main.py",
            kind="function",
            fqn="tests.test_main.test_run",
            start_line=10,
            end_line=20,
            original_start_line=10,
            original_end_line=20,
            content_hash="test456",
            parent_id="chunk:myrepo:file:tests/test_main.py",
            children=[],
            language="python",
            symbol_visibility="public",
            symbol_id="py:myrepo:function:tests.test_main.test_run",
            symbol_owner_id=None,
            summary=None,
            importance=None,
        ),
    ]


def test_repomap_builder_basic(sample_chunks):
    """Test basic RepoMap building."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig(include_tests=True, min_loc=0)
    builder = RepoMapBuilder(store, config)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    assert snapshot.repo_id == "myrepo"
    assert snapshot.snapshot_id == "main"
    assert len(snapshot.nodes) > 0

    # Check root node exists
    root_node = snapshot.get_node(snapshot.root_node_id)
    assert root_node is not None
    assert root_node.kind == "repo"


def test_repomap_tree_structure(sample_chunks):
    """Test RepoMap tree structure is correct."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig(include_tests=True)  # Include tests
    builder = RepoMapBuilder(store, config)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    # Find file nodes
    file_nodes = [n for n in snapshot.nodes if n.kind == "file"]
    assert len(file_nodes) == 2  # main.py and test_main.py

    # Check function nodes exist
    function_nodes = [n for n in snapshot.nodes if n.kind == "function"]
    assert len(function_nodes) >= 1  # At least main function


def test_repomap_metrics_computation(sample_chunks):
    """Test metrics are computed correctly."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    # Check that metrics are populated
    for node in snapshot.nodes:
        assert node.metrics is not None
        assert node.metrics.importance >= 0.0
        assert node.metrics.importance <= 1.0


def test_entrypoint_detection(sample_chunks):
    """Test entrypoint detection."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig(include_tests=True)
    builder = RepoMapBuilder(store, config)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    # Find main.py file - should be detected as entrypoint
    main_file = next((n for n in snapshot.nodes if n.path == "src/main.py"), None)
    assert main_file is not None
    assert main_file.is_entrypoint is True


def test_test_detection(sample_chunks):
    """Test test file/function detection."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig(include_tests=True)
    builder = RepoMapBuilder(store, config)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    # Find test file - should be detected as test
    test_file = next((n for n in snapshot.nodes if n.path == "tests/test_main.py"), None)
    assert test_file is not None
    assert test_file.is_test is True


def test_repomap_query_top_nodes(sample_chunks):
    """Test querying top nodes by importance."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)
    query = RepoMapQuery(store)

    _ = builder.build("myrepo", "main", sample_chunks)

    top_nodes = query.get_top_nodes("myrepo", "main", top_n=5)
    assert len(top_nodes) <= 5
    assert len(top_nodes) > 0

    # Check nodes are sorted by importance
    for i in range(len(top_nodes) - 1):
        assert top_nodes[i].metrics.importance >= top_nodes[i + 1].metrics.importance


def test_repomap_query_entrypoints(sample_chunks):
    """Test querying entrypoint nodes."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)
    query = RepoMapQuery(store)

    _ = builder.build("myrepo", "main", sample_chunks)

    entrypoints = query.get_entrypoints("myrepo", "main")
    assert len(entrypoints) > 0

    # All returned nodes should be entrypoints
    for node in entrypoints:
        assert node.is_entrypoint is True


def test_repomap_query_search_by_path(sample_chunks):
    """Test searching nodes by path pattern."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)
    query = RepoMapQuery(store)

    _ = builder.build("myrepo", "main", sample_chunks)

    # Search for "main" in path
    results = query.search_by_path("myrepo", "main", "main")
    assert len(results) >= 1

    # All results should contain "main" in path
    for node in results:
        assert node.path is not None
        assert "main" in node.path


def test_repomap_filter_tests(sample_chunks):
    """Test filtering out test files."""
    store = InMemoryRepoMapStore()
    config = RepoMapBuildConfig(include_tests=False)
    builder = RepoMapBuilder(store, config)

    snapshot = builder.build("myrepo", "main", sample_chunks)

    # Test files should still be present but have low importance
    test_nodes = [n for n in snapshot.nodes if n.is_test]
    if test_nodes:
        # Test nodes should have lower importance than non-test nodes
        non_test_nodes = [n for n in snapshot.nodes if not n.is_test and n.kind == "file"]
        if non_test_nodes:
            avg_test_importance = sum(n.metrics.importance for n in test_nodes) / len(test_nodes)
            avg_normal_importance = sum(n.metrics.importance for n in non_test_nodes) / len(non_test_nodes)
            assert avg_test_importance < avg_normal_importance


def test_repomap_storage_persistence(sample_chunks):
    """Test snapshot persistence and retrieval."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)

    # Build and save snapshot
    snapshot1 = builder.build("myrepo", "main", sample_chunks)

    # Retrieve snapshot
    snapshot2 = builder.get_snapshot("myrepo", "main")

    assert snapshot2 is not None
    assert snapshot2.repo_id == snapshot1.repo_id
    assert snapshot2.snapshot_id == snapshot1.snapshot_id
    assert len(snapshot2.nodes) == len(snapshot1.nodes)


def test_repomap_list_snapshots(sample_chunks):
    """Test listing snapshots for a repo."""
    store = InMemoryRepoMapStore()
    builder = RepoMapBuilder(store)

    # Build multiple snapshots
    builder.build("myrepo", "main", sample_chunks)
    builder.build("myrepo", "feature", sample_chunks)

    # List snapshots
    snapshots = builder.list_snapshots("myrepo")
    assert len(snapshots) == 2
    assert "main" in snapshots
    assert "feature" in snapshots
