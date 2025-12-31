from __future__ import annotations

from dataclasses import dataclass, field

from codegraph_engine.code_foundation.domain.type_inference.config import LocalFlowConfig
from codegraph_engine.code_foundation.infrastructure.ir.models import Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGEdgeKind,
    CFGBlockKind,
    ControlFlowBlock,
    ControlFlowEdge,
    ControlFlowGraph,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind, Expression
from codegraph_engine.code_foundation.infrastructure.type_inference.local_flow_inferencer import (
    LocalFlowTypeInferencer,
)


@dataclass
class _Node:
    id: str
    attrs: dict = field(default_factory=dict)


@dataclass
class _IRDoc:
    nodes: list[_Node]


def _span(line: int, col: int) -> Span:
    return Span(start_line=line, start_col=col, end_line=line, end_col=col + 1)


def test_return_x_uses_cfg_join_to_merge_reaching_defs_types():
    fn_id = "fn:1"
    # CFG blocks
    entry = ControlFlowBlock(id="b0", kind=CFGBlockKind.ENTRY, function_node_id=fn_id)
    then_b = ControlFlowBlock(id="b1", kind=CFGBlockKind.BLOCK, function_node_id=fn_id)
    else_b = ControlFlowBlock(id="b2", kind=CFGBlockKind.BLOCK, function_node_id=fn_id)
    join_b = ControlFlowBlock(id="b3", kind=CFGBlockKind.BLOCK, function_node_id=fn_id)
    exit_b = ControlFlowBlock(id="b4", kind=CFGBlockKind.EXIT, function_node_id=fn_id)

    edges = [
        ControlFlowEdge(source_block_id="b0", target_block_id="b1", kind=CFGEdgeKind.TRUE_BRANCH),
        ControlFlowEdge(source_block_id="b0", target_block_id="b2", kind=CFGEdgeKind.FALSE_BRANCH),
        ControlFlowEdge(source_block_id="b1", target_block_id="b3", kind=CFGEdgeKind.NORMAL),
        ControlFlowEdge(source_block_id="b2", target_block_id="b3", kind=CFGEdgeKind.NORMAL),
        ControlFlowEdge(source_block_id="b3", target_block_id="b4", kind=CFGEdgeKind.RETURN),
    ]
    cfg = ControlFlowGraph(
        id="cfg:fn:1",
        function_node_id=fn_id,
        entry_block_id="b0",
        exit_block_id="b4",
        blocks=[entry, then_b, else_b, join_b, exit_b],
        edges=edges,
    )

    # Expressions:
    # then: x = 1
    lit1 = Expression(
        id="e1",
        kind=ExprKind.LITERAL,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(1, 0),
        block_id="b1",
        attrs={"value_type": "integer"},
        defines_var="x",
    )
    # else: x = "a"
    lit2 = Expression(
        id="e2",
        kind=ExprKind.LITERAL,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(2, 0),
        block_id="b2",
        attrs={"value_type": "string"},
        defines_var="x",
    )
    # join: return x
    ret = Expression(
        id="e3",
        kind=ExprKind.NAME_LOAD,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(3, 0),
        block_id="b3",
        attrs={"var_name": "x", "is_return": True},
    )

    ir_doc = _IRDoc(nodes=[_Node(id=fn_id)])
    infer = LocalFlowTypeInferencer(config=LocalFlowConfig(max_iterations=5))
    infer.infer_and_annotate(ir_doc, [cfg], [lit1, lit2, ret])

    assert ir_doc.nodes[0].attrs["local_return_type"] in {"int | str", "str | int"}
    # return expression should also get inferred_type
    assert ret.inferred_type in {"int | str", "str | int"}


def test_ternary_expression_infers_union_type_and_assigns_to_defines_var():
    fn_id = "fn:2"
    b0 = ControlFlowBlock(id="b0", kind=CFGBlockKind.BLOCK, function_node_id=fn_id)
    cfg = ControlFlowGraph(
        id="cfg:fn:2",
        function_node_id=fn_id,
        entry_block_id="b0",
        exit_block_id="b0",
        blocks=[b0],
        edges=[],
    )

    # Build conditional expression tree:
    # x = (1 if c else "a")
    cond = Expression(
        id="c0",
        kind=ExprKind.CONDITIONAL,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(1, 0),
        block_id="b0",
        defines_var="x",
        attrs={"kind": "conditional_expression"},
    )
    true_lit = Expression(
        id="c1",
        kind=ExprKind.LITERAL,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(1, 1),
        block_id="b0",
        parent_expr_id="c0",
        attrs={"value_type": "integer"},
    )
    false_lit = Expression(
        id="c2",
        kind=ExprKind.LITERAL,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(1, 2),
        block_id="b0",
        parent_expr_id="c0",
        attrs={"value_type": "string"},
    )
    ret_x = Expression(
        id="c3",
        kind=ExprKind.NAME_LOAD,
        repo_id="r",
        file_path="f.py",
        function_fqn="f",
        span=_span(2, 0),
        block_id="b0",
        attrs={"var_name": "x", "is_return": True},
    )

    ir_doc = _IRDoc(nodes=[_Node(id=fn_id)])
    infer = LocalFlowTypeInferencer(config=LocalFlowConfig(max_iterations=2))
    infer.infer_and_annotate(ir_doc, [cfg], [cond, true_lit, false_lit, ret_x])

    assert cond.inferred_type in {"int | str", "str | int"}
    assert ret_x.inferred_type in {"int | str", "str | int"}
