"""
Real Integration Test: Inter-procedural Taint + PreciseCallGraph

Tests actual integration with production components.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.call_graph_adapter import (
    CallGraphAdapter,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    InterproceduralTaintAnalyzer,
)
from codegraph_engine.code_foundation.infrastructure.graphs.precise_call_graph import (
    CallSite,
    PreciseCallEdge,
    PreciseCallGraphBuilder,
)


class TestRealIntegration:
    """Test with actual PreciseCallGraphBuilder"""

    def test_adapter_interface(self):
        """Test CallGraphAdapter implements required interface"""
        builder = PreciseCallGraphBuilder()

        # Add some edges manually
        builder.edges = [
            PreciseCallEdge(
                caller_id="main",
                callee_id="foo",
                call_site=CallSite(
                    caller_id="main",
                    callee_name="foo",
                    location=(10, 5),
                ),
            ),
            PreciseCallEdge(
                caller_id="foo",
                callee_id="bar",
                call_site=CallSite(
                    caller_id="foo",
                    callee_name="bar",
                    location=(20, 5),
                ),
            ),
        ]

        adapter = CallGraphAdapter(builder)

        # Check interface
        assert hasattr(adapter, "get_callees")
        assert hasattr(adapter, "get_functions")

        # Check data
        assert adapter.get_callees("main") == ["foo"]
        assert adapter.get_callees("foo") == ["bar"]
        assert set(adapter.get_functions()) == {"main", "foo", "bar"}

    def test_analyzer_with_adapter(self):
        """Test InterproceduralTaintAnalyzer with CallGraphAdapter"""
        builder = PreciseCallGraphBuilder()

        # Build call graph: source -> process -> sink
        builder.edges = [
            PreciseCallEdge(
                caller_id="source",
                callee_id="process",
                call_site=CallSite(
                    caller_id="source",
                    callee_name="process",
                    location=(5, 1),
                ),
            ),
            PreciseCallEdge(
                caller_id="process",
                callee_id="sink",
                call_site=CallSite(
                    caller_id="process",
                    callee_name="sink",
                    location=(10, 1),
                ),
            ),
        ]

        adapter = CallGraphAdapter(builder)
        analyzer = InterproceduralTaintAnalyzer(adapter)

        # Define sources and sinks
        sources = {"source": {0}}
        sinks = {"sink": {0}}

        # Analyze
        paths = analyzer.analyze(sources, sinks)

        # Should find path source -> process -> sink
        assert len(paths) > 0
        assert any(p.source == "source" and p.sink == "sink" for p in paths)

    def test_adapter_invalid_builder(self):
        """Test adapter rejects invalid builder"""
        with pytest.raises(TypeError, match="Expected PreciseCallGraphBuilder"):
            CallGraphAdapter("not_a_builder")

    def test_analyzer_invalid_call_graph(self):
        """Test analyzer validates call_graph interface"""

        class InvalidCallGraph:
            pass

        with pytest.raises(TypeError, match="must implement get_callees"):
            InterproceduralTaintAnalyzer(InvalidCallGraph())

    def test_empty_call_graph(self):
        """Test with empty call graph"""
        builder = PreciseCallGraphBuilder()
        builder.edges = []

        adapter = CallGraphAdapter(builder)
        analyzer = InterproceduralTaintAnalyzer(adapter)

        paths = analyzer.analyze({"foo": {0}}, {"bar": {0}})

        # No edges = no paths
        assert len(paths) == 0

    def test_adapter_get_callers(self):
        """Test reverse lookup (callers)"""
        builder = PreciseCallGraphBuilder()
        builder.edges = [
            PreciseCallEdge(
                caller_id="main",
                callee_id="foo",
                call_site=CallSite(
                    caller_id="main",
                    callee_name="foo",
                    location=(1, 1),
                ),
            ),
            PreciseCallEdge(
                caller_id="bar",
                callee_id="foo",
                call_site=CallSite(
                    caller_id="bar",
                    callee_name="foo",
                    location=(2, 1),
                ),
            ),
        ]

        adapter = CallGraphAdapter(builder)

        # foo is called by both main and bar
        callers = set(adapter.get_callers("foo"))
        assert callers == {"main", "bar"}

    def test_adapter_rebuild_index(self):
        """Test rebuilding index after edges change"""
        builder = PreciseCallGraphBuilder()
        builder.edges = [
            PreciseCallEdge(
                caller_id="a",
                callee_id="b",
                call_site=CallSite(
                    caller_id="a",
                    callee_name="b",
                    location=(1, 1),
                ),
            ),
        ]

        adapter = CallGraphAdapter(builder)
        assert adapter.get_callees("a") == ["b"]

        # Add more edges
        builder.edges.append(
            PreciseCallEdge(
                caller_id="a",
                callee_id="c",
                call_site=CallSite(
                    caller_id="a",
                    callee_name="c",
                    location=(2, 1),
                ),
            )
        )

        # Rebuild
        adapter.rebuild_index()

        # Now should see both
        assert set(adapter.get_callees("a")) == {"b", "c"}
