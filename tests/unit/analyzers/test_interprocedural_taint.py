"""
Tests for Inter-procedural Taint Analysis
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    CallContext,
    FunctionSummary,
    InterproceduralTaintAnalyzer,
    SimpleCallGraph,
    TaintPath,
)


class TestCallContext:
    """Test CallContext"""

    def test_create(self):
        """Test context creation"""
        ctx = CallContext()
        assert ctx.call_stack == []
        assert ctx.depth == 0
        assert not ctx.return_tainted

    def test_copy(self):
        """Test deep copy"""
        ctx = CallContext(
            call_stack=["main", "foo"],
            tainted_params={0: {"user_input"}},
            depth=2,
        )

        copy = ctx.copy()
        assert copy.call_stack == ["main", "foo"]
        assert copy.depth == 2

        # Modify copy shouldn't affect original
        copy.call_stack.append("bar")
        assert ctx.call_stack == ["main", "foo"]

    def test_with_call(self):
        """Test adding call to context"""
        ctx = CallContext()
        new_ctx = ctx.with_call("foo")

        assert new_ctx.call_stack == ["foo"]
        assert new_ctx.depth == 1
        assert ctx.call_stack == []  # Original unchanged


class TestTaintPath:
    """Test TaintPath"""

    def test_create(self):
        """Test path creation"""
        path = TaintPath(
            source="get_input",
            sink="execute",
            path=["get_input", "process", "execute"],
            confidence=0.95,
        )

        assert path.source == "get_input"
        assert path.sink == "execute"
        assert len(path.path) == 3
        assert path.confidence == 0.95


class TestSimpleCallGraph:
    """Test SimpleCallGraph"""

    def test_add_call(self):
        """Test adding calls"""
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")
        cg.add_call("foo", "bar")

        assert cg.get_callees("main") == ["foo"]
        assert cg.get_callees("foo") == ["bar"]
        assert cg.get_callees("bar") == []

    def test_get_functions(self):
        """Test getting all functions"""
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")
        cg.add_call("foo", "bar")

        funcs = set(cg.get_functions())
        assert funcs == {"main", "foo", "bar"}


class TestInterproceduralTaintAnalyzer:
    """Test InterproceduralTaintAnalyzer"""

    def test_simple_propagation(self):
        """Test simple taint propagation"""
        # Build call graph:
        # main -> process -> execute
        cg = SimpleCallGraph()
        cg.add_call("main", "process")
        cg.add_call("process", "execute")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Sources: main returns tainted
        # Sinks: execute receives tainted
        sources = {"main": {0}}
        sinks = {"execute": {0}}

        paths = analyzer.analyze(sources, sinks)

        # Should find path main -> process -> execute
        assert len(paths) > 0
        assert any(p.source == "main" and p.sink == "execute" for p in paths)

    def test_no_path(self):
        """Test when no path exists"""
        # main -> foo
        # bar -> execute (disconnected)
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")
        cg.add_call("bar", "execute")

        analyzer = InterproceduralTaintAnalyzer(cg)

        sources = {"main": {0}}
        sinks = {"execute": {0}}

        paths = analyzer.analyze(sources, sinks)

        # main cannot reach execute
        assert all(p.source != "main" or p.sink != "execute" for p in paths)

    def test_max_depth(self):
        """Test max depth limiting"""
        # Build deep chain
        cg = SimpleCallGraph()
        for i in range(20):
            cg.add_call(f"f{i}", f"f{i + 1}")

        analyzer = InterproceduralTaintAnalyzer(cg, max_depth=5)

        sources = {"f0": {0}}
        sinks = {"f20": {0}}

        paths = analyzer.analyze(sources, sinks)

        # Should still find path (depth limit doesn't prevent BFS)
        # But limits recursion depth
        assert isinstance(paths, list)

    def test_cycle_detection(self):
        """Test circular call handling"""
        # main -> foo -> bar -> foo (cycle)
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")
        cg.add_call("foo", "bar")
        cg.add_call("bar", "foo")  # Cycle

        analyzer = InterproceduralTaintAnalyzer(cg)

        sources = {"main": {0}}
        sinks = {"bar": {0}}

        # Should not infinite loop
        paths = analyzer.analyze(sources, sinks)
        assert isinstance(paths, list)

    def test_branching_calls(self):
        """Test branching call graph"""
        # main -> foo
        # main -> bar
        # foo -> sink
        # bar -> sink
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")
        cg.add_call("main", "bar")
        cg.add_call("foo", "sink")
        cg.add_call("bar", "sink")

        analyzer = InterproceduralTaintAnalyzer(cg)

        sources = {"main": {0}}
        sinks = {"sink": {0}}

        paths = analyzer.analyze(sources, sinks)

        # Should find both paths
        assert len(paths) > 0

    def test_function_summary(self):
        """Test function summary creation"""
        summary = FunctionSummary(
            name="process",
            tainted_params={0, 1},
            return_tainted=True,
        )

        assert summary.name == "process"
        assert 0 in summary.tainted_params
        assert summary.return_tainted

    def test_empty_sources(self):
        """Test with no sources"""
        cg = SimpleCallGraph()
        cg.add_call("main", "foo")

        analyzer = InterproceduralTaintAnalyzer(cg)

        paths = analyzer.analyze({}, {"foo": {0}})

        # No sources = no paths
        assert len(paths) == 0

    def test_max_paths(self):
        """Test max paths limiting"""
        # Create many paths
        cg = SimpleCallGraph()
        for i in range(50):
            cg.add_call("main", f"sink{i}")

        analyzer = InterproceduralTaintAnalyzer(cg, max_paths=10)

        sources = {"main": {0}}
        sinks = {f"sink{i}": {0} for i in range(50)}

        paths = analyzer.analyze(sources, sinks)

        # Should limit to max_paths
        assert len(paths) <= 10
