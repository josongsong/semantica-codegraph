"""
RFC-037 Phase 0: IRQuery Port + Adapter Tests

Tests for:
1. IRQuery protocol definition
2. IRDocumentAdapter implementation
3. Hexagonal architecture compliance
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.ir_query import IRQuery
from codegraph_engine.code_foundation.infrastructure.ir.adapters import IRDocumentAdapter
from codegraph_engine.code_foundation.infrastructure.ir.models import (
    Edge,
    EdgeKind,
    IRDocument,
    Node,
    NodeKind,
    Occurrence,
    Span,
    SymbolRole,
)


# ============================================================
# BASE CASES: Protocol Implementation
# ============================================================


class TestIRDocumentAdapter:
    """Test IRDocumentAdapter implements IRQuery."""

    def test_adapter_implements_protocol(self):
        """Adapter implements IRQuery protocol."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test")
        adapter = IRDocumentAdapter(ir_doc)

        assert isinstance(adapter, IRQuery)

    def test_get_all_nodes(self):
        """Get all nodes."""
        node1 = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(1, 0, 5, 0),
            file_path="test.py",
            language="python",
        )
        node2 = Node(
            id="class::Test",
            kind=NodeKind.CLASS,
            name="Test",
            fqn="Test",
            span=Span(10, 0, 20, 0),
            file_path="test.py",
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[node1, node2],
        )
        adapter = IRDocumentAdapter(ir_doc)

        nodes = adapter.get_nodes()
        assert len(nodes) == 2
        assert node1 in nodes
        assert node2 in nodes

    def test_get_nodes_filtered_by_kind(self):
        """Get nodes filtered by kind."""
        func = Node(
            id="func::test",
            kind=NodeKind.FUNCTION,
            name="test",
            fqn="test",
            span=Span(1, 0, 5, 0),
            file_path="test.py",
            language="python",
        )
        cls = Node(
            id="class::Test",
            kind=NodeKind.CLASS,
            name="Test",
            fqn="Test",
            span=Span(10, 0, 20, 0),
            file_path="test.py",
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func, cls],
        )
        adapter = IRDocumentAdapter(ir_doc)

        functions = adapter.get_nodes(NodeKind.FUNCTION)
        assert len(functions) == 1
        assert functions[0].kind == NodeKind.FUNCTION

        classes = adapter.get_nodes(NodeKind.CLASS)
        assert len(classes) == 1
        assert classes[0].kind == NodeKind.CLASS

    def test_get_edges_filtered_by_kind(self):
        """Get edges filtered by kind."""
        calls_edge = Edge(
            id="edge::1",
            source_id="func::a",
            target_id="func::b",
            kind=EdgeKind.CALLS,
        )
        defines_edge = Edge(
            id="edge::2",
            source_id="class::A",
            target_id="func::a",
            kind=EdgeKind.DEFINES,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            edges=[calls_edge, defines_edge],
        )
        adapter = IRDocumentAdapter(ir_doc)

        calls = adapter.get_edges(EdgeKind.CALLS)
        assert len(calls) == 1
        assert calls[0].kind == EdgeKind.CALLS

        defines = adapter.get_edges(EdgeKind.DEFINES)
        assert len(defines) == 1
        assert defines[0].kind == EdgeKind.DEFINES

    def test_get_occurrences_all(self):
        """Get all occurrences (schema-agnostic)."""
        # Test with empty occurrences (schema-safe)
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            occurrences=[],
        )
        adapter = IRDocumentAdapter(ir_doc)

        # Get all
        all_occs = adapter.get_occurrences(None)
        assert all_occs == []

        # Get filtered (returns empty for non-existent)
        filtered = adapter.get_occurrences("test_func")
        assert filtered == []


# ============================================================
# EDGE CASES: Tier Detection
# ============================================================


class TestTierDetection:
    """Test has_tier method."""

    def test_base_tier_always_true(self):
        """BASE tier always available (has nodes)."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test")
        adapter = IRDocumentAdapter(ir_doc)

        assert adapter.has_tier("base")
        assert adapter.has_tier("BASE")

    def test_extended_tier_with_dfg(self):
        """EXTENDED tier when DFG present."""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

        dfg = DfgSnapshot(variables=[], events=[], edges=[])
        expr = Expression(
            id="expr::1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="test",
            span=Span(1, 0, 1, 10),
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            dfg_snapshot=dfg,
            expressions=[expr],
        )
        adapter = IRDocumentAdapter(ir_doc)

        assert adapter.has_tier("extended")

    def test_extended_tier_without_dfg(self):
        """EXTENDED tier false without DFG."""
        ir_doc = IRDocument(repo_id="test", snapshot_id="test")
        adapter = IRDocumentAdapter(ir_doc)

        assert not adapter.has_tier("extended")


# ============================================================
# HEXAGONAL: Architecture Compliance
# ============================================================


class TestHexagonalCompliance:
    """Test Hexagonal architecture compliance."""

    def test_adapter_has_no_domain_imports(self):
        """Adapter (Infrastructure) can import Domain."""
        # This is allowed: Infrastructure → Domain
        from codegraph_engine.code_foundation.infrastructure.ir.adapters import IRDocumentAdapter
        # Should not raise

    def test_protocol_has_no_infrastructure_imports(self):
        """Protocol (Domain) has no Infrastructure imports outside TYPE_CHECKING."""
        import inspect
        from codegraph_engine.code_foundation.domain.ports import ir_query

        source = inspect.getsource(ir_query)

        # TYPE_CHECKING imports are OK (not runtime dependency)
        # Check that infrastructure imports are only in TYPE_CHECKING block
        lines = source.split("\n")
        in_type_checking = False

        for line in lines:
            if "if TYPE_CHECKING:" in line:
                in_type_checking = True
            elif line.startswith("if ") or (line and not line[0].isspace()):
                in_type_checking = False

            # Infrastructure import outside TYPE_CHECKING is violation
            if not in_type_checking and "from codegraph_engine.code_foundation.infrastructure" in line:
                pytest.fail(f"Infrastructure import outside TYPE_CHECKING: {line}")

        # If we got here, all infrastructure imports are in TYPE_CHECKING ✅


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
