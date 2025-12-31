"""
Cost Analyzer SOTA Enhancements Tests

제약사항 해결:
1. Collection iterator (for item in arr)
2. Step 지원 (range(0, n, 2))
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.cost import ComplexityClass, CostAnalyzer
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind, ControlFlowBlock
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


class TestCollectionIterator:
    """Collection iterator support (SOTA)"""

    def test_for_item_in_collection(self):
        """for item in arr → len(arr)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="process",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")

        ir_doc.cfg_blocks = [loop]

        # Collection iterator (NAME_LOAD)
        arr_var = Expression(
            id="e1",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="process",
            span=Span(2, 14, 2, 17),
            block_id="l1",
            attrs={"var_name": "arr"},
        )

        ir_doc.expressions = [arr_var]

        result = analyzer.analyze_function(ir_doc, "process")

        # Should extract len(arr)
        assert result.loop_bounds[0].bound == "len(arr)"
        assert result.loop_bounds[0].verdict == "likely"  # Approximation
        assert result.complexity == ComplexityClass.LINEAR

    def test_for_item_in_method_call(self):
        """for item in get_items() → len(...)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="process", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # Method call iterator
        call_expr = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="process",
            span=Span(2, 14, 2, 26),
            block_id="l1",
            attrs={"callee_name": "get_items", "arg_expr_ids": []},
        )

        ir_doc.expressions = [call_expr]

        result = analyzer.analyze_function(ir_doc, "process")

        # Call은 range()가 아니므로 likely fallback
        assert result.loop_bounds[0].verdict in ("likely", "heuristic")


class TestRangeStep:
    """range() with step (SOTA)"""

    def test_range_with_constant_step(self):
        """range(0, n, 2) → n/2"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(0, n, 2)
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 28),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e_start", "e_end", "e_step"]},
        )

        start = Expression(
            id="e_start",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 20, 2, 21),
            attrs={"value": 0},
        )

        end = Expression(
            id="e_end",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 23, 2, 24),
            attrs={"var_name": "n"},
        )

        step = Expression(
            id="e_step",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 26, 2, 27),
            attrs={"value": 2},
        )

        ir_doc.expressions = [range_call, start, end, step]

        result = analyzer.analyze_function(ir_doc, "func")

        # Should extract n/2
        assert result.loop_bounds[0].bound == "(n/2)"
        assert result.loop_bounds[0].verdict == "proven"
        assert result.loop_bounds[0].confidence == 0.95

    def test_range_with_step_1(self):
        """range(0, n, 1) → n (step=1 무시)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(0, n, 1) — step=1은 의미 없음
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 28),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e_start", "e_end", "e_step"]},
        )

        end = Expression(
            id="e_end",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 23, 2, 24),
            attrs={"var_name": "n"},
        )

        step = Expression(
            id="e_step",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 26, 2, 27),
            attrs={"value": 1},
        )  # step=1

        ir_doc.expressions = [range_call, end, step]

        result = analyzer.analyze_function(ir_doc, "func")

        # step=1 → just n (no division)
        assert result.loop_bounds[0].bound == "n"

    def test_range_with_variable_step(self):
        """range(0, n, step_var) → n (step 변수면 무시)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(0, n, step_var)
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 35),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e_start", "e_end", "e_step"]},
        )

        end = Expression(
            id="e_end",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 23, 2, 24),
            attrs={"var_name": "n"},
        )

        step = Expression(
            id="e_step",
            kind=ExprKind.NAME_LOAD,  # Variable step!
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 26, 2, 34),
            attrs={"var_name": "step_var"},
        )

        ir_doc.expressions = [range_call, end, step]

        result = analyzer.analyze_function(ir_doc, "func")

        # Variable step → ignore, just n
        assert result.loop_bounds[0].bound == "n"
        assert result.loop_bounds[0].verdict == "proven"


class TestComplexIterators:
    """Complex iterator patterns"""

    def test_len_call_iterator(self):
        """for i in range(len(arr)) → len(arr)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(len(arr))
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 29),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e_len"]},
        )

        len_call = Expression(
            id="e_len",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 20, 2, 28),
            attrs={"callee_name": "len", "arg_expr_ids": ["e_arr"]},
        )

        ir_doc.expressions = [range_call, len_call]

        result = analyzer.analyze_function(ir_doc, "func")

        # Should extract len(...)
        assert result.loop_bounds[0].bound == "len(...)"
        assert result.complexity == ComplexityClass.LINEAR
