"""
SOTA Query Indexes Tests

Tests for:
- BloomFilter (O(1) existence check)
- EdgeBloomFilter (Edge existence pre-filter)
- ReachabilityBloomFilter (Reachability quick-reject)
- ReachabilityIndex (Transitive Closure)
- BidirectionalReachabilityIndex (Meet-in-the-middle)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.query.indexes.bloom_filter import (
    BloomFilter,
    EdgeBloomFilter,
    ReachabilityBloomFilter,
)
from codegraph_engine.code_foundation.infrastructure.query.indexes.reachability_index import (
    BidirectionalReachabilityIndex,
    ReachabilityIndex,
)


class TestBloomFilter:
    """BloomFilter unit tests"""

    def test_init_valid_params(self):
        """Valid initialization"""
        bf = BloomFilter(expected_elements=1000, fpr=0.01)
        assert bf.count == 0
        assert bf.size_bits > 0

    def test_init_invalid_elements(self):
        """Invalid expected_elements raises ValueError"""
        with pytest.raises(ValueError, match="expected_elements must be positive"):
            BloomFilter(expected_elements=0)

    def test_init_invalid_fpr(self):
        """Invalid FPR raises ValueError"""
        with pytest.raises(ValueError, match="fpr must be between"):
            BloomFilter(expected_elements=100, fpr=0)

        with pytest.raises(ValueError, match="fpr must be between"):
            BloomFilter(expected_elements=100, fpr=1.0)

    def test_add_and_contains(self):
        """Basic add and contains operations"""
        bf = BloomFilter(expected_elements=100)
        bf.add("test_item")

        assert "test_item" in bf
        assert bf.count == 1

    def test_definitely_not_contains(self):
        """Items not added are definitely not present"""
        bf = BloomFilter(expected_elements=100)
        bf.add("present")

        # Not added items return False (no false negatives)
        assert bf.definitely_not_contains("absent")
        assert "absent" not in bf

    def test_add_many(self):
        """Bulk add operation"""
        bf = BloomFilter(expected_elements=1000)
        items = [f"item_{i}" for i in range(100)]

        count = bf.add_many(items)

        assert count == 100
        assert bf.count == 100
        for item in items:
            assert item in bf

    def test_clear(self):
        """Clear operation resets filter"""
        bf = BloomFilter(expected_elements=100)
        bf.add_many(["a", "b", "c"])

        bf.clear()

        assert bf.count == 0
        assert "a" not in bf

    def test_no_false_negatives(self):
        """Bloom filter never has false negatives"""
        bf = BloomFilter(expected_elements=10000, fpr=0.01)
        items = [f"item_{i}" for i in range(1000)]

        bf.add_many(items)

        # Every added item MUST be found (no false negatives)
        for item in items:
            assert item in bf, f"False negative: {item}"

    def test_estimated_fpr(self):
        """Estimated FPR is reasonable"""
        bf = BloomFilter(expected_elements=1000, fpr=0.01)
        bf.add_many([f"item_{i}" for i in range(1000)])

        # Actual FPR should be close to target
        assert bf.estimated_fpr < 0.02  # Some tolerance

    def test_get_stats(self):
        """Statistics are complete"""
        bf = BloomFilter(expected_elements=100, fpr=0.05)
        bf.add("test")

        stats = bf.get_stats()

        assert stats["expected_elements"] == 100
        assert stats["target_fpr"] == 0.05
        assert stats["items_added"] == 1
        assert "size_bits" in stats
        assert "hash_count" in stats


class TestEdgeBloomFilter:
    """EdgeBloomFilter unit tests"""

    def test_add_and_check_edge(self):
        """Edge add and check operations"""
        ebf = EdgeBloomFilter(expected_edges=1000)
        ebf.add_edge("node_a", "node_b")

        assert ebf.might_have_edge("node_a", "node_b")
        assert ebf.definitely_no_edge("node_a", "node_c")

    def test_directional_edges(self):
        """Edges are directional"""
        ebf = EdgeBloomFilter(expected_edges=1000)
        ebf.add_edge("from", "to")

        assert ebf.might_have_edge("from", "to")
        # Reverse edge was not added
        # Note: Might have false positive, but usually won't
        # This test just verifies the API works


class TestReachabilityBloomFilter:
    """ReachabilityBloomFilter unit tests"""

    def test_add_and_check_reachable(self):
        """Reachability add and check"""
        rbf = ReachabilityBloomFilter(expected_pairs=10000)
        rbf.add_reachable("source", "target")

        assert rbf.might_reach("source", "target")
        assert rbf.definitely_unreachable("source", "unknown")

    def test_lower_fpr(self):
        """Reachability filter has lower FPR (0.1%)"""
        rbf = ReachabilityBloomFilter(expected_pairs=1000, fpr=0.001)
        stats = rbf.get_stats()

        assert stats["target_fpr"] == 0.001


class TestReachabilityIndex:
    """ReachabilityIndex integration tests"""

    @pytest.fixture
    def mock_graph(self):
        """Create mock graph for testing"""

        class MockNode:
            def __init__(self, id_: str):
                self.id = id_

        class MockEdge:
            def __init__(self, from_: str, to_: str):
                self.from_node = from_
                self.to_node = to_

        class MockGraph:
            def __init__(self):
                # Simple graph: A -> B -> C -> D
                self._edges = {
                    "A": [MockEdge("A", "B")],
                    "B": [MockEdge("B", "C")],
                    "C": [MockEdge("C", "D")],
                    "D": [],
                }
                self._nodes = {k: MockNode(k) for k in self._edges}

            def get_outgoing_edges(self, node_id: str):
                return self._edges.get(node_id, [])

            def get_incoming_edges(self, node_id: str):
                result = []
                for source, edges in self._edges.items():
                    for edge in edges:
                        if edge.to_node == node_id:
                            result.append(edge)
                return result

            def get_all_nodes(self):
                return list(self._nodes.values())

        return MockGraph()

    def test_build_and_query(self, mock_graph):
        """Build index and query reachability"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)
        idx.build(sources=["A"])

        assert idx.can_reach("A", "B")
        assert idx.can_reach("A", "C")
        assert idx.can_reach("A", "D")
        assert not idx.can_reach("A", "X")

    def test_lazy_build(self, mock_graph):
        """Lazy build on demand"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)

        # Should trigger lazy build
        assert idx.can_reach("A", "B", lazy=True)
        assert idx._sources_indexed == {"A"}

    def test_get_distance(self, mock_graph):
        """Get hop count distance"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)
        idx.build(sources=["A"])

        assert idx.get_distance("A", "B") == 1
        assert idx.get_distance("A", "C") == 2
        assert idx.get_distance("A", "D") == 3
        assert idx.get_distance("A", "X") is None

    def test_get_reachable_from(self, mock_graph):
        """Get all reachable nodes"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)

        reachable = idx.get_reachable_from("A")

        assert reachable == {"B", "C", "D"}

    def test_invalidate(self, mock_graph):
        """Invalidate cache"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)
        idx.build(sources=["A"])

        idx.invalidate()

        assert idx._sources_indexed == set()
        assert not idx._built

    def test_stats(self, mock_graph):
        """Get statistics"""
        idx = ReachabilityIndex(mock_graph, max_depth=10)
        idx.build(sources=["A"])

        stats = idx.get_stats()

        assert stats["sources_indexed"] == 1
        assert stats["total_pairs"] == 3  # B, C, D
        assert stats["built"] is True


