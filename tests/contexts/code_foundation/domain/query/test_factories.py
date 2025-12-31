"""
Q and E Factories Unit Tests

SOTA L11급:
- Base case: 모든 팩토리 메서드
- Edge case: None 파라미터
- Corner case: 특수 문자, 복잡한 패턴
"""

import pytest

from codegraph_engine.code_foundation.domain.query.factories import E, Q
from codegraph_engine.code_foundation.domain.query.selectors import EdgeSelector, NodeSelector
from codegraph_engine.code_foundation.domain.query.types import EdgeType, SelectorType


class TestQFactory:
    """Q (NodeSelector) 팩토리 테스트"""

    # ========================================================================
    # Base Cases
    # ========================================================================

    def test_var_basic(self):
        """Q.Var 기본"""
        selector = Q.Var("x")

        assert isinstance(selector, NodeSelector)
        assert selector.selector_type == SelectorType.VAR
        assert selector.name == "x"

    def test_var_with_type(self):
        """Q.Var with type"""
        selector = Q.Var("x", type="str")

        assert selector.attrs["type"] == "str"

    def test_var_with_scope(self):
        """Q.Var with scope"""
        selector = Q.Var("x", scope="main")

        assert selector.attrs["scope"] == "main"

    def test_var_with_context(self):
        """Q.Var with context (k-CFA)"""
        selector = Q.Var("x", context="call_123")

        assert selector.context == "call_123"

    def test_func_basic(self):
        """Q.Func 기본"""
        selector = Q.Func("process")

        assert selector.selector_type == SelectorType.FUNC
        assert selector.name == "process"

    def test_call_basic(self):
        """Q.Call 기본"""
        selector = Q.Call("execute")

        assert selector.selector_type == SelectorType.CALL
        assert selector.name == "execute"

    def test_block_basic(self):
        """Q.Block 기본"""
        selector = Q.Block("entry")

        assert selector.selector_type == SelectorType.BLOCK
        assert selector.name == "entry"

    def test_module_basic(self):
        """Q.Module 기본"""
        selector = Q.Module("core.*")

        assert selector.selector_type == SelectorType.MODULE
        assert selector.pattern == "core.*"

    def test_class_basic(self):
        """Q.Class 기본"""
        selector = Q.Class("User")

        assert selector.selector_type == SelectorType.CLASS
        assert selector.name == "User"

    def test_source_basic(self):
        """Q.Source 기본"""
        selector = Q.Source("request")

        assert selector.selector_type == SelectorType.SOURCE
        assert selector.attrs["category"] == "request"

    def test_sink_basic(self):
        """Q.Sink 기본"""
        selector = Q.Sink("execute")

        assert selector.selector_type == SelectorType.SINK
        assert selector.attrs["category"] == "execute"

    def test_any_basic(self):
        """Q.Any 기본"""
        selector = Q.Any()

        assert selector.selector_type == SelectorType.ANY

    def test_field_basic(self):
        """Q.Field 기본"""
        selector = Q.Field("user", "id")

        assert selector.selector_type == SelectorType.FIELD
        assert selector.name == "user.id"
        assert selector.attrs["obj_name"] == "user"
        assert selector.attrs["field_name"] == "id"

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_var_none_name(self):
        """Q.Var(None) - wildcard"""
        selector = Q.Var(None)

        assert selector.name is None

    def test_func_none_name(self):
        """Q.Func(None) - wildcard"""
        selector = Q.Func(None)

        assert selector.name is None

    # ========================================================================
    # Corner Cases
    # ========================================================================

    def test_var_field_access(self):
        """Q.Var with field access syntax"""
        selector = Q.Var("user.password")

        assert selector.name == "user.password"

    def test_call_method_syntax(self):
        """Q.Call with method syntax"""
        selector = Q.Call("logger.write")

        assert selector.name == "logger.write"

    def test_module_glob_pattern(self):
        """Q.Module with complex glob"""
        selector = Q.Module("src.**.utils")

        assert selector.pattern == "src.**.utils"


class TestEFactory:
    """E (EdgeSelector) 팩토리 테스트"""

    # ========================================================================
    # Base Cases
    # ========================================================================

    def test_dfg(self):
        """E.DFG"""
        assert isinstance(E.DFG, EdgeSelector)
        assert E.DFG.edge_type == EdgeType.DFG

    def test_cfg(self):
        """E.CFG"""
        assert E.CFG.edge_type == EdgeType.CFG

    def test_call(self):
        """E.CALL"""
        assert E.CALL.edge_type == EdgeType.CALL

    def test_all(self):
        """E.ALL"""
        assert E.ALL.edge_type == EdgeType.ALL

    def test_backward(self):
        """E.DFG.backward()"""
        backward = E.DFG.backward()

        assert backward.is_backward is True
        assert backward.edge_type == EdgeType.DFG

    def test_depth(self):
        """E.DFG.depth()"""
        with_depth = E.DFG.depth(5)

        assert with_depth.max_depth == 5
        assert with_depth.min_depth == 1

    def test_depth_range(self):
        """E.DFG.depth(max, min)"""
        with_range = E.DFG.depth(10, 3)

        assert with_range.max_depth == 10
        assert with_range.min_depth == 3

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_union(self):
        """E.DFG | E.CALL"""
        union = E.DFG | E.CALL

        assert union.edge_type == "union"
        assert len(union.attrs["operands"]) == 2

    # ========================================================================
    # Corner Cases
    # ========================================================================

    def test_chained_modifiers(self):
        """E.DFG.backward().depth(5)"""
        chained = E.DFG.backward().depth(5)

        assert chained.is_backward is True
        assert chained.max_depth == 5


class TestOperatorIntegration:
    """Q와 E 연산자 통합 테스트"""

    def test_forward_operator(self):
        """>> 연산자"""
        from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr

        flow = Q.Var("x") >> Q.Var("y")

        assert isinstance(flow, FlowExpr)
        assert flow.source.name == "x"
        assert flow.target.name == "y"

    def test_adjacency_operator(self):
        """> 연산자"""
        flow = Q.Func("a") > Q.Func("b")

        assert flow.depth_range == (1, 1)

    def test_backward_operator(self):
        """<< 연산자"""
        flow = Q.Var("y") << Q.Var("x")

        # y가 target, x가 source
        assert flow.source.name == "x"
        assert flow.target.name == "y"

    def test_via_chain(self):
        """via() 체이닝"""
        flow = (Q.Var("x") >> Q.Var("y")).via(E.DFG)

        assert flow.edge_type == E.DFG
