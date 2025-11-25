"""
Integration Tests for PostgresRepoMapStore

These tests require a running PostgreSQL instance.
To run:
  1. docker-compose -f docker-compose.test.yml up -d postgres-test
  2. Apply migrations:
     psql -h localhost -p 5433 -U codegraph_test -d codegraph_test \
       -f migrations/001_create_repomap_tables.sql
  3. pytest tests/repomap/test_postgres_store.py -m integration
  4. docker-compose -f docker-compose.test.yml down -v
"""

import os

import pytest

pytest.importorskip("asyncpg")

from src.foundation.chunk.models import Chunk
from src.repomap import RepoMapBuilder
from src.repomap.models import RepoMapMetrics, RepoMapNode, RepoMapSnapshot
from src.repomap.storage_postgres import PostgresRepoMapStore

# Test database connection from docker-compose.test.yml
TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql://codegraph_test:test_password@localhost:5433/codegraph_test",
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


@pytest.fixture(scope="module")
def postgres_store():
    """Create PostgresRepoMapStore for integration tests."""
    try:
        store = PostgresRepoMapStore(TEST_DB_URL)
        yield store
    except ImportError:
        pytest.skip("asyncpg not installed")
    except Exception as e:
        pytest.skip(f"Cannot connect to test database: {e}")


@pytest.fixture(autouse=True)
def cleanup(postgres_store):
    """Clean up test data after each test."""
    yield
    # Delete all test snapshots
    try:
        snapshots = postgres_store.list_snapshots("test_repo")
        for snapshot_id in snapshots:
            postgres_store.delete_snapshot("test_repo", snapshot_id)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
def test_save_and_get_snapshot(postgres_store):
    """Test saving and retrieving a snapshot."""
    # Create test nodes
    node1 = RepoMapNode(
        id="node:test:1",
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        kind="file",
        name="test.py",
        path="src/test.py",
        fqn=None,
        parent_id=None,
        children_ids=["node:test:2"],
        depth=0,
        chunk_ids=["chunk:test:1"],
        graph_node_ids=[],
        metrics=RepoMapMetrics(loc=100, symbol_count=5),
        language="python",
    )

    node2 = RepoMapNode(
        id="node:test:2",
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        kind="function",
        name="test_func",
        path="src/test.py",
        fqn="test.test_func",
        parent_id="node:test:1",
        children_ids=[],
        depth=1,
        chunk_ids=["chunk:test:2"],
        graph_node_ids=[],
        metrics=RepoMapMetrics(loc=20, symbol_count=1, importance=0.85),
        language="python",
        is_entrypoint=True,
    )

    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        root_node_id="node:test:1",
        nodes=[node1, node2],
    )

    # Save snapshot
    postgres_store.save_snapshot(snapshot)

    # Retrieve snapshot
    retrieved = postgres_store.get_snapshot("test_repo", "snapshot:1")

    assert retrieved is not None
    assert retrieved.repo_id == "test_repo"
    assert retrieved.snapshot_id == "snapshot:1"
    assert retrieved.root_node_id == "node:test:1"
    assert len(retrieved.nodes) == 2

    # Check node data
    node_map = {n.id: n for n in retrieved.nodes}
    assert "node:test:1" in node_map
    assert "node:test:2" in node_map

    retrieved_node1 = node_map["node:test:1"]
    assert retrieved_node1.kind == "file"
    assert retrieved_node1.name == "test.py"
    assert retrieved_node1.metrics.loc == 100
    assert retrieved_node1.children_ids == ["node:test:2"]

    retrieved_node2 = node_map["node:test:2"]
    assert retrieved_node2.parent_id == "node:test:1"
    assert retrieved_node2.metrics.importance == 0.85
    assert retrieved_node2.is_entrypoint is True


@pytest.mark.integration
def test_list_snapshots(postgres_store):
    """Test listing snapshots for a repo."""
    # Create and save multiple snapshots
    for i in range(3):
        snapshot = RepoMapSnapshot(
            repo_id="test_repo",
            snapshot_id=f"snapshot:{i}",
            root_node_id=f"node:test:{i}",
            nodes=[
                RepoMapNode(
                    id=f"node:test:{i}",
                    repo_id="test_repo",
                    snapshot_id=f"snapshot:{i}",
                    kind="file",
                    name=f"test{i}.py",
                    path=f"src/test{i}.py",
                    fqn=None,
                    parent_id=None,
                    children_ids=[],
                    depth=0,
                    chunk_ids=[],
                    graph_node_ids=[],
                    metrics=RepoMapMetrics(),
                    language="python",
                )
            ],
        )
        postgres_store.save_snapshot(snapshot)

    # List snapshots
    snapshots = postgres_store.list_snapshots("test_repo")

    assert len(snapshots) == 3
    assert "snapshot:0" in snapshots
    assert "snapshot:1" in snapshots
    assert "snapshot:2" in snapshots


