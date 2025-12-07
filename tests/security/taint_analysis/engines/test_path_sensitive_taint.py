"""
Unit tests for PathSensitiveTaintAnalyzer

Tests:
1. State propagation
2. State merging (Meet-Over-Paths)
3. Strong/weak updates
4. Path-sensitive analysis
5. Loop limiting
"""

from dataclasses import dataclass
from typing import List, Set

import pytest

from src.contexts.code_foundation.infrastructure.analyzers.path_sensitive_taint import (
    PathSensitiveTaintAnalyzer,
    TaintState,
    create_path_sensitive_analyzer,
)


class TestTaintState:
    """Test TaintState dataclass"""

    def test_basic_creation(self):
        """Test creating a basic state"""
        state = TaintState(
            tainted_vars={"x", "y"},
            path_condition=["is_admin"],
            depth=5,
        )

        assert state.tainted_vars == {"x", "y"}
        assert state.path_condition == ["is_admin"]
        assert state.depth == 5

    def test_copy(self):
        """Test state copying (deep copy)"""
        original = TaintState(
            tainted_vars={"x"},
            path_condition=["cond1"],
            depth=3,
        )

        copy = original.copy()

        # Modify copy
        copy.tainted_vars.add("y")
        copy.path_condition.append("cond2")
        copy.depth = 5

        # Original should be unchanged
        assert original.tainted_vars == {"x"}
        assert original.path_condition == ["cond1"]
        assert original.depth == 3


# Mock CFG/DFG for testing


@dataclass
class MockCFGNode:
    """Mock CFG node"""

    node_id: str
    type: str
    lhs: str = ""
    rhs: str = ""
    function_name: str = ""
    result_var: str = ""


@dataclass
class MockCFGEdge:
    """Mock CFG edge"""

    from_node: str
    to_node: str
    condition: str = ""


class MockCFG:
    """Mock Control Flow Graph"""

    def __init__(self):
        self.entry = "entry"
        self.nodes = {}
        self.edges = []
        self.successors = {}
        self.predecessors = {}

    def add_node(self, node: MockCFGNode):
        self.nodes[node.node_id] = node
        if node.node_id not in self.successors:
            self.successors[node.node_id] = []
        if node.node_id not in self.predecessors:
            self.predecessors[node.node_id] = []

    def add_edge(self, from_id: str, to_id: str, condition: str = ""):
        edge = MockCFGEdge(from_id, to_id, condition)
        self.edges.append(edge)
        self.successors[from_id].append(to_id)
        self.predecessors[to_id].append(from_id)


class MockDFG:
    """Mock Data Flow Graph"""

    pass


class TestPathSensitiveTaintAnalyzer:
    """Test PathSensitiveTaintAnalyzer"""

    def test_basic_initialization(self):
        """Test creating analyzer"""
        cfg = MockCFG()
        dfg = MockDFG()

        analyzer = PathSensitiveTaintAnalyzer(cfg, dfg, max_depth=50)

        assert analyzer.cfg is cfg
        assert analyzer.dfg is dfg
        assert analyzer.max_depth == 50

    def test_simple_taint_propagation(self):
        """Test simple taint propagation without branches"""
        # Build CFG:
        # entry → assign1 → assign2 → sink
        # assign1: x = user_input (source)
        # assign2: y = x
        # sink: execute(y)

        cfg = MockCFG()
        cfg.add_node(MockCFGNode("entry", "entry"))
        cfg.add_node(MockCFGNode("assign1", "assignment", lhs="x", rhs="user_input"))
        cfg.add_node(MockCFGNode("assign2", "assignment", lhs="y", rhs="x"))
        cfg.add_node(MockCFGNode("sink", "call", function_name="execute"))

        cfg.add_edge("entry", "assign1")
        cfg.add_edge("assign1", "assign2")
        cfg.add_edge("assign2", "sink")

        dfg = MockDFG()

        analyzer = PathSensitiveTaintAnalyzer(cfg, dfg)

        # Run analysis
        # Note: This is a basic test, actual implementation needs more integration
        # For now, just verify analyzer doesn't crash

        # Would test: vulns = analyzer.analyze(sources={"user_input"}, sinks={"sink"})
        # assert len(vulns) == 1

    def test_state_merging_at_join_point(self):
        """Test state merging with Meet-Over-Paths"""
        cfg = MockCFG()
        dfg = MockDFG()

        analyzer = PathSensitiveTaintAnalyzer(cfg, dfg)

        # Simulate two paths merging at join point
        state1 = TaintState(tainted_vars={"x"}, path_condition=["cond1"])
        state2 = TaintState(tainted_vars={"y"}, path_condition=["!cond1"])

        # Merge state1 first
        analyzer._merge_state("join", state1)
        assert analyzer.states["join"].tainted_vars == {"x"}

        # Merge state2 (should union)
        analyzer._merge_state("join", state2)
        assert analyzer.states["join"].tainted_vars == {"x", "y"}  # Union!

    def test_strong_update_single_predecessor(self):
        """Test strong update when single predecessor"""
        cfg = MockCFG()
        dfg = MockDFG()

        analyzer = PathSensitiveTaintAnalyzer(cfg, dfg)

        # Single predecessor → strong update (replace)
        state1 = TaintState(tainted_vars={"x"})
        state2 = TaintState(tainted_vars={"y"})

        analyzer._strong_update("node1", state1)
        assert analyzer.states["node1"].tainted_vars == {"x"}

        analyzer._strong_update("node1", state2)
        assert analyzer.states["node1"].tainted_vars == {"y"}  # Replaced!

    def test_sanitizing_condition(self):
        """Test that conditions can sanitize taint"""
        cfg = MockCFG()
        dfg = MockDFG()

        analyzer = PathSensitiveTaintAnalyzer(cfg, dfg)

        # Test various sanitizing conditions
        assert analyzer._sanitizes_condition("is_admin", {"x"}) is True
        assert analyzer._sanitizes_condition("is_authenticated", {"x"}) is True
        assert analyzer._sanitizes_condition("x.isdigit()", {"x"}) is True
        assert analyzer._sanitizes_condition("re.match(pattern, x)", {"x"}) is True

        # Non-sanitizing condition
        assert analyzer._sanitizes_condition("x > 5", {"x"}) is False


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_create_path_sensitive_analyzer(self):
        """Test creating analyzer via convenience function"""
        cfg = MockCFG()
        dfg = MockDFG()

        analyzer = create_path_sensitive_analyzer(cfg, dfg, max_depth=42)

        assert isinstance(analyzer, PathSensitiveTaintAnalyzer)
        assert analyzer.max_depth == 42


# Integration scenarios


class TestIntegrationScenarios:
    """Test realistic analysis scenarios"""

    def test_if_else_branch_scenario(self):
        """
        Test scenario:
            user_input = get_input()  # Source

            if is_admin:
                execute(query)  # Path 1: Sanitized by condition
            else:
                execute(query)  # Path 2: Tainted!
        """
        # This would require full CFG integration
        # Placeholder for future implementation
        pass

    def test_sanitizer_function_scenario(self):
        """
        Test scenario:
            user_input = get_input()  # Source
            clean = escape_html(user_input)  # Sanitizer
            render(clean)  # Sink: clean
        """
        # Placeholder
        pass

    def test_loop_scenario(self):
        """
        Test scenario with loop (depth limiting):
            for i in range(10):
                x = process(x)
        """
        # Should hit max_depth and stop
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
