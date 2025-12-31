"""
Cost Analyzer Unit Tests (RFC-028)

Helper 메서드 단위 테스트.

Test Cases:
- _extract_bound_from_expr (모든 ExprKind)
- _determine_verdict (worst case)
- _find_hotspots
- Edge cases
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer
from codegraph_engine.code_foundation.infrastructure.analyzers.cost.models import BoundResult, ComplexityClass
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind, ControlFlowBlock
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


class TestExtractBoundFromExpr:
    """_extract_bound_from_expr unit tests"""

    def test_name_load(self):
        """NAME_LOAD should extract var_name"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 1),
            attrs={"var_name": "n"},
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert bound == "n"

    def test_literal(self):
        """LITERAL should extract value"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 2),
            attrs={"value": 10, "value_type": "int"},
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert bound == "10"

    def test_call_len(self):
        """CALL (len) should extract function name"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 8),
            attrs={"callee_name": "len", "arg_expr_ids": ["e2"]},
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert bound == "len(...)"

    def test_bin_op(self):
        """BIN_OP should return operator-based name"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.BIN_OP,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 5),
            attrs={"operator": "+"},
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert "+" in bound

    def test_unknown_kind(self):
        """Unknown ExprKind should return '?'"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.LAMBDA,  # Not handled
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 10),
            attrs={},
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert bound == "?"


class TestDetermineVerdict:
    """_determine_verdict unit tests"""

    def test_all_proven(self):
        """All proven → proven"""
        analyzer = CostAnalyzer()

        bounds = [
            BoundResult("n", "proven", 1.0, "pattern"),
            BoundResult("m", "proven", 1.0, "pattern"),
        ]

        verdict = analyzer._determine_verdict(bounds)

        assert verdict == "proven"

    def test_one_heuristic(self):
        """One heuristic → heuristic (worst case)"""
        analyzer = CostAnalyzer()

        bounds = [
            BoundResult("n", "proven", 1.0, "pattern"),
            BoundResult("unknown", "heuristic", 0.2, "heuristic"),
        ]

        verdict = analyzer._determine_verdict(bounds)

        assert verdict == "heuristic"

    def test_one_likely(self):
        """One likely → likely"""
        analyzer = CostAnalyzer()

        bounds = [
            BoundResult("n", "proven", 1.0, "pattern"),
            BoundResult("m", "likely", 0.8, "widening"),
        ]

        verdict = analyzer._determine_verdict(bounds)

        assert verdict == "likely"


class TestFindHotspots:
    """_find_hotspots unit tests"""

    def test_hotspots_from_loops(self):
        """Hotspots should extract loop locations"""
        analyzer = CostAnalyzer()

        loops = [
            ControlFlowBlock(
                id="l1",
                kind=CFGBlockKind.LOOP_HEADER,
                function_node_id="f1",
                span=Span(10, 4, 10, 20),
            ),
            ControlFlowBlock(
                id="l2",
                kind=CFGBlockKind.LOOP_HEADER,
                function_node_id="f1",
                span=Span(15, 8, 15, 24),
            ),
        ]

        hotspots = analyzer._find_hotspots(loops)

        assert len(hotspots) == 2
        assert hotspots[0]["line"] == 10
        assert hotspots[1]["line"] == 15


class TestEdgeCases:
    """Edge cases and corner cases"""

    def test_empty_expression_list(self):
        """Empty expressions list should return heuristic"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="func",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1", span=Span(2, 4, 2, 20))

        ir_doc.cfg_blocks = [loop]
        ir_doc.expressions = []  # Empty!

        result = analyzer.analyze_function(ir_doc, "func")

        # No expressions → heuristic
        assert result.verdict == "heuristic"

    def test_loop_without_range_call(self):
        """Loop without range() call should return heuristic"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="func",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1", span=Span(2, 4, 2, 20))

        ir_doc.cfg_blocks = [loop]

        # Expression but not range()
        expr = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 22),
            block_id="l1",
            attrs={"callee_name": "iter", "arg_expr_ids": []},  # Not range!
        )

        ir_doc.expressions = [expr]

        result = analyzer.analyze_function(ir_doc, "func")

        # Not range() → heuristic
        assert result.verdict == "heuristic"

    def test_range_zero(self):
        """range(0) should be handled (edge case)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="func",
            file_path="test.py",
            span=Span(1, 0, 3, 0),
            language="python",
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")

        ir_doc.cfg_blocks = [loop]

        # range(0)
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 22),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e2"]},
        )

        zero_literal = Expression(
            id="e2",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 20, 2, 21),
            attrs={"value": 0, "value_type": "int"},
        )

        ir_doc.expressions = [range_call, zero_literal]

        result = analyzer.analyze_function(ir_doc, "func")

        # range(0) → bound="0", still O(n) classification
        # (ComplexityCalculator treats "0" as constant, but analyzer classifies as LINEAR)
        assert result.loop_bounds[0].bound == "0"
        assert result.verdict == "proven"

    def test_cache_isolation(self):
        """Cache should be isolated per instance"""
        analyzer1 = CostAnalyzer(enable_cache=True)
        analyzer2 = CostAnalyzer(enable_cache=True)

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="func",
            file_path="test.py",
            span=Span(1, 0, 2, 0),
            language="python",
        )
        ir_doc.nodes = [func]
        ir_doc.cfg_blocks = [ControlFlowBlock(id="c1", kind=CFGBlockKind.ENTRY, function_node_id="f1")]
        ir_doc.expressions = []

        # Analyzer1 caches
        result1 = analyzer1.analyze_function(ir_doc, "func")

        # Analyzer2 should not see analyzer1's cache
        assert "snap:func" not in (analyzer2._cache or {})


class TestPerformance:
    """Performance tests"""

    def test_large_cfg_performance(self):
        """Large CFG should complete in reasonable time"""
        import time

        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1",
            kind=NodeKind.METHOD,
            fqn="large_func",
            file_path="test.py",
            span=Span(1, 0, 1000, 0),
            language="python",
        )
        ir_doc.nodes = [func]

        # 100 blocks
        cfg_blocks = [ControlFlowBlock(id=f"b{i}", kind=CFGBlockKind.BLOCK, function_node_id="f1") for i in range(100)]

        # 10 loops
        for i in range(10):
            cfg_blocks.append(
                ControlFlowBlock(
                    id=f"loop{i}",
                    kind=CFGBlockKind.LOOP_HEADER,
                    function_node_id="f1",
                    span=Span(i * 10, 0, i * 10, 10),
                )
            )

        ir_doc.cfg_blocks = cfg_blocks
        ir_doc.expressions = []  # Minimal

        start = time.time()
        result = analyzer.analyze_function(ir_doc, "large_func")
        elapsed = time.time() - start

        # Should complete in < 100ms (target)
        assert elapsed < 1.0  # Relaxed for CI (target 0.1s)
        assert result.verdict == "heuristic"  # No expressions → heuristic
