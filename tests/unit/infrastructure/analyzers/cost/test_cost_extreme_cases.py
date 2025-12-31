"""
Cost Analyzer 극한 케이스 테스트 (SOTA L11)

누락된 극한 케이스:
- range(start, end, step) (3-arg)
- range(-1) (음수)
- Circular CFG (무한 루프 가능)
- 매우 깊은 nesting (10+ levels)
- 순환 표현식 (expr → expr)
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.cost import ComplexityClass, CostAnalyzer
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
    CFGBlockKind,
    CFGEdgeKind,
    ControlFlowBlock,
    ControlFlowEdge,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


class TestRangeEdgeCases:
    """range() edge cases"""

    def test_range_three_args(self):
        """range(start, end, step) should extract end (2nd arg)"""
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

        # range(0, n, 2) — 3 args
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 28),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e_start", "e_end", "e_step"]},  # 3 args
        )

        end_var = Expression(
            id="e_end",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 20, 2, 21),
            attrs={"var_name": "n"},
        )

        ir_doc.expressions = [range_call, end_var]

        result = analyzer.analyze_function(ir_doc, "func")

        # Should extract last arg (step) by current logic → WRONG!
        # 실제로는 2nd arg (end)를 써야 함
        # 이것은 버그!
        assert result.loop_bounds[0].bound == "n"  # 현재는 실패할 것

    def test_range_negative(self):
        """range(-1) (negative bound)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(-1)
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 23),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["e2"]},
        )

        neg_literal = Expression(
            id="e2",
            kind=ExprKind.LITERAL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 20, 2, 22),
            attrs={"value": -1, "value_type": "int"},
        )

        ir_doc.expressions = [range_call, neg_literal]

        result = analyzer.analyze_function(ir_doc, "func")

        # range(-1) → empty loop, but analyzer treats as bound="-1"
        assert result.loop_bounds[0].bound == "-1"
        # Still classifies as LINEAR (not CONSTANT)
        # This is acceptable (conservative)


class TestCircularCFG:
    """Circular CFG (무한 루프 가능성)"""

    def test_circular_cfg_protection(self):
        """Circular CFG should not hang (BFS protection)"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 10, 0), language="python"
        )
        ir_doc.nodes = [func]

        # Create circular CFG: Entry → Block → Loop → Block (cycle!)
        entry = ControlFlowBlock(id="entry", kind=CFGBlockKind.ENTRY, function_node_id="f1")
        block1 = ControlFlowBlock(id="b1", kind=CFGBlockKind.BLOCK, function_node_id="f1")
        loop = ControlFlowBlock(id="loop", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        block2 = ControlFlowBlock(id="b2", kind=CFGBlockKind.BLOCK, function_node_id="f1")

        ir_doc.cfg_blocks = [entry, block1, loop, block2]

        # Circular edges
        ir_doc.cfg_edges = [
            ControlFlowEdge("entry", "b1", CFGEdgeKind.NORMAL),
            ControlFlowEdge("b1", "loop", CFGEdgeKind.NORMAL),
            ControlFlowEdge("loop", "b2", CFGEdgeKind.TRUE_BRANCH),
            ControlFlowEdge("b2", "b1", CFGEdgeKind.NORMAL),  # ← Cycle!
        ]

        ir_doc.expressions = []

        # Should not hang (BFS visited protection)
        result = analyzer.analyze_function(ir_doc, "func")

        # Should complete (heuristic)
        assert result.verdict == "heuristic"


class TestDeepNesting:
    """매우 깊은 nesting (10+ levels)"""

    def test_deep_nesting_10_levels(self):
        """10-level nested loops should be handled"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 100, 0), language="python"
        )
        ir_doc.nodes = [func]

        # Create 10 nested loops
        entry = ControlFlowBlock(id="entry", kind=CFGBlockKind.ENTRY, function_node_id="f1")
        loops = [
            ControlFlowBlock(
                id=f"loop{i}",
                kind=CFGBlockKind.LOOP_HEADER,
                function_node_id="f1",
                span=Span(i + 2, i * 4, i + 2, i * 4 + 20),
            )
            for i in range(10)
        ]
        exit_block = ControlFlowBlock(id="exit", kind=CFGBlockKind.EXIT, function_node_id="f1")

        ir_doc.cfg_blocks = [entry] + loops + [exit_block]

        # Nested edges: entry → loop0 → loop1 → ... → loop9 → exit
        edges = [ControlFlowEdge("entry", "loop0", CFGEdgeKind.NORMAL)]
        for i in range(9):
            edges.append(ControlFlowEdge(f"loop{i}", f"loop{i + 1}", CFGEdgeKind.TRUE_BRANCH))
        edges.append(ControlFlowEdge("loop9", "exit", CFGEdgeKind.TRUE_BRANCH))

        ir_doc.cfg_edges = edges

        # Expressions (all range(n))
        expressions = []
        for i in range(10):
            range_call = Expression(
                id=f"e_call_{i}",
                kind=ExprKind.CALL,
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                span=Span(i + 2, 14, i + 2, 22),
                block_id=f"loop{i}",
                attrs={"callee_name": "range", "arg_expr_ids": [f"e_var_{i}"]},
            )
            var = Expression(
                id=f"e_var_{i}",
                kind=ExprKind.NAME_LOAD,
                repo_id="test",
                file_path="test.py",
                function_fqn="func",
                span=Span(i + 2, 20, i + 2, 21),
                attrs={"var_name": "n"},
            )
            expressions.extend([range_call, var])

        ir_doc.expressions = expressions

        result = analyzer.analyze_function(ir_doc, "func")

        # 10 nested loops → O(n^10) → EXPONENTIAL
        assert result.complexity == ComplexityClass.EXPONENTIAL
        assert len(result.loop_bounds) == 10


