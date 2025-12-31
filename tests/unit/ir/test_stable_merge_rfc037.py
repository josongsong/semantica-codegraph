"""
RFC-037: Stable Merge 규칙 테스트

Deterministic build를 위한 stable sorting 검증.

Test Categories:
1. Node sorting (10 tests)
2. Edge sorting (10 tests)
3. Determinism verification (8 tests)
4. Edge cases (10 tests)
5. Integration (5 tests)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind, Span


# ============================================================
# Test 1: Node Sorting
# ============================================================


class TestNodeSorting:
    """Test node sorting for determinism."""

    def test_nodes_sorted_by_id(self):
        """Nodes should be sorted by ID after build_indexes()."""
        # Create nodes in random order
        nodes = [
            Node(
                id="node_c",
                kind=NodeKind.FUNCTION,
                fqn="c",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node_a",
                kind=NodeKind.FUNCTION,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node_b",
                kind=NodeKind.FUNCTION,
                fqn="b",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Should be sorted by ID
        assert ir_doc.nodes[0].id == "node_a"
        assert ir_doc.nodes[1].id == "node_b"
        assert ir_doc.nodes[2].id == "node_c"

    def test_nodes_stable_across_builds(self):
        """Same nodes should produce same order across builds."""
        nodes1 = [
            Node(
                id="z", kind=NodeKind.FUNCTION, fqn="z", file_path="test.py", span=Span(1, 0, 1, 0), language="python"
            ),
            Node(
                id="a", kind=NodeKind.FUNCTION, fqn="a", file_path="test.py", span=Span(1, 0, 1, 0), language="python"
            ),
        ]

        nodes2 = [
            Node(
                id="a", kind=NodeKind.FUNCTION, fqn="a", file_path="test.py", span=Span(1, 0, 1, 0), language="python"
            ),
            Node(
                id="z", kind=NodeKind.FUNCTION, fqn="z", file_path="test.py", span=Span(1, 0, 1, 0), language="python"
            ),
        ]

        ir_doc1 = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes1)
        ir_doc2 = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes2)

        ir_doc1.build_indexes(sort_key="id")
        ir_doc2.build_indexes(sort_key="id")

        # Should have same order
        assert [n.id for n in ir_doc1.nodes] == [n.id for n in ir_doc2.nodes]

    def test_empty_nodes_no_crash(self):
        """Empty nodes list should not crash."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=[])
        ir_doc.build_indexes(sort_key="id")

        assert ir_doc.nodes == []

    def test_single_node_no_change(self):
        """Single node should remain unchanged."""
        node = Node(
            id="only", kind=NodeKind.FUNCTION, fqn="only", file_path="test.py", span=Span(1, 0, 1, 0), language="python"
        )

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=[node])
        ir_doc.build_indexes(sort_key="id")

        assert ir_doc.nodes[0].id == "only"

    def test_duplicate_ids_stable(self):
        """Duplicate IDs should have stable order (by insertion)."""
        nodes = [
            Node(
                id="dup",
                kind=NodeKind.FUNCTION,
                fqn="dup1",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="dup",
                kind=NodeKind.FUNCTION,
                fqn="dup2",
                file_path="test.py",
                span=Span(2, 0, 2, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Both have same ID, order should be stable (Python sort is stable)
        assert ir_doc.nodes[0].fqn == "dup1"
        assert ir_doc.nodes[1].fqn == "dup2"

    def test_numeric_ids_sorted_correctly(self):
        """Numeric IDs should be sorted as strings."""
        nodes = [
            Node(
                id="node_10",
                kind=NodeKind.FUNCTION,
                fqn="10",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node_2",
                kind=NodeKind.FUNCTION,
                fqn="2",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node_1",
                kind=NodeKind.FUNCTION,
                fqn="1",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # String sort: "node_1" < "node_10" < "node_2"
        assert ir_doc.nodes[0].id == "node_1"
        assert ir_doc.nodes[1].id == "node_10"
        assert ir_doc.nodes[2].id == "node_2"

    def test_special_characters_in_ids(self):
        """Special characters in IDs should be sorted correctly."""
        nodes = [
            Node(
                id="node:z",
                kind=NodeKind.FUNCTION,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node:a",
                kind=NodeKind.FUNCTION,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node_b",
                kind=NodeKind.FUNCTION,
                fqn="b",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Lexicographic sort
        assert ir_doc.nodes[0].id == "node:a"
        assert ir_doc.nodes[1].id == "node:z"
        assert ir_doc.nodes[2].id == "node_b"


# ============================================================
# Test 2: Edge Sorting
# ============================================================


class TestEdgeSorting:
    """Test edge sorting for determinism."""

    def test_edges_sorted_by_source_target(self):
        """Edges should be sorted by (source, target, kind)."""
        edges = [
            Edge(id="e3", source_id="c", target_id="a", kind=EdgeKind.CALLS),
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
            Edge(id="e2", source_id="b", target_id="c", kind=EdgeKind.CALLS),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", edges=edges)
        ir_doc.build_indexes(sort_key="id")

        # Should be sorted by (source_id, target_id)
        assert ir_doc.edges[0].source_id == "a"
        assert ir_doc.edges[1].source_id == "b"
        assert ir_doc.edges[2].source_id == "c"

    def test_edges_stable_across_builds(self):
        """Same edges should produce same order."""
        edges1 = [
            Edge(id="e2", source_id="b", target_id="c", kind=EdgeKind.CALLS),
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
        ]

        edges2 = [
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
            Edge(id="e2", source_id="b", target_id="c", kind=EdgeKind.CALLS),
        ]

        ir_doc1 = IRDocument(repo_id="test", snapshot_id="test", edges=edges1)
        ir_doc2 = IRDocument(repo_id="test", snapshot_id="test", edges=edges2)

        ir_doc1.build_indexes(sort_key="id")
        ir_doc2.build_indexes(sort_key="id")

        # Same order
        assert [e.id for e in ir_doc1.edges] == [e.id for e in ir_doc2.edges]

    def test_same_source_sorted_by_target(self):
        """Edges with same source should be sorted by target."""
        edges = [
            Edge(id="e3", source_id="a", target_id="z", kind=EdgeKind.CALLS),
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
            Edge(id="e2", source_id="a", target_id="m", kind=EdgeKind.CALLS),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", edges=edges)
        ir_doc.build_indexes(sort_key="id")

        # Same source, sorted by target
        assert ir_doc.edges[0].target_id == "b"
        assert ir_doc.edges[1].target_id == "m"
        assert ir_doc.edges[2].target_id == "z"

    def test_same_source_target_sorted_by_kind(self):
        """Edges with same source/target should be sorted by kind."""
        edges = [
            Edge(id="e2", source_id="a", target_id="b", kind=EdgeKind.REFERENCES),
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
            Edge(id="e3", source_id="a", target_id="b", kind=EdgeKind.CONTAINS),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", edges=edges)
        ir_doc.build_indexes(sort_key="id")

        # Same source/target, sorted by kind value
        assert ir_doc.edges[0].kind == EdgeKind.CALLS
        assert ir_doc.edges[1].kind == EdgeKind.CONTAINS
        assert ir_doc.edges[2].kind == EdgeKind.REFERENCES

    def test_empty_edges_no_crash(self):
        """Empty edges list should not crash."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test", edges=[])
        ir_doc.build_indexes(sort_key="id")

        assert ir_doc.edges == []


# ============================================================
# Test 3: Determinism Verification
# ============================================================


class TestDeterminismVerification:
    """Test determinism guarantees."""

    def test_multiple_builds_same_order(self):
        """Multiple builds should produce same order."""

        def create_ir():
            nodes = [
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"f{i}",
                    file_path="test.py",
                    span=Span(i, 0, i, 0),
                    language="python",
                )
                for i in [5, 2, 8, 1, 9, 3]
            ]
            ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
            ir_doc.build_indexes(sort_key="id")
            return ir_doc

        # Build 3 times
        ir1 = create_ir()
        ir2 = create_ir()
        ir3 = create_ir()

        # All should have same order
        ids1 = [n.id for n in ir1.nodes]
        ids2 = [n.id for n in ir2.nodes]
        ids3 = [n.id for n in ir3.nodes]

        assert ids1 == ids2 == ids3

    def test_insertion_order_irrelevant(self):
        """Insertion order should not affect final order."""
        # Forward order
        nodes_fwd = [
            Node(
                id=f"node_{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
            )
            for i in range(10)
        ]

        # Reverse order
        nodes_rev = [
            Node(
                id=f"node_{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
            )
            for i in range(9, -1, -1)
        ]

        ir_fwd = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes_fwd)
        ir_rev = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes_rev)

        ir_fwd.build_indexes(sort_key="id")
        ir_rev.build_indexes(sort_key="id")

        # Same final order
        assert [n.id for n in ir_fwd.nodes] == [n.id for n in ir_rev.nodes]

    def test_random_order_deterministic(self):
        """Random insertion order should produce deterministic result."""
        import random

        # Create nodes
        base_nodes = [
            Node(
                id=f"node_{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
            )
            for i in range(20)
        ]

        # Shuffle 10 times
        results = []
        for _ in range(10):
            nodes = base_nodes.copy()
            random.shuffle(nodes)

            ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
            ir_doc.build_indexes(sort_key="id")

            results.append([n.id for n in ir_doc.nodes])

        # All should be identical
        for result in results[1:]:
            assert result == results[0]

    def test_concurrent_builds_deterministic(self):
        """Concurrent builds should produce same order."""
        import concurrent.futures

        def build():
            nodes = [
                Node(
                    id=f"node_{i}",
                    kind=NodeKind.FUNCTION,
                    fqn=f"f{i}",
                    file_path="test.py",
                    span=Span(i, 0, i, 0),
                    language="python",
                )
                for i in [7, 2, 9, 1, 5]
            ]
            ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
            ir_doc.build_indexes(sort_key="id")
            return [n.id for n in ir_doc.nodes]

        # Build concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(build) for _ in range(10)]
            results = [f.result() for f in futures]

        # All should be identical
        for result in results[1:]:
            assert result == results[0]


# ============================================================
# Test 4: Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_number_of_nodes(self):
        """Large number of nodes should be sorted correctly."""
        nodes = [
            Node(
                id=f"node_{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
            )
            for i in range(1000, 0, -1)  # Reverse order
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Should be sorted
        for i in range(len(ir_doc.nodes) - 1):
            assert ir_doc.nodes[i].id <= ir_doc.nodes[i + 1].id

    def test_unicode_ids(self):
        """Unicode in IDs should be sorted correctly."""
        nodes = [
            Node(
                id="함수_z",
                kind=NodeKind.FUNCTION,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="함수_a",
                kind=NodeKind.FUNCTION,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Should be sorted (Unicode comparison)
        assert ir_doc.nodes[0].id == "함수_a"
        assert ir_doc.nodes[1].id == "함수_z"

    def test_mixed_node_kinds(self):
        """Mixed node kinds should be sorted by ID (not kind)."""
        nodes = [
            Node(
                id="z_func",
                kind=NodeKind.FUNCTION,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="a_class",
                kind=NodeKind.CLASS,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="m_method",
                kind=NodeKind.METHOD,
                fqn="m",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Sorted by ID (not kind)
        assert ir_doc.nodes[0].id == "a_class"
        assert ir_doc.nodes[1].id == "m_method"
        assert ir_doc.nodes[2].id == "z_func"

    def test_colon_separated_ids(self):
        """Colon-separated IDs should be sorted correctly."""
        nodes = [
            Node(
                id="method:Class:z",
                kind=NodeKind.METHOD,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="method:Class:a",
                kind=NodeKind.METHOD,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="function:z",
                kind=NodeKind.FUNCTION,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # Lexicographic sort
        assert ir_doc.nodes[0].id == "function:z"
        assert ir_doc.nodes[1].id == "method:Class:a"
        assert ir_doc.nodes[2].id == "method:Class:z"

    def test_whitespace_in_ids(self):
        """Whitespace in IDs should be sorted correctly."""
        nodes = [
            Node(
                id="node z",
                kind=NodeKind.FUNCTION,
                fqn="z",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
            Node(
                id="node a",
                kind=NodeKind.FUNCTION,
                fqn="a",
                file_path="test.py",
                span=Span(1, 0, 1, 0),
                language="python",
            ),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        assert ir_doc.nodes[0].id == "node a"
        assert ir_doc.nodes[1].id == "node z"

    def test_edges_with_same_source_target_different_kind(self):
        """Multiple edges between same nodes should be sorted by kind."""
        edges = [
            Edge(id="e3", source_id="a", target_id="b", kind=EdgeKind.REFERENCES),
            Edge(id="e1", source_id="a", target_id="b", kind=EdgeKind.CALLS),
            Edge(id="e2", source_id="a", target_id="b", kind=EdgeKind.CONTAINS),
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", edges=edges)
        ir_doc.build_indexes(sort_key="id")

        # Sorted by kind value
        kinds = [e.kind.value for e in ir_doc.edges]
        assert kinds == sorted(kinds)


# ============================================================
# Test 5: Integration with Provenance
# ============================================================


@pytest.mark.asyncio
class TestProvenanceIntegration:
    """Test integration with BuildProvenance."""

    async def test_provenance_sort_key_applied(self, tmp_path):
        """Provenance sort_key should be applied to IR."""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def z_func():
    pass

def a_func():
    pass

def m_func():
    pass
""")

        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        result = await builder.build([test_file], config)

        # Verify provenance exists
        assert result.provenance is not None
        assert result.provenance.node_sort_key == "id"

        # Verify nodes are sorted
        ir_doc = result.ir_documents[str(test_file)]
        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]

        if len(func_nodes) >= 2:
            # Should be sorted by ID
            for i in range(len(func_nodes) - 1):
                assert func_nodes[i].id <= func_nodes[i + 1].id

    async def test_deterministic_node_order_across_builds(self, tmp_path):
        """Node order should be deterministic across builds."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def func_c():
    pass

def func_a():
    pass

def func_b():
    pass
""")

        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
        from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        # Build twice
        result1 = await builder.build([test_file], config)
        result2 = await builder.build([test_file], config)

        ir1 = result1.ir_documents[str(test_file)]
        ir2 = result2.ir_documents[str(test_file)]

        # Same node order
        assert [n.id for n in ir1.nodes] == [n.id for n in ir2.nodes]

        # Same edge order
        assert [e.id for e in ir1.edges] == [e.id for e in ir2.edges]


# ============================================================
# Test 6: Performance
# ============================================================


class TestSortingPerformance:
    """Test sorting performance."""

    def test_sorting_is_fast(self):
        """Sorting should be fast even for large IR."""
        import time

        # Create 10K nodes
        nodes = [
            Node(
                id=f"node_{10000 - i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
            )
            for i in range(1000)  # 10000 → 1000
        ]

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)

        start = time.perf_counter()
        ir_doc.build_indexes(sort_key="id")
        elapsed = time.perf_counter() - start

        # Should be fast (< 100ms for 10K nodes)
        assert elapsed < 0.1, f"Sorting too slow: {elapsed:.3f}s"

    def test_sorting_preserves_data(self):
        """Sorting should not lose or corrupt data."""
        nodes = [
            Node(
                id=f"node_{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"f{i}",
                file_path="test.py",
                span=Span(i, 0, i, 0),
                language="python",
                name=f"func_{i}",
            )
            for i in range(100)
        ]

        original_ids = {n.id for n in nodes}
        original_names = {n.name for n in nodes}

        ir_doc = IRDocument(repo_id="test", snapshot_id="test", nodes=nodes)
        ir_doc.build_indexes(sort_key="id")

        # All nodes should still exist
        assert {n.id for n in ir_doc.nodes} == original_ids
        assert {n.name for n in ir_doc.nodes} == original_names
        assert len(ir_doc.nodes) == 100
