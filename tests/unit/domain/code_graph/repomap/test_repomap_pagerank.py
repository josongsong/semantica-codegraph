"""
Tests for RepoMap PageRank computation.
"""

import pytest

try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

from src.foundation.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from src.repomap import PageRankAggregator, PageRankEngine, RepoMapBuildConfig
from src.repomap.pagerank import GraphAdapter


@pytest.fixture
def sample_graph():
    """Create a sample code graph for testing."""
    # Simple call graph: main → helper1 → helper2
    #                     main → helper2
    nodes = {
        "func:main": GraphNode(
            id="func:main",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="main",
            fqn="main",
            name="main",
        ),
        "func:helper1": GraphNode(
            id="func:helper1",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="main",
            fqn="helper1",
            name="helper1",
        ),
        "func:helper2": GraphNode(
            id="func:helper2",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="main",
            fqn="helper2",
            name="helper2",
        ),
    }

    edges = [
        GraphEdge(
            id="call:main->helper1",
            kind=GraphEdgeKind.CALLS,
            source_id="func:main",
            target_id="func:helper1",
        ),
        GraphEdge(
            id="call:main->helper2",
            kind=GraphEdgeKind.CALLS,
            source_id="func:main",
            target_id="func:helper2",
        ),
        GraphEdge(
            id="call:helper1->helper2",
            kind=GraphEdgeKind.CALLS,
            source_id="func:helper1",
            target_id="func:helper2",
        ),
    ]

    return GraphDocument(
        repo_id="test",
        snapshot_id="main",
        graph_nodes=nodes,
        graph_edges=edges,
    )


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_graph_adapter_build_graph(sample_graph):
    """Test GraphAdapter builds NetworkX graph correctly."""
    adapter = GraphAdapter()
    G = adapter.build_graph(sample_graph)

    # Check nodes
    assert len(G.nodes()) == 3
    assert "func:main" in G
    assert "func:helper1" in G
    assert "func:helper2" in G

    # Check edges
    assert G.has_edge("func:main", "func:helper1")
    assert G.has_edge("func:main", "func:helper2")
    assert G.has_edge("func:helper1", "func:helper2")


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_pagerank_engine_compute(sample_graph):
    """Test PageRank computation."""
    config = RepoMapBuildConfig(pagerank_enabled=True)
    engine = PageRankEngine(config)

    scores = engine.compute_pagerank(sample_graph)

    # Check scores exist for all nodes
    assert "func:main" in scores
    assert "func:helper1" in scores
    assert "func:helper2" in scores

    # helper2 should have highest PageRank (called by 2 nodes)
    assert scores["func:helper2"] > scores["func:main"]
    assert scores["func:helper2"] > scores["func:helper1"]

    # All scores should be in [0, 1] range
    for score in scores.values():
        assert 0.0 <= score <= 1.0


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_graph_adapter_degree_stats(sample_graph):
    """Test degree statistics computation."""
    adapter = GraphAdapter()
    stats = adapter.get_degree_stats(sample_graph)

    # main: out_degree=2, in_degree=0
    assert stats["func:main"]["out_degree"] == 2
    assert stats["func:main"]["in_degree"] == 0

    # helper1: out_degree=1, in_degree=1
    assert stats["func:helper1"]["out_degree"] == 1
    assert stats["func:helper1"]["in_degree"] == 1

    # helper2: out_degree=0, in_degree=2
    assert stats["func:helper2"]["out_degree"] == 0
    assert stats["func:helper2"]["in_degree"] == 2


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_pagerank_aggregator(sample_graph):
    """Test PageRank aggregation to RepoMapNodes."""
    from src.repomap.models import RepoMapMetrics, RepoMapNode

    # Compute PageRank
    config = RepoMapBuildConfig(pagerank_enabled=True)
    engine = PageRankEngine(config)
    scores = engine.compute_pagerank(sample_graph)

    # Create RepoMapNodes referencing GraphNodes
    nodes = [
        RepoMapNode(
            id="repomap:test:main:function:main",
            repo_id="test",
            snapshot_id="main",
            kind="function",
            name="main",
            graph_node_ids=["func:main"],
            metrics=RepoMapMetrics(),
            depth=1,
        ),
        RepoMapNode(
            id="repomap:test:main:function:helper2",
            repo_id="test",
            snapshot_id="main",
            kind="function",
            name="helper2",
            graph_node_ids=["func:helper2"],
            metrics=RepoMapMetrics(),
            depth=1,
        ),
    ]

    # Aggregate
    aggregator = PageRankAggregator()
    aggregator.aggregate(nodes, scores)

    # Check PageRank was aggregated
    assert nodes[0].metrics.pagerank > 0.0
    assert nodes[1].metrics.pagerank > 0.0

    # helper2 should have higher PageRank
    assert nodes[1].metrics.pagerank > nodes[0].metrics.pagerank


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_pagerank_with_no_edges():
    """Test PageRank with isolated nodes."""
    nodes = {
        "func:isolated": GraphNode(
            id="func:isolated",
            kind=GraphNodeKind.FUNCTION,
            repo_id="test",
            snapshot_id="main",
            fqn="isolated",
            name="isolated",
        ),
    }

    graph_doc = GraphDocument(
        repo_id="test",
        snapshot_id="main",
        graph_nodes=nodes,
        graph_edges=[],
    )

    config = RepoMapBuildConfig(pagerank_enabled=True)
    engine = PageRankEngine(config)
    scores = engine.compute_pagerank(graph_doc)

    # Isolated node should get default score
    assert "func:isolated" in scores
    assert scores["func:isolated"] > 0.0  # PageRank gives some score even to isolated nodes


@pytest.mark.skipif(not NETWORKX_AVAILABLE, reason="NetworkX not installed")
def test_pagerank_top_nodes(sample_graph):
    """Test getting top nodes by PageRank."""
    config = RepoMapBuildConfig(pagerank_enabled=True)
    engine = PageRankEngine(config)

    top_nodes = engine.get_top_nodes(sample_graph, top_n=2)

    # Should return 2 nodes
    assert len(top_nodes) == 2

    # Should be sorted by score descending
    assert top_nodes[0][1] >= top_nodes[1][1]

    # Top node should be helper2 (most called)
    assert top_nodes[0][0] == "func:helper2"