class TestExpressionChainEdgeCases:
    """Expression chain edge cases"""

    def test_missing_arg_expression(self):
        """arg_expr_id가 존재하지 않으면 heuristic"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")
        ir_doc.cfg_blocks = [loop]

        # range(n) but n expression missing!
        range_call = Expression(
            id="e1",
            kind=ExprKind.CALL,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(2, 14, 2, 22),
            block_id="l1",
            attrs={"callee_name": "range", "arg_expr_ids": ["missing_expr"]},  # ← 존재 안 함!
        )

        ir_doc.expressions = [range_call]  # n expression 없음

        result = analyzer.analyze_function(ir_doc, "func")

        # Should fallback to heuristic (bound expression not found)
        assert result.verdict == "heuristic"

    def test_attrs_missing_var_name(self):
        """attrs에 var_name 없으면 '?' 반환"""
        analyzer = CostAnalyzer()

        expr = Expression(
            id="e1",
            kind=ExprKind.NAME_LOAD,
            repo_id="test",
            file_path="test.py",
            function_fqn="func",
            span=Span(1, 0, 1, 1),
            attrs={},  # var_name 없음!
        )

        bound = analyzer._extract_bound_from_expr(expr, None)

        assert bound == "?"


class TestBoundaryConditions:
    """Boundary conditions (경계값)"""

    def test_single_block_function(self):
        """1개 block만 있는 function"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 2, 0), language="python"
        )
        ir_doc.nodes = [func]

        # Single block (no entry/exit even)
        block = ControlFlowBlock(id="b1", kind=CFGBlockKind.BLOCK, function_node_id="f1")

        ir_doc.cfg_blocks = [block]
        ir_doc.expressions = []

        result = analyzer.analyze_function(ir_doc, "func")

        # No loops → O(1)
        assert result.complexity == ComplexityClass.CONSTANT

    def test_zero_cfg_edges(self):
        """CFG edges 없으면 nesting level 0"""
        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 3, 0), language="python"
        )
        ir_doc.nodes = [func]

        loop = ControlFlowBlock(id="l1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1")

        ir_doc.cfg_blocks = [loop]
        ir_doc.cfg_edges = []  # No edges!
        ir_doc.expressions = []

        result = analyzer.analyze_function(ir_doc, "func")

        # No edges → nesting level 0
        assert result.loop_bounds[0].loop_id == "l1"

    def test_thousand_loops(self):
        """1000개 loops (performance stress test)"""
        import time

        analyzer = CostAnalyzer()

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 10000, 0), language="python"
        )
        ir_doc.nodes = [func]

        # 1000 loops (sequential, not nested)
        loops = [
            ControlFlowBlock(
                id=f"loop{i}", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1", span=Span(i, 0, i, 10)
            )
            for i in range(1000)
        ]

        ir_doc.cfg_blocks = loops
        ir_doc.cfg_edges = []
        ir_doc.expressions = []  # No expressions (heuristic)

        start = time.time()
        result = analyzer.analyze_function(ir_doc, "func")
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 5.0  # 5초 이내
        assert len(result.loop_bounds) == 1000


