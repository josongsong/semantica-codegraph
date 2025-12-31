"""
Tests for FlowExpr and PathQuery
"""

import pytest

from codegraph_engine.code_foundation.domain.query import E, Q
from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr, PathQuery


class TestFlowExpr:
    """Test FlowExpr creation and modification"""

    def test_create_from_operators(self):
        """Test FlowExpr creation from >> operator"""
        source = Q.Var("input")
        sink = Q.Call("execute")
        expr = source >> sink

        assert isinstance(expr, FlowExpr)
        assert expr.source == source
        assert expr.target == sink

    def test_via_method(self):
        """Test .via() method"""
        expr = Q.Var("input") >> Q.Call("execute")
        modified = expr.via(E.DFG)

        # via() returns new FlowExpr (immutable)
        assert isinstance(modified, FlowExpr)
        assert modified.edge_type == E.DFG
        assert expr.edge_type is None  # Original unchanged

    def test_depth_method(self):
        """Test .depth() method"""
        expr = Q.Var("input") >> Q.Call("execute")
        modified = expr.depth(5)

        assert isinstance(modified, FlowExpr)
        assert modified.depth_range == (1, 5)

    def test_auto_promotion_where(self):
        """Test auto-promotion to PathQuery with .where()"""
        expr = Q.Var("input") >> Q.Call("execute")
        query = expr.where(lambda p: len(p) > 5)

        assert isinstance(query, PathQuery)
        assert query.flow == expr
        assert len(query.constraints) == 1

    def test_auto_promotion_within(self):
        """Test auto-promotion to PathQuery with .within()"""
        expr = Q.Var("input") >> Q.Call("execute")
        query = expr.within(Q.Module("core.*"))

        assert isinstance(query, PathQuery)
        assert len(query.constraints) == 1

    def test_auto_promotion_excluding(self):
        """Test auto-promotion to PathQuery with .excluding()"""
        expr = Q.Var("input") >> Q.Call("execute")
        query = expr.excluding(Q.Call("sanitize"))

        assert isinstance(query, PathQuery)
        assert len(query.constraints) == 1


class TestPathQuery:
    """Test PathQuery construction and chaining"""

    def test_create_from_flow_expr(self):
        """Test PathQuery.from_flow_expr()"""
        flow = Q.Var("input") >> Q.Call("execute")
        query = PathQuery.from_flow_expr(flow)

        assert isinstance(query, PathQuery)
        assert query.flow == flow
        assert len(query.constraints) == 0

    def test_method_chaining(self):
        """Test method chaining"""
        query = (
            (Q.Var("input") >> Q.Call("execute"))
            .via(E.DFG | E.CALL)
            .where(lambda p: len(p) < 10)
            .excluding(Q.Call("sanitize"))
            .limit_paths(20)
            .timeout(ms=5000)
        )

        assert isinstance(query, PathQuery)
        assert len(query.constraints) == 2  # where, excluding
        assert query.safety["max_paths"] == 20
        assert query.safety["timeout_ms"] == 5000

    def test_context_sensitive(self):
        """Test .context_sensitive()"""
        query = (Q.Var("input") >> Q.Call("execute")).context_sensitive(k=1)

        assert "context" in query.sensitivity
        assert query.sensitivity["context"]["k"] == 1

    def test_alias_sensitive(self):
        """Test .alias_sensitive()"""
        query = (Q.Var("input") >> Q.Call("execute")).alias_sensitive(mode="must")

        assert "alias" in query.sensitivity
        assert query.sensitivity["alias"]["mode"] == "must"

    def test_explain(self):
        """Test .explain() method"""
        query = (Q.Var("input") >> Q.Call("execute")).via(E.DFG).where(lambda p: len(p) > 5)

        explanation = query.explain()
        assert isinstance(explanation, str)
        assert "input" in explanation
        assert "execute" in explanation
        assert "dfg" in explanation.lower()

    def test_any_path_raises(self):
        """Test .any_path() raises without engine"""
        query = Q.Var("input") >> Q.Call("execute")

        with pytest.raises(Exception):  # InvalidQueryError
            query.any_path()

    def test_all_paths_raises(self):
        """Test .all_paths() raises without engine"""
        query = Q.Var("input") >> Q.Call("execute")

        with pytest.raises(Exception):  # InvalidQueryError
            query.all_paths()
