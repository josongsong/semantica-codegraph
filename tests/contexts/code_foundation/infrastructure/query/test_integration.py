"""
Integration Tests for Query Engine

End-to-end tests with real IRDocument.
"""

import pytest

from codegraph_engine.code_foundation import E, Q, QueryEngine
from codegraph_engine.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
)


@pytest.fixture
def simple_ir_doc():
    """
    Create simple IRDocument for testing

    Graph structure:
        var:x (input) --dfg--> var:y (intermediate) --dfg--> var:z (output)
    """
    ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

    # Add function node
    func_node = Node(
        id="func:test_func",
        kind=NodeKind.FUNCTION,
        fqn="test.test_func",
        file_path="test.py",
        span=Span(1, 0, 10, 0),
        language="python",
        name="test_func",
    )
    ir_doc.nodes.append(func_node)

    # Add variables
    var_x = VariableEntity(
        id="var:x", repo_id="test", file_path="test.py", function_fqn="test_func", name="x", kind="param"
    )
    var_y = VariableEntity(
        id="var:y", repo_id="test", file_path="test.py", function_fqn="test_func", name="y", kind="local"
    )
    var_z = VariableEntity(
        id="var:z", repo_id="test", file_path="test.py", function_fqn="test_func", name="z", kind="local"
    )

    # Add DFG edges
    edge1 = DataFlowEdge(
        id="dfg:1",
        from_variable_id="var:x",
        to_variable_id="var:y",
        kind="assign",
        repo_id="test",
        file_path="test.py",
        function_fqn="test_func",
    )
    edge2 = DataFlowEdge(
        id="dfg:2",
        from_variable_id="var:y",
        to_variable_id="var:z",
        kind="assign",
        repo_id="test",
        file_path="test.py",
        function_fqn="test_func",
    )

    dfg = DfgSnapshot(variables=[var_x, var_y, var_z], edges=[edge1, edge2])
    ir_doc.dfg_snapshot = dfg

    return ir_doc


@pytest.fixture
def call_graph_ir_doc():
    """
    Create IRDocument with call graph

    Graph structure:
        func:main --call--> func:helper
    """
    ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

    # Add function nodes
    func_main = Node(
        id="func:main",
        kind=NodeKind.FUNCTION,
        fqn="test.main",
        file_path="test.py",
        span=Span(1, 0, 5, 0),
        language="python",
        name="main",
    )
    func_helper = Node(
        id="func:helper",
        kind=NodeKind.FUNCTION,
        fqn="test.helper",
        file_path="test.py",
        span=Span(7, 0, 10, 0),
        language="python",
        name="helper",
    )
    ir_doc.nodes.extend([func_main, func_helper])

    # Add call edge
    call_edge = Edge(id="edge:call:1", source_id="func:main", target_id="func:helper", kind=EdgeKind.CALLS)
    ir_doc.edges.append(call_edge)

    return ir_doc


class TestQueryEngineIntegration:
    """Integration tests for Query Engine"""

    def test_simple_dfg_query(self, simple_ir_doc):
        """Test simple DFG query: x >> z"""
        engine = QueryEngine(simple_ir_doc)

        # Query: Find paths from x to z via DFG
        source = Q.Var("x")
        target = Q.Var("z")
        query = (source >> target).via(E.DFG)

        # Execute
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 1  # Should find 1 path: x → y → z
        path = result.paths[0]
        assert len(path) == 3  # 3 nodes
        assert path[0].name == "x"
        assert path[1].name == "y"
        assert path[2].name == "z"

    def test_1hop_query(self, simple_ir_doc):
        """Test 1-hop adjacency query: x > y"""
        engine = QueryEngine(simple_ir_doc)

        # Query: Find direct connection from x to y
        source = Q.Var("x")
        target = Q.Var("y")
        query = source > target

        # Execute
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 1
        path = result.paths[0]
        assert len(path) == 2  # x → y (1 hop)
        assert path[0].name == "x"
        assert path[1].name == "y"

    def test_no_path_found(self, simple_ir_doc):
        """Test query with no matching paths"""
        engine = QueryEngine(simple_ir_doc)

        # Query: z >> x (reverse direction, no path exists)
        source = Q.Var("z")
        target = Q.Var("x")
        query = (source >> target).via(E.DFG)

        # Execute
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 0
        assert result.complete is True

    def test_backward_query(self, simple_ir_doc):
        """Test backward query: z << x"""
        engine = QueryEngine(simple_ir_doc)

        # Query: Backward from z to x
        sink = Q.Var("z")
        source = Q.Var("x")
        query = (sink << source).via(E.DFG)

        # Execute
        result = engine.execute_any_path(query)

        # Verify: Should find path x → y → z (traversed backward)
        assert len(result) == 1
        path = result.paths[0]
        assert len(path) == 3
        assert path[0].name == "x"  # Path should be in forward order
        assert path[2].name == "z"

    def test_call_graph_query(self, call_graph_ir_doc):
        """Test call graph query: main >> helper"""
        engine = QueryEngine(call_graph_ir_doc)

        # Query: Find call path from main to helper
        caller = Q.Func("main")
        callee = Q.Func("helper")
        query = (caller >> callee).via(E.CALL)

        # Execute
        result = engine.execute_any_path(query)

        # Verify
        assert len(result) == 1
        path = result.paths[0]
        assert len(path) == 2
        assert path[0].name == "main"
        assert path[1].name == "helper"

    def test_excluding_constraint(self, simple_ir_doc):
        """Test .excluding() constraint"""
        engine = QueryEngine(simple_ir_doc)

        # Query: x >> z, excluding y
        source = Q.Var("x")
        target = Q.Var("z")
        query = (source >> target).via(E.DFG).excluding(Q.Var("y"))

        # Execute
        result = engine.execute_any_path(query)

        # Verify: No paths (only path goes through y)
        assert len(result) == 0

    def test_where_constraint(self, simple_ir_doc):
        """Test .where() predicate"""
        engine = QueryEngine(simple_ir_doc)

        # Query: x >> z, path length > 2
        source = Q.Var("x")
        target = Q.Var("z")
        query = (source >> target).via(E.DFG).where(lambda p: len(p) > 2)

        # Execute
        result = engine.execute_any_path(query)

        # Verify: Should find path (x → y → z has 3 nodes)
        assert len(result) == 1
        assert len(result.paths[0]) == 3

    def test_limit_paths(self, simple_ir_doc):
        """Test .limit_paths() safety"""
        engine = QueryEngine(simple_ir_doc)

        # Query with limit
        source = Q.Var("x")
        target = Q.Var("z")
        query = (source >> target).via(E.DFG).limit_paths(1)

        # Execute
        result = engine.execute_any_path(query)

        # Verify: At most 1 path
        assert len(result) <= 1

    def test_query_explain(self):
        """Test .explain() method"""
        source = Q.Var("input")
        sink = Q.Call("execute")
        query = (source >> sink).via(E.DFG).where(lambda p: len(p) < 10).limit_paths(20)

        explanation = query.explain()

        # Verify explanation contains key info
        assert "input" in explanation
        assert "execute" in explanation
        assert "dfg" in explanation.lower()
        assert "where" in explanation.lower()
