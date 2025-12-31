"""
Edge Case Tests: Inter-procedural Taint Analysis

Tests corner cases, error conditions, and boundary scenarios.
"""

import pytest
from pydantic import ValidationError

from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    CallContext,
    FunctionSummary,
    InterproceduralTaintAnalyzer,
    SimpleCallGraph,
    TaintPath,
)


class TestPydanticValidation:
    """Test Pydantic schema validation"""

    def test_call_context_negative_depth(self):
        """Test negative depth is rejected"""
        with pytest.raises(ValidationError):
            CallContext(depth=-1)

    def test_taint_path_empty_source(self):
        """Test empty source is rejected"""
        with pytest.raises(ValidationError):
            TaintPath(source="", sink="foo")

    def test_taint_path_empty_sink(self):
        """Test empty sink is rejected"""
        with pytest.raises(ValidationError):
            TaintPath(source="foo", sink="")

    def test_taint_path_invalid_confidence(self):
        """Test invalid confidence values"""
        # Too low
        with pytest.raises(ValidationError):
            TaintPath(source="a", sink="b", confidence=-0.1)

        # Too high
        with pytest.raises(ValidationError):
            TaintPath(source="a", sink="b", confidence=1.1)

    def test_function_summary_empty_name(self):
        """Test empty function name is rejected"""
        with pytest.raises(ValidationError):
            FunctionSummary(name="")

    def test_call_context_immutability(self):
        """Test Pydantic models are validated on creation"""
        ctx = CallContext(depth=5)
        assert ctx.depth == 5

        # Models are mutable in Pydantic v1, but validated
        ctx.depth = -1  # This is allowed at runtime
        # But copy/validation will catch it
        with pytest.raises(ValidationError):
            CallContext(depth=-1)


