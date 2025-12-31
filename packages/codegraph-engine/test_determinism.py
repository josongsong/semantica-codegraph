"""
RFC-RUST-ENGINE Phase 1: Determinism Tests

Tests for total ordering and deterministic IR generation.

Test Requirements:
1. Same input → same ordering → same hash (10 runs)
2. local_seq is assigned correctly
3. Total ordering is enforced
4. No ties in ordering keys
"""

import hashlib
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class TestDeterministicOrdering:
    """Test deterministic ordering with local_seq tie-breaker"""

    def test_local_seq_assignment(self):
        """Test that local_seq is assigned sequentially to nodes and edges"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add nodes
        for i in range(5):
            node = Node(
                id=f"node:{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"test.func{i}",
                file_path="test.py",
                span=Span(i, 0, i + 1, 0),
                language="python",
            )
            ir_doc.nodes.append(node)

        # Add edges
        for i in range(3):
            edge = Edge(
                id=f"edge:{i}",
                kind=EdgeKind.CALLS,
                source_id=f"node:{i}",
                target_id=f"node:{i + 1}",
            )
            ir_doc.edges.append(edge)

        # Assign local_seq
        ir_doc.assign_local_seq()

        # Verify nodes
        for idx, node in enumerate(ir_doc.nodes):
            assert node.local_seq == idx, f"Node {idx} has wrong local_seq: {node.local_seq}"

        # Verify edges
        for idx, edge in enumerate(ir_doc.edges):
            assert edge.local_seq == idx, f"Edge {idx} has wrong local_seq: {edge.local_seq}"

    def test_total_ordering_sorts_correctly(self):
        """Test that enforce_total_ordering sorts nodes and edges correctly"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add nodes in random order (different files and lines)
        nodes_data = [
            ("file_b.py", NodeKind.CLASS, 30, 40, 2),
            ("file_a.py", NodeKind.FUNCTION, 10, 20, 0),
            ("file_a.py", NodeKind.FUNCTION, 30, 40, 1),
        ]

        for file_path, kind, start, end, local_seq in nodes_data:
            node = Node(
                id=f"node:{local_seq}",
                kind=kind,
                fqn=f"test.item{local_seq}",
                file_path=file_path,
                span=Span(start, 0, end, 0),
                language="python",
                local_seq=local_seq,
            )
            ir_doc.nodes.append(node)

        # Enforce ordering
        ir_doc.enforce_total_ordering()

        # Verify nodes are sorted by (file_path, kind, start_line, end_line, local_seq)
        # Expected order after sorting:
        # 1. file_a.py, FUNCTION, 10-20, local_seq=0
        # 2. file_a.py, FUNCTION, 30-40, local_seq=1
        # 3. file_b.py, CLASS, 30-40, local_seq=2

        assert ir_doc.nodes[0].file_path == "file_a.py"
        assert ir_doc.nodes[0].span.start_line == 10
        assert ir_doc.nodes[0].local_seq == 0

        assert ir_doc.nodes[1].file_path == "file_a.py"
        assert ir_doc.nodes[1].span.start_line == 30
        assert ir_doc.nodes[1].local_seq == 1

        assert ir_doc.nodes[2].file_path == "file_b.py"
        assert ir_doc.nodes[2].local_seq == 2

    def test_no_ordering_ties(self):
        """Test that local_seq prevents ties in ordering"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add nodes with identical primary keys (same file, kind, span)
        for i in range(3):
            node = Node(
                id=f"node:{i}",
                kind=NodeKind.VARIABLE,
                fqn=f"test.var{i}",
                file_path="test.py",
                span=Span(10, i, 10, i + 5),  # Same line, different columns
                language="python",
                local_seq=i,
            )
            ir_doc.nodes.append(node)

        # Enforce ordering
        ir_doc.enforce_total_ordering()

        # Verify no two nodes have same ordering key
        # With local_seq as tie-breaker, all ordering keys should be unique
        ordering_keys = []
        for node in ir_doc.nodes:
            key = (
                node.file_path,
                node.kind.value,
                node.span.start_line,
                node.span.end_line,
                node.local_seq,
            )
            assert key not in ordering_keys, f"Duplicate ordering key: {key}"
            ordering_keys.append(key)

        # Verify sorted by local_seq (since other fields are same)
        for idx, node in enumerate(ir_doc.nodes):
            assert node.local_seq == idx


class TestDeterministicHashing:
    """Test that same input produces same hash"""

    @pytest.mark.asyncio
    async def test_deterministic_ir_generation(self, tmp_path: Path):
        """Test that IR generation is deterministic across multiple runs"""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def foo():
    pass

def bar():
    x = 1
    return x

class Baz:
    def method(self):
        return 42
""")

        # Build IR multiple times
        hashes = []
        for run in range(3):
            builder = LayeredIRBuilder(project_root=tmp_path)

            # Build with minimal config (structural IR only)
            from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig

            config = BuildConfig(
                occurrences=False,
                lsp_enrichment=False,
                cross_file=False,
                retrieval_index=False,
                diagnostics=False,
                packages=False,
            )

            result = await builder.build([test_file], config)

            # Get IR document
            ir_doc = result.ir_documents.get(str(test_file))
            assert ir_doc is not None, f"Run {run}: IR doc not found"

            # Compute hash of nodes and edges
            node_hash = self._compute_ir_hash(ir_doc)
            hashes.append(node_hash)

        # All hashes should be identical
        assert len(set(hashes)) == 1, f"Hashes differ across runs: {hashes}"

    def _compute_ir_hash(self, ir_doc: IRDocument) -> str:
        """Compute stable hash of IR document"""
        hasher = hashlib.sha256()

        # Hash nodes (in order)
        for node in ir_doc.nodes:
            # Hash key fields only (deterministic)
            node_repr = f"{node.id}|{node.kind.value}|{node.fqn}|{node.file_path}|{node.local_seq}"
            if node.span:
                node_repr += f"|{node.span.start_line}|{node.span.end_line}"
            hasher.update(node_repr.encode())

        # Hash edges (in order)
        for edge in ir_doc.edges:
            edge_repr = f"{edge.id}|{edge.kind.value}|{edge.source_id}|{edge.target_id}|{edge.local_seq}"
            hasher.update(edge_repr.encode())

        return hasher.hexdigest()


class TestBuildIndexesIntegration:
    """Test build_indexes with total_order mode"""

    def test_build_indexes_with_total_order(self):
        """Test that build_indexes with total_order mode works correctly"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        # Add nodes in random order
        for i in [2, 0, 1]:
            node = Node(
                id=f"node:{i}",
                kind=NodeKind.FUNCTION,
                fqn=f"test.func{i}",
                file_path="test.py",
                span=Span(i * 10, 0, (i + 1) * 10, 0),
                language="python",
                local_seq=i,
            )
            ir_doc.nodes.append(node)

        # Build indexes with total_order
        ir_doc.build_indexes(sort_key="total_order")

        # Verify nodes are sorted
        assert ir_doc.nodes[0].local_seq == 0
        assert ir_doc.nodes[1].local_seq == 1
        assert ir_doc.nodes[2].local_seq == 2

        # Verify indexes are built
        assert ir_doc._node_index is not None
        assert len(ir_doc._node_index) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