@pytest.mark.integration
def test_delete_snapshot(postgres_store):
    """Test deleting a snapshot."""
    # Create snapshot
    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:delete",
        root_node_id="node:test:1",
        nodes=[
            RepoMapNode(
                id="node:test:1",
                repo_id="test_repo",
                snapshot_id="snapshot:delete",
                kind="file",
                name="test.py",
                path="src/test.py",
                fqn=None,
                parent_id=None,
                children_ids=[],
                depth=0,
                chunk_ids=[],
                graph_node_ids=[],
                metrics=RepoMapMetrics(),
                language="python",
            )
        ],
    )
    postgres_store.save_snapshot(snapshot)

    # Verify it exists
    assert postgres_store.get_snapshot("test_repo", "snapshot:delete") is not None

    # Delete it
    postgres_store.delete_snapshot("test_repo", "snapshot:delete")

    # Verify it's gone
    assert postgres_store.get_snapshot("test_repo", "snapshot:delete") is None


@pytest.mark.integration
def test_get_node(postgres_store):
    """Test getting a single node by ID."""
    node = RepoMapNode(
        id="node:test:single",
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        kind="function",
        name="test_func",
        path="src/test.py",
        fqn="test.test_func",
        parent_id=None,
        children_ids=[],
        depth=0,
        chunk_ids=["chunk:test:1"],
        graph_node_ids=["graph:node:1"],
        metrics=RepoMapMetrics(pagerank=0.95),
        language="python",
    )

    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        root_node_id="node:test:single",
        nodes=[node],
    )
    postgres_store.save_snapshot(snapshot)

    # Get node
    retrieved = postgres_store.get_node("node:test:single")

    assert retrieved is not None
    assert retrieved.id == "node:test:single"
    assert retrieved.name == "test_func"
    assert retrieved.metrics.pagerank == 0.95
    assert retrieved.chunk_ids == ["chunk:test:1"]
    assert retrieved.graph_node_ids == ["graph:node:1"]


@pytest.mark.integration
def test_get_nodes_by_path(postgres_store):
    """Test getting nodes by file path."""
    nodes = [
        RepoMapNode(
            id=f"node:test:{i}",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="function",
            name=f"func{i}",
            path="src/test.py",
            fqn=f"test.func{i}",
            parent_id=None,
            children_ids=[],
            depth=0,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        )
        for i in range(3)
    ]

    # Add a node with different path
    nodes.append(
        RepoMapNode(
            id="node:test:other",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="function",
            name="other_func",
            path="src/other.py",
            fqn="other.other_func",
            parent_id=None,
            children_ids=[],
            depth=0,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        )
    )

    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        root_node_id="node:test:0",
        nodes=nodes,
    )
    postgres_store.save_snapshot(snapshot)

    # Query by path
    retrieved = postgres_store.get_nodes_by_path("test_repo", "snapshot:1", "src/test.py")

    assert len(retrieved) == 3
    assert all(n.path == "src/test.py" for n in retrieved)


@pytest.mark.integration
def test_get_nodes_by_fqn(postgres_store):
    """Test getting nodes by FQN."""
    node = RepoMapNode(
        id="node:test:fqn",
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        kind="function",
        name="target_func",
        path="src/test.py",
        fqn="module.TargetClass.target_func",
        parent_id=None,
        children_ids=[],
        depth=0,
        chunk_ids=[],
        graph_node_ids=[],
        metrics=RepoMapMetrics(),
        language="python",
    )

    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        root_node_id="node:test:fqn",
        nodes=[node],
    )
    postgres_store.save_snapshot(snapshot)

    # Query by FQN
    retrieved = postgres_store.get_nodes_by_fqn("test_repo", "snapshot:1", "module.TargetClass.target_func")

    assert len(retrieved) == 1
    assert retrieved[0].fqn == "module.TargetClass.target_func"
    assert retrieved[0].name == "target_func"


