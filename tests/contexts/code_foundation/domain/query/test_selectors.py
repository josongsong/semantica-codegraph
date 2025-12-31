"""
Tests for NodeSelector and EdgeSelector
"""

import pytest

from codegraph_engine.code_foundation.domain.query import E, EdgeSelector, NodeSelector, Q
from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr


class TestNodeSelector:
    """Test NodeSelector creation and operators"""

    def test_create_var_selector(self):
        """Test Q.Var() factory"""
        var = Q.Var("input")
        assert isinstance(var, NodeSelector)
        assert var.selector_type == "var"
        assert var.name == "input"

    def test_create_func_selector(self):
        """Test Q.Func() factory"""
        func = Q.Func("process")
        assert isinstance(func, NodeSelector)
        assert func.selector_type == "func"
        assert func.name == "process"

    def test_forward_operator(self):
        """Test >> operator (N-hop forward)"""
        source = Q.Var("input")
        sink = Q.Call("execute")
        expr = source >> sink

        assert isinstance(expr, FlowExpr)
        assert expr.source == source
        assert expr.target == sink
        assert expr.direction == "forward"

    def test_adjacency_operator(self):
        """Test > operator (1-hop)"""
        caller = Q.Func("main")
        callee = Q.Func("helper")
        expr = caller > callee

        assert isinstance(expr, FlowExpr)
        assert expr.depth_range == (1, 1)

    def test_backward_operator(self):
        """Test << operator (backward)"""
        sink = Q.Call("execute")
        source = Q.Var("input")
        expr = sink << source

        assert isinstance(expr, FlowExpr)
        assert expr.source == source
        assert expr.target == sink
        assert expr.direction == "backward"

    def test_union_operator(self):
        """Test | operator (union)"""
        var1 = Q.Var("x")
        var2 = Q.Var("y")
        union = var1 | var2

        assert isinstance(union, NodeSelector)
        assert union.selector_type == "union"

    def test_intersection_operator(self):
        """Test & operator (intersection)"""
        var1 = Q.Var("x")
        var2 = Q.Source("request")
        intersection = var1 & var2

        assert isinstance(intersection, NodeSelector)
        assert intersection.selector_type == "intersection"


class TestEdgeSelector:
    """Test EdgeSelector"""

    def test_edge_factories(self):
        """Test E.DFG, E.CFG, E.CALL, E.ALL"""
        assert isinstance(E.DFG, EdgeSelector)
        assert E.DFG.edge_type == "dfg"

        assert isinstance(E.CFG, EdgeSelector)
        assert E.CFG.edge_type == "cfg"

        assert isinstance(E.CALL, EdgeSelector)
        assert E.CALL.edge_type == "call"

        assert isinstance(E.ALL, EdgeSelector)
        assert E.ALL.edge_type == "all"

    def test_backward(self):
        """Test .backward() method"""
        backward_dfg = E.DFG.backward()

        assert isinstance(backward_dfg, EdgeSelector)
        assert backward_dfg.edge_type == "dfg"
        assert backward_dfg.is_backward is True

    def test_depth(self):
        """Test .depth() method"""
        limited = E.DFG.depth(5)

        assert isinstance(limited, EdgeSelector)
        assert limited.max_depth == 5
        assert limited.min_depth == 1

    def test_depth_range(self):
        """Test .depth(max, min)"""
        limited = E.CFG.depth(10, 3)

        assert limited.min_depth == 3
        assert limited.max_depth == 10

    def test_union(self):
        """Test | operator (union)"""
        union = E.DFG | E.CALL

        assert isinstance(union, EdgeSelector)
        assert union.edge_type == "union"