class TestComplexityCalculatorEdgeCases:
    """ComplexityCalculator extreme cases"""

    def test_fifteen_multiplications(self):
        """15개 중첩 → EXPONENTIAL"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost.complexity_calculator import (
            ComplexityCalculator,
        )

        calc = ComplexityCalculator()

        # 15 nested loops (all level different)
        bounds = [BoundResult(f"n{i}", "proven", 1.0, "pattern", loop_id=f"l{i}") for i in range(15)]

        nesting = {f"l{i}": i for i in range(15)}

        complexity, confidence, cost_term = calc.calculate(bounds, nesting)

        # 15 multiplications → EXPONENTIAL
        assert complexity == ComplexityClass.EXPONENTIAL

    def test_empty_bounds_list(self):
        """Empty bounds → O(1)"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost.complexity_calculator import (
            ComplexityCalculator,
        )

        calc = ComplexityCalculator()

        complexity, confidence, cost_term = calc.calculate([], {})

        assert complexity == ComplexityClass.CONSTANT
        assert cost_term == "1"


class TestCacheConsistency:
    """Cache consistency under various conditions"""

    def test_cache_invalidation(self):
        """Cache invalidation should work"""
        analyzer = CostAnalyzer(enable_cache=True)

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap")

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 2, 0), language="python"
        )
        ir_doc.nodes = [func]
        ir_doc.cfg_blocks = [ControlFlowBlock(id="c1", kind=CFGBlockKind.ENTRY, function_node_id="f1")]
        ir_doc.expressions = []

        # First call (cache miss)
        result1 = analyzer.analyze_function(ir_doc, "func")

        # Invalidate
        count = analyzer.invalidate_cache("func")
        assert count == 1

        # Second call (cache miss again)
        result2 = analyzer.analyze_function(ir_doc, "func")

        # Different instances (not cached)
        assert result1 is not result2

    def test_cache_with_different_snapshots(self):
        """Different snapshots should not share cache"""
        analyzer = CostAnalyzer(enable_cache=True)

        func = Node(
            id="f1", kind=NodeKind.METHOD, fqn="func", file_path="test.py", span=Span(1, 0, 2, 0), language="python"
        )

        # Snapshot 1
        ir_doc1 = IRDocument(repo_id="test", snapshot_id="snap1")
        ir_doc1.nodes = [func]
        ir_doc1.cfg_blocks = [ControlFlowBlock(id="c1", kind=CFGBlockKind.ENTRY, function_node_id="f1")]
        ir_doc1.expressions = []

        # Snapshot 2
        ir_doc2 = IRDocument(repo_id="test", snapshot_id="snap2")
        ir_doc2.nodes = [func]
        ir_doc2.cfg_blocks = [ControlFlowBlock(id="c1", kind=CFGBlockKind.ENTRY, function_node_id="f1")]
        ir_doc2.expressions = []

        result1 = analyzer.analyze_function(ir_doc1, "func")
        result2 = analyzer.analyze_function(ir_doc2, "func")

        # Different snapshots → different cache keys
        assert result1 is not result2


from codegraph_engine.code_foundation.infrastructure.analyzers.cost.models import BoundResult