@pytest.mark.integration
def test_get_subtree(postgres_store):
    """Test getting node subtree with recursive query."""
    # Create tree structure:
    # root (depth=0)
    #   ├── child1 (depth=1)
    #   │   └── grandchild1 (depth=2)
    #   └── child2 (depth=1)

    nodes = [
        RepoMapNode(
            id="node:root",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="file",
            name="root.py",
            path="src/root.py",
            fqn=None,
            parent_id=None,
            children_ids=["node:child1", "node:child2"],
            depth=0,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        ),
        RepoMapNode(
            id="node:child1",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="class",
            name="Child1",
            path="src/root.py",
            fqn="root.Child1",
            parent_id="node:root",
            children_ids=["node:grandchild1"],
            depth=1,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        ),
        RepoMapNode(
            id="node:grandchild1",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="function",
            name="grandchild_func",
            path="src/root.py",
            fqn="root.Child1.grandchild_func",
            parent_id="node:child1",
            children_ids=[],
            depth=2,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        ),
        RepoMapNode(
            id="node:child2",
            repo_id="test_repo",
            snapshot_id="snapshot:1",
            kind="function",
            name="child2_func",
            path="src/root.py",
            fqn="root.child2_func",
            parent_id="node:root",
            children_ids=[],
            depth=1,
            chunk_ids=[],
            graph_node_ids=[],
            metrics=RepoMapMetrics(),
            language="python",
        ),
    ]

    snapshot = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:1",
        root_node_id="node:root",
        nodes=nodes,
    )
    postgres_store.save_snapshot(snapshot)

    # Get subtree from root (should get all 4 nodes)
    subtree = postgres_store.get_subtree("node:root")
    assert len(subtree) == 4
    subtree_ids = {n.id for n in subtree}
    assert subtree_ids == {"node:root", "node:child1", "node:child2", "node:grandchild1"}

    # Get subtree from child1 (should get 2 nodes: child1 and grandchild1)
    subtree = postgres_store.get_subtree("node:child1")
    assert len(subtree) == 2
    subtree_ids = {n.id for n in subtree}
    assert subtree_ids == {"node:child1", "node:grandchild1"}

    # Get subtree from leaf node (should get 1 node)
    subtree = postgres_store.get_subtree("node:grandchild1")
    assert len(subtree) == 1
    assert subtree[0].id == "node:grandchild1"


@pytest.mark.integration
def test_upsert_snapshot(postgres_store):
    """Test that saving the same snapshot twice upserts correctly."""
    # Create initial snapshot
    snapshot1 = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:upsert",
        root_node_id="node:test:1",
        nodes=[
            RepoMapNode(
                id="node:test:1",
                repo_id="test_repo",
                snapshot_id="snapshot:upsert",
                kind="file",
                name="test.py",
                path="src/test.py",
                fqn=None,
                parent_id=None,
                children_ids=[],
                depth=0,
                chunk_ids=[],
                graph_node_ids=[],
                metrics=RepoMapMetrics(loc=100),
                language="python",
            )
        ],
    )
    postgres_store.save_snapshot(snapshot1)

    # Update snapshot with different data
    snapshot2 = RepoMapSnapshot(
        repo_id="test_repo",
        snapshot_id="snapshot:upsert",
        root_node_id="node:test:2",  # Different root
        nodes=[
            RepoMapNode(
                id="node:test:2",
                repo_id="test_repo",
                snapshot_id="snapshot:upsert",
                kind="file",
                name="updated.py",
                path="src/updated.py",
                fqn=None,
                parent_id=None,
                children_ids=[],
                depth=0,
                chunk_ids=[],
                graph_node_ids=[],
                metrics=RepoMapMetrics(loc=200),  # Different metrics
                language="python",
            )
        ],
    )
    postgres_store.save_snapshot(snapshot2)

    # Should still have only one snapshot
    snapshots = postgres_store.list_snapshots("test_repo")
    assert len(snapshots) == 1

    # Verify updated data
    retrieved = postgres_store.get_snapshot("test_repo", "snapshot:upsert")
    assert retrieved.root_node_id == "node:test:2"
    assert len(retrieved.nodes) == 1
    assert retrieved.nodes[0].name == "updated.py"
    assert retrieved.nodes[0].metrics.loc == 200


@pytest.mark.integration
def test_integration_with_builder(postgres_store):
    """Test PostgresRepoMapStore integration with RepoMapBuilder."""
    # Create test chunks
    chunks = [
        create_test_chunk(
            chunk_id=f"chunk:test:{i}",
            file_path=f"src/file{i}.py",
            fqn=f"module.func{i}",
        )
        for i in range(5)
    ]

    # Build RepoMap with PostgresRepoMapStore
    builder = RepoMapBuilder(store=postgres_store)
    snapshot = builder.build("test_repo", "snapshot:builder", chunks)

    assert snapshot.repo_id == "test_repo"
    assert snapshot.snapshot_id == "snapshot:builder"
    assert len(snapshot.nodes) > 0

    # Verify it was saved to database
    retrieved = postgres_store.get_snapshot("test_repo", "snapshot:builder")
    assert retrieved is not None
    assert len(retrieved.nodes) == len(snapshot.nodes)