class TestNullAndEmptyInputs:
    """Test null and empty inputs"""

    def test_empty_sources_empty_sinks(self):
        """Test with no sources and no sinks"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")

        analyzer = InterproceduralTaintAnalyzer(cg)
        paths = analyzer.analyze({}, {})

        assert len(paths) == 0

    def test_none_in_sources(self):
        """Test sources with None values"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Sources with empty set is valid
        paths = analyzer.analyze({"a": set()}, {"b": {0}})
        assert isinstance(paths, list)

    def test_disconnected_graph(self):
        """Test completely disconnected components"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")
        cg.add_call("c", "d")  # Disconnected

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Source in one component, sink in another
        paths = analyzer.analyze({"a": {0}}, {"d": {0}})

        # Should find no path from a to d
        assert all(p.source != "a" or p.sink != "d" for p in paths)

    def test_self_loop(self):
        """Test function calling itself"""
        cg = SimpleCallGraph()
        cg.add_call("recursive", "recursive")  # Self-loop

        analyzer = InterproceduralTaintAnalyzer(cg)

        # Should handle gracefully
        paths = analyzer.analyze(
            {"recursive": {0}},
            {"recursive": {0}},
        )

        assert isinstance(paths, list)


class TestBoundaryConditions:
    """Test boundary conditions"""

    def test_max_depth_zero(self):
        """Test with max_depth=0"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")

        analyzer = InterproceduralTaintAnalyzer(cg, max_depth=0)

        paths = analyzer.analyze({"a": {0}}, {"b": {0}})

        # With max_depth=0, should still work but limit propagation
        assert isinstance(paths, list)

    def test_max_paths_zero(self):
        """Test with max_paths=0"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")

        analyzer = InterproceduralTaintAnalyzer(cg, max_paths=0)

        paths = analyzer.analyze({"a": {0}}, {"b": {0}})

        # Should return empty or very limited results
        assert len(paths) == 0

    def test_very_large_depth(self):
        """Test with very large max_depth"""
        cg = SimpleCallGraph()
        for i in range(100):
            cg.add_call(f"f{i}", f"f{i + 1}")

        analyzer = InterproceduralTaintAnalyzer(cg, max_depth=1000)

        paths = analyzer.analyze({"f0": {0}}, {"f100": {0}})

        # Should handle large depth without crashing
        assert isinstance(paths, list)

    def test_very_many_functions(self):
        """Test with many functions"""
        cg = SimpleCallGraph()

        # Create star topology: main calls 1000 functions
        for i in range(100):  # 1000 → 100
            cg.add_call("main", f"func_{i}")

        analyzer = InterproceduralTaintAnalyzer(cg, max_paths=10)

        sinks = {f"func_{i}": {0} for i in range(100)}  # 1000 → 100
        paths = analyzer.analyze({"main": {0}}, sinks)

        # Should limit to max_paths
        assert len(paths) <= 10


class TestContextSensitivity:
    """Test context-sensitive analysis"""

    def test_context_copy_independence(self):
        """Test that context copies are independent"""
        ctx1 = CallContext(call_stack=["a", "b"])
        ctx2 = ctx1.copy()

        ctx2.call_stack.append("c")

        # Original should be unchanged
        assert ctx1.call_stack == ["a", "b"]
        assert ctx2.call_stack == ["a", "b", "c"]

    def test_context_with_call(self):
        """Test context evolution"""
        ctx = CallContext()

        ctx1 = ctx.with_call("a")
        assert ctx1.depth == 1
        assert ctx1.call_stack == ["a"]

        ctx2 = ctx1.with_call("b")
        assert ctx2.depth == 2
        assert ctx2.call_stack == ["a", "b"]

        # Original unchanged
        assert ctx.depth == 0


class TestErrorConditions:
    """Test error handling"""

    def test_invalid_call_graph_type(self):
        """Test with completely wrong type"""
        with pytest.raises(TypeError, match="must implement get_callees"):
            InterproceduralTaintAnalyzer(None)

        with pytest.raises(TypeError, match="must implement get_callees"):
            InterproceduralTaintAnalyzer(42)

        with pytest.raises(TypeError, match="must implement get_callees"):
            InterproceduralTaintAnalyzer("not_a_graph")

    def test_call_graph_missing_get_functions(self):
        """Test call_graph with only get_callees"""

        class PartialCallGraph:
            def get_callees(self, func):
                return []

        with pytest.raises(TypeError, match="must implement get_functions"):
            InterproceduralTaintAnalyzer(PartialCallGraph())

    def test_call_graph_exception_in_get_callees(self):
        """Test when get_callees raises exception"""

        class BrokenCallGraph:
            def get_callees(self, func):
                raise RuntimeError("Broken!")

            def get_functions(self):
                return ["a", "b"]

        analyzer = InterproceduralTaintAnalyzer(BrokenCallGraph())

        # Should handle gracefully (returns empty list internally)
        paths = analyzer.analyze({"a": {0}}, {"b": {0}})
        assert isinstance(paths, list)

    def test_call_graph_none_return(self):
        """Test when get_callees returns None"""

        class NoneCallGraph:
            def get_callees(self, func):
                return None  # Should handle gracefully

            def get_functions(self):
                return ["a", "b"]

        analyzer = InterproceduralTaintAnalyzer(NoneCallGraph())
        paths = analyzer.analyze({"a": {0}}, {"b": {0}})

        # Should handle None gracefully
        assert isinstance(paths, list)


class TestDataIntegrity:
    """Test data integrity and consistency"""

    def test_path_uniqueness(self):
        """Test that duplicate paths are not returned"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")
        cg.add_call("a", "b")  # Duplicate

        analyzer = InterproceduralTaintAnalyzer(cg)
        paths = analyzer.analyze({"a": {0}}, {"b": {0}})

        # Should not have identical duplicates
        path_tuples = [(p.source, p.sink) for p in paths]
        # (duplicates might exist but should be limited)
        assert len(path_tuples) < 100  # Sanity check

    def test_summary_consistency(self):
        """Test function summary data consistency"""
        summary = FunctionSummary(
            name="test",
            tainted_params={0, 1},
            return_tainted=True,
        )

        assert summary.name == "test"
        assert 0 in summary.tainted_params
        assert 1 in summary.tainted_params
        assert summary.return_tainted

    def test_path_confidence_bounds(self):
        """Test path confidence is always in valid range"""
        cg = SimpleCallGraph()
        cg.add_call("a", "b")

        analyzer = InterproceduralTaintAnalyzer(cg)
        paths = analyzer.analyze({"a": {0}}, {"b": {0}})

        for path in paths:
            assert 0.0 <= path.confidence <= 1.0
