"""
Tests for RepoMap models and ID generation.
"""


from src.repomap.id_strategy import RepoMapIdContext, RepoMapIdGenerator
from src.repomap.models import RepoMapMetrics, RepoMapNode, RepoMapSnapshot


def test_repomap_metrics_creation():
    """Test RepoMapMetrics model creation."""
    metrics = RepoMapMetrics(
        loc=100,
        symbol_count=5,
        edge_degree=10,
        pagerank=0.5,
        importance=0.8,
    )

    assert metrics.loc == 100
    assert metrics.symbol_count == 5
    assert metrics.edge_degree == 10
    assert metrics.pagerank == 0.5
    assert metrics.importance == 0.8


def test_repomap_node_creation():
    """Test RepoMapNode model creation."""
    node = RepoMapNode(
        id="repomap:myrepo:main:file:src/main.py",
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        name="main.py",
        path="src/main.py",
        depth=2,
    )

    assert node.id == "repomap:myrepo:main:file:src/main.py"
    assert node.kind == "file"
    assert node.name == "main.py"
    assert node.depth == 2
    assert node.metrics.loc == 0  # Default


def test_repomap_snapshot_creation():
    """Test RepoMapSnapshot model creation."""
    root_node = RepoMapNode(
        id="repomap:myrepo:main:repo:root",
        repo_id="myrepo",
        snapshot_id="main",
        kind="repo",
        name="myrepo",
        depth=0,
    )

    snapshot = RepoMapSnapshot(
        repo_id="myrepo",
        snapshot_id="main",
        root_node_id=root_node.id,
        nodes=[root_node],
    )

    assert snapshot.repo_id == "myrepo"
    assert snapshot.snapshot_id == "main"
    assert len(snapshot.nodes) == 1


def test_repomap_snapshot_get_node():
    """Test RepoMapSnapshot.get_node()."""
    node1 = RepoMapNode(
        id="node1",
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        name="file1.py",
        depth=1,
    )
    node2 = RepoMapNode(
        id="node2",
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        name="file2.py",
        depth=1,
    )

    snapshot = RepoMapSnapshot(
        repo_id="myrepo",
        snapshot_id="main",
        root_node_id="node1",
        nodes=[node1, node2],
    )

    assert snapshot.get_node("node1") == node1
    assert snapshot.get_node("node2") == node2
    assert snapshot.get_node("node3") is None


def test_repomap_snapshot_get_children():
    """Test RepoMapSnapshot.get_children()."""
    parent = RepoMapNode(
        id="parent",
        repo_id="myrepo",
        snapshot_id="main",
        kind="dir",
        name="src",
        children_ids=["child1", "child2"],
        depth=1,
    )
    child1 = RepoMapNode(
        id="child1",
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        name="file1.py",
        parent_id="parent",
        depth=2,
    )
    child2 = RepoMapNode(
        id="child2",
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        name="file2.py",
        parent_id="parent",
        depth=2,
    )

    snapshot = RepoMapSnapshot(
        repo_id="myrepo",
        snapshot_id="main",
        root_node_id="parent",
        nodes=[parent, child1, child2],
    )

    children = snapshot.get_children("parent")
    assert len(children) == 2
    assert child1 in children
    assert child2 in children


def test_repomap_id_generator_basic():
    """Test basic RepoMap ID generation."""
    ctx = RepoMapIdContext(
        repo_id="myrepo",
        snapshot_id="main",
        kind="file",
        identifier="src/main.py",
    )

    node_id = RepoMapIdGenerator.generate(ctx)
    assert node_id == "repomap:myrepo:main:file:src.main.py"


def test_repomap_id_generator_repo_root():
    """Test repo root ID generation."""
    root_id = RepoMapIdGenerator.generate_repo_root("myrepo", "main")
    assert root_id == "repomap:myrepo:main:repo:root"


def test_repomap_id_generator_dir():
    """Test directory ID generation."""
    dir_id = RepoMapIdGenerator.generate_dir("myrepo", "main", "src/indexing")
    assert dir_id == "repomap:myrepo:main:dir:src.indexing"


def test_repomap_id_generator_file():
    """Test file ID generation."""
    file_id = RepoMapIdGenerator.generate_file("myrepo", "main", "src/main.py")
    assert file_id == "repomap:myrepo:main:file:src.main.py"


def test_repomap_id_generator_symbol():
    """Test symbol ID generation."""
    symbol_id = RepoMapIdGenerator.generate_symbol("myrepo", "main", "src.main.run", "function")
    assert symbol_id == "repomap:myrepo:main:function:src.main.run"


def test_repomap_id_generator_long_identifier():
    """Test ID generation with very long identifier."""
    long_id = "a" * 250
    ctx = RepoMapIdContext(
        repo_id="myrepo",
        snapshot_id="main",
        kind="function",
        identifier=long_id,
    )

    node_id = RepoMapIdGenerator.generate(ctx)
    # Should be truncated with hash suffix
    assert len(node_id) < 250
    assert "..." in node_id