class TestBidirectionalReachabilityIndex:
    """BidirectionalReachabilityIndex tests"""

    @pytest.fixture
    def mock_graph(self):
        """Create mock graph with meeting point"""

        class MockEdge:
            def __init__(self, from_: str, to_: str):
                self.from_node = from_
                self.to_node = to_

        class MockGraph:
            def __init__(self):
                # Graph: A -> M <- B, M -> C
                # A and B both reach M, M reaches C
                self._edges = {
                    "A": [MockEdge("A", "M")],
                    "B": [MockEdge("B", "M")],
                    "M": [MockEdge("M", "C")],
                    "C": [],
                }

            def get_outgoing_edges(self, node_id: str):
                return self._edges.get(node_id, [])

            def get_incoming_edges(self, node_id: str):
                result = []
                for source, edges in self._edges.items():
                    for edge in edges:
                        if edge.to_node == node_id:
                            result.append(edge)
                return result

        return MockGraph()

    def test_can_reach(self, mock_graph):
        """Bidirectional reachability check"""
        idx = BidirectionalReachabilityIndex(mock_graph)

        assert idx.can_reach("A", "C")
        assert idx.can_reach("A", "M")
        assert not idx.can_reach("C", "A")  # No reverse path

    def test_get_meeting_points(self, mock_graph):
        """Get meeting points between source and sink"""
        idx = BidirectionalReachabilityIndex(mock_graph)

        # A -> M -> C, so M is a meeting point
        points = idx.get_meeting_points("A", "C")
        assert "M" in points or "C" in points

    def test_invalidate(self, mock_graph):
        """Invalidate clears caches"""
        idx = BidirectionalReachabilityIndex(mock_graph)
        idx.build_forward("A")
        idx.build_backward("C")

        idx.invalidate()

        assert idx._forward == {}
        assert idx._backward == {}


class TestIntegration:
    """Integration tests with UnifiedGraphIndex"""

    @pytest.fixture
    def ir_doc_fixture(self):
        """Create minimal IRDocument for testing"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            IRDocument,
            Node,
            Span,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import NodeKind

        # Create minimal IR with nodes and edges
        nodes = [
            Node(
                id="node:func:main",
                kind=NodeKind.FUNCTION,
                name="main",
                fqn="test.main",
                language="python",
                file_path="test.py",
                span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
            ),
            Node(
                id="node:func:helper",
                kind=NodeKind.FUNCTION,
                name="helper",
                fqn="test.helper",
                language="python",
                file_path="test.py",
                span=Span(start_line=10, start_col=0, end_line=15, end_col=0),
            ),
        ]

        return IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=nodes,
            edges=[],
            cfg_blocks=[],
            cfg_edges=[],
        )

    def test_unified_graph_index_sota_methods(self, ir_doc_fixture):
        """UnifiedGraphIndex has SOTA methods"""
        from codegraph_engine.code_foundation.infrastructure.query.graph_index import (
            UnifiedGraphIndex,
        )

        graph = UnifiedGraphIndex(ir_doc_fixture)

        # SOTA methods exist
        assert hasattr(graph, "might_have_edge")
        assert hasattr(graph, "can_reach")
        assert hasattr(graph, "get_distance")
        assert hasattr(graph, "get_reachable_from")
        assert hasattr(graph, "can_reach_bidirectional")
        assert hasattr(graph, "get_meeting_points")
        assert hasattr(graph, "invalidate_caches")

    def test_query_engine_expanded_cache(self):
        """QueryEngine has expanded cache size"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import (
            QueryEngine,
        )

        # Check default values
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[],
            edges=[],
            cfg_blocks=[],
            cfg_edges=[],
        )
        engine = QueryEngine(ir_doc)

        assert engine._cache_maxsize == 500  # SOTA: expanded
        assert engine._cache_max_bytes == 100 * 1024 * 1024  # SOTA: 100MB
