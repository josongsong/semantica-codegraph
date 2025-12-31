"""
PageRank Engine Edge Case / Extreme Tests

Tests for rustworkx-based PageRank computation covering:
1. Empty graphs
2. Single node graphs
3. Disconnected graphs
4. Self-loops
5. Very large graphs
6. Graphs with no edges
7. Dangling nodes (no outgoing edges)
8. Cyclic graphs
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphIndex,
    GraphNode,
    GraphNodeKind,
)
from codegraph_engine.repo_structure.infrastructure.models import RepoMapBuildConfig
from codegraph_engine.repo_structure.infrastructure.pagerank.engine import PageRankEngine
from codegraph_engine.repo_structure.infrastructure.pagerank.incremental import IncrementalPageRankEngine


@pytest.fixture
def config():
    """Default PageRank config."""
    return RepoMapBuildConfig(
        pagerank_enabled=True,
        pagerank_damping=0.85,
        pagerank_max_iterations=100,
    )


@pytest.fixture
def engine(config):
    """Create PageRank engine."""
    return PageRankEngine(config)


@pytest.fixture
def incremental_engine(config):
    """Create Incremental PageRank engine."""
    return IncrementalPageRankEngine(config)


def make_node(node_id: str, kind: GraphNodeKind = GraphNodeKind.FUNCTION) -> GraphNode:
    """Helper to create a graph node."""
    return GraphNode(
        id=node_id,
        kind=kind,
        repo_id="test",
        snapshot_id="snap1",
        fqn=node_id,
        name=node_id,
        path="test.py",
    )


def make_edge(source_id: str, target_id: str, kind: GraphEdgeKind = GraphEdgeKind.CALLS) -> GraphEdge:
    """Helper to create a graph edge."""
    return GraphEdge(
        id=f"{source_id}->{target_id}",
        kind=kind,
        source_id=source_id,
        target_id=target_id,
    )


def make_graph_doc(nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphDocument:
    """Helper to create a GraphDocument."""
    return GraphDocument(
        repo_id="test",
        snapshot_id="snap1",
        graph_nodes={n.id: n for n in nodes},
        graph_edges=edges,
        edge_by_id={e.id: e for e in edges},
        indexes=GraphIndex(),
    )


class TestPageRankEmptyGraph:
    """Empty graph edge cases."""

    def test_empty_graph_returns_empty_dict(self, engine):
        """Empty graph should return empty scores."""
        graph = make_graph_doc([], [])
        scores = engine.compute_pagerank(graph)
        assert scores == {}

    def test_empty_graph_with_degree(self, engine):
        """Empty graph should return empty degree stats."""
        graph = make_graph_doc([], [])
        result = engine.compute_with_degree(graph)
        assert result == {}

    def test_empty_graph_top_nodes(self, engine):
        """Empty graph should return empty top nodes."""
        graph = make_graph_doc([], [])
        top = engine.get_top_nodes(graph, top_n=10)
        assert top == []


class TestPageRankSingleNode:
    """Single node graph edge cases."""

    def test_single_node_no_edges(self, engine):
        """Single node with no edges should have score 1.0."""
        node = make_node("solo")
        graph = make_graph_doc([node], [])

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 1
        assert scores["solo"] == 1.0

    def test_single_node_self_loop(self, engine):
        """Single node with self-loop should have score 1.0."""
        node = make_node("solo")
        edge = make_edge("solo", "solo")
        graph = make_graph_doc([node], [edge])

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 1
        assert 0.99 <= scores["solo"] <= 1.01


class TestPageRankNoEdges:
    """Graphs with no edges."""

    def test_multiple_nodes_no_edges_uniform(self, engine):
        """Multiple nodes with no edges should have uniform scores."""
        nodes = [make_node(f"node_{i}") for i in range(5)]
        graph = make_graph_doc(nodes, [])

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 5
        expected = 1.0 / 5
        for score in scores.values():
            assert abs(score - expected) < 0.001


class TestPageRankDisconnected:
    """Disconnected graph edge cases."""

    def test_disconnected_components(self, engine):
        """Disconnected components should all have valid scores."""
        # Component 1: A -> B
        nodes = [
            make_node("a"),
            make_node("b"),
            make_node("c"),
            make_node("d"),
        ]
        edges = [
            make_edge("a", "b"),
            make_edge("c", "d"),
        ]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 4
        # All scores should be positive
        assert all(s > 0 for s in scores.values())
        # Sum should be ~1.0
        assert 0.99 <= sum(scores.values()) <= 1.01


class TestPageRankCycles:
    """Cyclic graph edge cases."""

    def test_simple_cycle(self, engine):
        """Simple A -> B -> C -> A cycle."""
        nodes = [make_node("a"), make_node("b"), make_node("c")]
        edges = [
            make_edge("a", "b"),
            make_edge("b", "c"),
            make_edge("c", "a"),
        ]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 3
        # Symmetric cycle should have nearly equal scores
        values = list(scores.values())
        assert max(values) - min(values) < 0.1

    def test_complex_cycle_with_branch(self, engine):
        """Cycle with a branch: A -> B -> C -> A, B -> D."""
        nodes = [make_node("a"), make_node("b"), make_node("c"), make_node("d")]
        edges = [
            make_edge("a", "b"),
            make_edge("b", "c"),
            make_edge("c", "a"),
            make_edge("b", "d"),
        ]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 4
        # D should have lower score (only one incoming edge, no outgoing)
        assert scores["d"] < scores["b"]


class TestPageRankDanglingNodes:
    """Dangling nodes (no outgoing edges)."""

    def test_dangling_node(self, engine):
        """Node with no outgoing edges (sink)."""
        nodes = [make_node("source"), make_node("sink")]
        edges = [make_edge("source", "sink")]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 2
        # Sink should have higher score (receives all flow)
        assert scores["sink"] > scores["source"]

    def test_multiple_dangling_nodes(self, engine):
        """Multiple sinks receiving from single source."""
        nodes = [
            make_node("source"),
            make_node("sink1"),
            make_node("sink2"),
            make_node("sink3"),
        ]
        edges = [
            make_edge("source", "sink1"),
            make_edge("source", "sink2"),
            make_edge("source", "sink3"),
        ]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 4
        # All sinks should have similar scores
        sink_scores = [scores["sink1"], scores["sink2"], scores["sink3"]]
        assert max(sink_scores) - min(sink_scores) < 0.05


class TestPageRankLargeGraph:
    """Large graph performance tests."""

    def test_large_graph_100_nodes(self, engine):
        """100 node linear chain."""
        nodes = [make_node(f"node_{i}") for i in range(100)]
        edges = [make_edge(f"node_{i}", f"node_{i + 1}") for i in range(99)]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 100
        # Last node should have highest score
        assert scores["node_99"] > scores["node_0"]

    def test_large_graph_complete_10(self, engine):
        """Complete graph with 10 nodes (all connected)."""
        n = 10
        nodes = [make_node(f"node_{i}") for i in range(n)]
        edges = [make_edge(f"node_{i}", f"node_{j}") for i in range(n) for j in range(n) if i != j]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == n
        # Complete graph should have nearly uniform scores
        values = list(scores.values())
        assert max(values) - min(values) < 0.05


class TestPageRankNodeKindFiltering:
    """Node kind filtering tests."""

    def test_excludes_cfg_blocks(self, engine):
        """CFG blocks should be excluded from PageRank."""
        nodes = [
            make_node("func", GraphNodeKind.FUNCTION),
            make_node("cfg_block", GraphNodeKind.CFG_BLOCK),
        ]
        edges = [make_edge("func", "cfg_block")]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        # Only function should be in results
        assert len(scores) == 1
        assert "func" in scores
        assert "cfg_block" not in scores

    def test_includes_external_functions(self, engine):
        """External functions should be included."""
        nodes = [
            make_node("func", GraphNodeKind.FUNCTION),
            make_node("ext", GraphNodeKind.EXTERNAL_FUNCTION),
        ]
        edges = [make_edge("func", "ext")]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 2
        assert "func" in scores
        assert "ext" in scores


class TestIncrementalPageRank:
    """Incremental PageRank edge cases."""

    def test_minor_changes_skip_recompute(self, incremental_engine):
        """<10% changes should skip recomputation."""
        nodes = [make_node(f"node_{i}") for i in range(100)]
        edges = [make_edge(f"node_{i}", f"node_{i + 1}") for i in range(99)]
        graph = make_graph_doc(nodes, edges)

        # Previous scores
        previous = {f"node_{i}": 0.01 for i in range(100)}

        # Only 5 affected nodes (5%)
        affected = {f"node_{i}" for i in range(5)}

        scores = incremental_engine.compute_with_changes(graph, affected, previous)

        assert len(scores) == 100
        # Should mostly preserve previous scores
        for i in range(5, 100):
            assert scores[f"node_{i}"] == previous[f"node_{i}"]

    def test_major_changes_full_recompute(self, incremental_engine):
        """>50% changes should trigger full recomputation."""
        nodes = [make_node(f"node_{i}") for i in range(10)]
        edges = [make_edge(f"node_{i}", f"node_{i + 1}") for i in range(9)]
        graph = make_graph_doc(nodes, edges)

        # 60% affected
        affected = {f"node_{i}" for i in range(6)}

        scores = incremental_engine.compute_with_changes(graph, affected, None)

        assert len(scores) == 10
        # Sum should be ~1.0 (full recompute normalizes)
        assert 0.99 <= sum(scores.values()) <= 1.01

    def test_empty_affected_set(self, incremental_engine):
        """Empty affected set with previous scores."""
        nodes = [make_node(f"node_{i}") for i in range(10)]
        edges = []
        graph = make_graph_doc(nodes, edges)

        previous = {f"node_{i}": 0.1 for i in range(10)}

        scores = incremental_engine.compute_with_changes(graph, set(), previous)

        # Should return previous scores
        assert len(scores) == 10
        for k, v in previous.items():
            assert scores[k] == v

    def test_moderate_changes_incremental_recompute(self, incremental_engine):
        """10-50% changes should trigger incremental recomputation."""
        nodes = [make_node(f"node_{i}") for i in range(20)]
        edges = [make_edge(f"node_{i}", f"node_{i + 1}") for i in range(19)]
        graph = make_graph_doc(nodes, edges)

        # Previous scores
        previous = {f"node_{i}": 0.05 for i in range(20)}

        # 25% affected (5 out of 20)
        affected = {f"node_{i}" for i in range(5)}

        scores = incremental_engine.compute_with_changes(graph, affected, previous)

        assert len(scores) == 20
        # All nodes should have valid scores
        assert all(s > 0 for s in scores.values())
        # Sum should be ~1.0 (normalized after merge)
        assert 0.99 <= sum(scores.values()) <= 1.01

    def test_moderate_changes_no_previous_scores(self, incremental_engine):
        """10-50% changes without previous scores should full recompute."""
        nodes = [make_node(f"node_{i}") for i in range(20)]
        edges = [make_edge(f"node_{i}", f"node_{i + 1}") for i in range(19)]
        graph = make_graph_doc(nodes, edges)

        # 25% affected, but NO previous scores
        affected = {f"node_{i}" for i in range(5)}

        scores = incremental_engine.compute_with_changes(graph, affected, None)

        assert len(scores) == 20
        # Full recompute: sum should be ~1.0
        assert 0.99 <= sum(scores.values()) <= 1.01


class TestPageRankEdgeTypeFiltering:
    """Edge type filtering tests."""

    def test_imports_edges_included(self, engine):
        """IMPORTS edges should be included by default."""
        nodes = [
            make_node("a", GraphNodeKind.MODULE),
            make_node("b", GraphNodeKind.MODULE),
        ]
        edges = [make_edge("a", "b", GraphEdgeKind.IMPORTS)]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 2
        # B should have higher score (imported)
        assert scores["b"] > scores["a"]

    def test_inherits_edges_excluded_by_default(self, engine):
        """INHERITS edges should be excluded by default."""
        nodes = [
            make_node("child", GraphNodeKind.CLASS),
            make_node("parent", GraphNodeKind.CLASS),
        ]
        edges = [make_edge("child", "parent", GraphEdgeKind.INHERITS)]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        # No INHERITS edges included → uniform scores
        assert len(scores) == 2
        assert abs(scores["child"] - scores["parent"]) < 0.01

    def test_references_type_edges_excluded(self, engine):
        """REFERENCES_TYPE edges should be excluded by default."""
        nodes = [
            make_node("func", GraphNodeKind.FUNCTION),
            make_node("type", GraphNodeKind.CLASS),
        ]
        edges = [make_edge("func", "type", GraphEdgeKind.REFERENCES_TYPE)]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        # No REFERENCES_TYPE edges → uniform scores
        assert len(scores) == 2
        assert abs(scores["func"] - scores["type"]) < 0.01


class TestPageRankDegreeCentrality:
    """Degree centrality computation tests."""

    def test_compute_with_degree_basic(self, engine):
        """compute_with_degree returns pagerank + degree stats."""
        nodes = [make_node("a"), make_node("b"), make_node("c")]
        edges = [make_edge("a", "b"), make_edge("a", "c")]
        graph = make_graph_doc(nodes, edges)

        results = engine.compute_with_degree(graph)

        assert len(results) == 3
        # Check all keys present
        for node_id in ["a", "b", "c"]:
            assert "pagerank" in results[node_id]
            assert "in_degree_centrality" in results[node_id]
            assert "out_degree_centrality" in results[node_id]
            assert "degree_centrality" in results[node_id]

        # A has out_degree=2, in_degree=0
        assert results["a"]["out_degree_centrality"] > 0
        assert results["a"]["in_degree_centrality"] == 0

        # B and C have in_degree=1, out_degree=0
        assert results["b"]["in_degree_centrality"] > 0
        assert results["b"]["out_degree_centrality"] == 0

    def test_compute_with_degree_no_edges(self, engine):
        """compute_with_degree with no edges returns zero centrality."""
        nodes = [make_node("a"), make_node("b")]
        graph = make_graph_doc(nodes, [])

        results = engine.compute_with_degree(graph)

        assert len(results) == 2
        for node_id in ["a", "b"]:
            assert results[node_id]["in_degree_centrality"] == 0.0
            assert results[node_id]["out_degree_centrality"] == 0.0
            assert results[node_id]["degree_centrality"] == 0.0


class TestPageRankDuplicateEdges:
    """Duplicate edge handling tests."""

    def test_duplicate_edges_handled(self, engine):
        """Duplicate edges should be handled gracefully."""
        nodes = [make_node("a"), make_node("b")]
        # Same edge twice
        edges = [
            GraphEdge(id="e1", kind=GraphEdgeKind.CALLS, source_id="a", target_id="b"),
            GraphEdge(id="e2", kind=GraphEdgeKind.CALLS, source_id="a", target_id="b"),
        ]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 2
        # Should not crash, B should have higher score
        assert scores["b"] > scores["a"]


class TestPageRankStress:
    """Stress tests for large graphs."""

    def test_star_graph_1000_nodes(self, engine):
        """Star graph: 1 center connected to 999 leaves."""
        nodes = [make_node("center")] + [make_node(f"leaf_{i}") for i in range(999)]
        edges = [make_edge("center", f"leaf_{i}") for i in range(999)]
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 1000
        # All leaves should have similar scores
        leaf_scores = [scores[f"leaf_{i}"] for i in range(999)]
        assert max(leaf_scores) - min(leaf_scores) < 0.001

    def test_binary_tree_depth_10(self, engine):
        """Binary tree with depth 10 (1023 nodes)."""
        nodes = [make_node(f"node_{i}") for i in range(1023)]
        edges = []
        for i in range(511):  # Internal nodes
            left_child = 2 * i + 1
            right_child = 2 * i + 2
            if left_child < 1023:
                edges.append(make_edge(f"node_{i}", f"node_{left_child}"))
            if right_child < 1023:
                edges.append(make_edge(f"node_{i}", f"node_{right_child}"))
        graph = make_graph_doc(nodes, edges)

        scores = engine.compute_pagerank(graph)

        assert len(scores) == 1023
        # Root should have lower score (only outgoing edges)
        # Leaves at same depth have equal scores (symmetric tree)
        # All leaf scores should be equal (symmetric)
        leaf_scores = [scores[f"node_{i}"] for i in range(511, 1023)]
        assert max(leaf_scores) - min(leaf_scores) < 0.0001
        # Root has lowest score (no incoming edges)
        assert scores["node_0"] <= min(scores.values()) + 0.0001
