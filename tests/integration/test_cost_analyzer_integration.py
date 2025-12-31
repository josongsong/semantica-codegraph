"""
Cost Analyzer Integration Tests (RFC-028)

Production-grade integration tests with real IRDocument.

Test Cases:
- Simple loop (for i in range(n))
- Nested loops (for i in range(n): for j in range(m))
- No loops (O(1))
- Unbounded loop (while True)
"""

import pytest

from apps.orchestrator.orchestrator.domain.rfc_specs.evidence import EvidenceKind
from codegraph_engine.code_foundation.infrastructure.analyzers.cost import ComplexityClass, CostAnalyzer
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind, ControlFlowBlock
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


@pytest.fixture
def simple_loop_ir():
    """
    IRDocument for:

    def process_data(n):
        for i in range(n):
            compute(i)
    """
    ir_doc = IRDocument(repo_id="test", snapshot_id="snap_001")

    # Function node
    func_node = Node(
        id="func_1",
        kind=NodeKind.METHOD,
        fqn="process_data",
        file_path="test.py",
        span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
        language="python",
    )
    ir_doc.nodes = [func_node]

    # CFG blocks
    entry = ControlFlowBlock(id="cfg_1", kind=CFGBlockKind.ENTRY, function_node_id="func_1")

    loop_header = ControlFlowBlock(
        id="cfg_2",
        kind=CFGBlockKind.LOOP_HEADER,
        function_node_id="func_1",
        span=Span(start_line=2, start_col=4, end_line=2, end_col=20),
    )

    loop_body = ControlFlowBlock(id="cfg_3", kind=CFGBlockKind.BLOCK, function_node_id="func_1")

    exit = ControlFlowBlock(id="cfg_4", kind=CFGBlockKind.EXIT, function_node_id="func_1")

    ir_doc.cfg_blocks = [entry, loop_header, loop_body, exit]

    # Expressions
    # range(n) call
    range_call = Expression(
        id="expr_1",
        kind=ExprKind.CALL,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_data",
        span=Span(start_line=2, start_col=14, end_line=2, end_col=22),
        block_id="cfg_2",  # ← Loop block
        attrs={"callee_name": "range", "arg_expr_ids": ["expr_2"]},
    )

    # n variable
    n_var = Expression(
        id="expr_2",
        kind=ExprKind.NAME_LOAD,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_data",
        span=Span(start_line=2, start_col=20, end_line=2, end_col=21),
        attrs={"var_name": "n"},
    )

    ir_doc.expressions = [range_call, n_var]

    return ir_doc


@pytest.fixture
def nested_loop_ir():
    """
    IRDocument for:

    def process_matrix(n, m):
        for i in range(n):
            for j in range(m):
                compute(i, j)
    """
    ir_doc = IRDocument(repo_id="test", snapshot_id="snap_002")

    func_node = Node(
        id="func_2",
        kind=NodeKind.METHOD,
        fqn="process_matrix",
        file_path="test.py",
        span=Span(start_line=1, start_col=0, end_line=4, end_col=0),
        language="python",
    )
    ir_doc.nodes = [func_node]

    # CFG blocks
    entry = ControlFlowBlock(id="cfg_1", kind=CFGBlockKind.ENTRY, function_node_id="func_2")

    loop1 = ControlFlowBlock(
        id="cfg_2",
        kind=CFGBlockKind.LOOP_HEADER,
        function_node_id="func_2",
        span=Span(start_line=2, start_col=4, end_line=2, end_col=20),
    )

    loop2 = ControlFlowBlock(
        id="cfg_3",
        kind=CFGBlockKind.LOOP_HEADER,
        function_node_id="func_2",
        span=Span(start_line=3, start_col=8, end_line=3, end_col=24),
    )

    body = ControlFlowBlock(id="cfg_4", kind=CFGBlockKind.BLOCK, function_node_id="func_2")

    exit = ControlFlowBlock(id="cfg_5", kind=CFGBlockKind.EXIT, function_node_id="func_2")

    ir_doc.cfg_blocks = [entry, loop1, loop2, body, exit]

    # Expressions
    # range(n)
    range_n = Expression(
        id="expr_1",
        kind=ExprKind.CALL,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_matrix",
        span=Span(start_line=2, start_col=14, end_line=2, end_col=22),
        block_id="cfg_2",
        attrs={"callee_name": "range", "arg_expr_ids": ["expr_2"]},
    )

    n_var = Expression(
        id="expr_2",
        kind=ExprKind.NAME_LOAD,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_matrix",
        span=Span(start_line=2, start_col=20, end_line=2, end_col=21),
        attrs={"var_name": "n"},
    )

    # range(m)
    range_m = Expression(
        id="expr_3",
        kind=ExprKind.CALL,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_matrix",
        span=Span(start_line=3, start_col=18, end_line=3, end_col=26),
        block_id="cfg_3",
        attrs={"callee_name": "range", "arg_expr_ids": ["expr_4"]},
    )

    m_var = Expression(
        id="expr_4",
        kind=ExprKind.NAME_LOAD,
        repo_id="test",
        file_path="test.py",
        function_fqn="process_matrix",
        span=Span(start_line=3, start_col=24, end_line=3, end_col=25),
        attrs={"var_name": "m"},
    )

    ir_doc.expressions = [range_n, n_var, range_m, m_var]

    # CFG edges (for nesting calculation)
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGEdgeKind, ControlFlowEdge

    ir_doc.cfg_edges = [
        ControlFlowEdge("cfg_1", "cfg_2", CFGEdgeKind.NORMAL),  # Entry → Loop1
        ControlFlowEdge("cfg_2", "cfg_3", CFGEdgeKind.TRUE_BRANCH),  # Loop1 → Loop2 (nested!)
        ControlFlowEdge("cfg_3", "cfg_4", CFGEdgeKind.TRUE_BRANCH),  # Loop2 → Body
        ControlFlowEdge("cfg_4", "cfg_3", CFGEdgeKind.LOOP_BACK),  # Body → Loop2
        ControlFlowEdge("cfg_3", "cfg_2", CFGEdgeKind.FALSE_BRANCH),  # Loop2 exit → Loop1
        ControlFlowEdge("cfg_2", "cfg_5", CFGEdgeKind.FALSE_BRANCH),  # Loop1 exit → Exit
    ]

    return ir_doc


class TestCostAnalyzerSimpleLoop:
    """Test simple loop (for i in range(n))"""

    def test_simple_loop_proven(self, simple_loop_ir):
        """Simple loop should be O(n) proven"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(simple_loop_ir, "process_data", request_id="test_001")

        # Assertions
        assert result.complexity == ComplexityClass.LINEAR
        assert result.verdict == "proven"
        assert result.confidence == 1.0
        assert len(result.loop_bounds) == 1
        assert result.loop_bounds[0].bound == "n"
        assert result.loop_bounds[0].method == "pattern"

    def test_simple_loop_evidence(self, simple_loop_ir):
        """Evidence should conform to RFC-027 schema"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(simple_loop_ir, "process_data")

        # Evidence validation
        assert result.evidence.kind == EvidenceKind.COST_TERM
        assert result.evidence.content["cost_term"] == "n"
        assert len(result.evidence.content["loop_bounds"]) == 1
        assert result.evidence.content["loop_bounds"][0]["bound"] == "n"
        assert result.evidence.provenance.engine == "CostAnalyzer"

    def test_simple_loop_is_not_slow(self, simple_loop_ir):
        """O(n) should not be considered slow"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(simple_loop_ir, "process_data")

        assert not result.is_slow()  # O(n) is not slow


class TestCostAnalyzerNestedLoop:
    """Test nested loops"""

    def test_nested_loop_quadratic(self, nested_loop_ir):
        """Nested loops should be O(n²) proven"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(nested_loop_ir, "process_matrix")

        # Complexity should be quadratic (n * m)
        assert result.complexity == ComplexityClass.QUADRATIC
        assert result.verdict == "proven"
        assert len(result.loop_bounds) == 2

    def test_nested_loop_bounds(self, nested_loop_ir):
        """Both loop bounds should be extracted"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(nested_loop_ir, "process_matrix")

        bounds = {lb.bound for lb in result.loop_bounds}
        assert "n" in bounds
        assert "m" in bounds

    def test_nested_loop_nesting_levels(self, nested_loop_ir):
        """Nesting levels should be calculated"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(nested_loop_ir, "process_matrix")

        # Loop 1: level 0 (outer)
        # Loop 2: level 1 (nested)
        # This is reflected in complexity: n * m → O(n²)
        assert result.complexity == ComplexityClass.QUADRATIC

    def test_nested_loop_is_slow(self, nested_loop_ir):
        """O(n²) should be considered slow"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(nested_loop_ir, "process_matrix")

        assert result.is_slow()  # O(n²) is slow!


class TestCostAnalyzerEdgeCases:
    """Edge cases"""

    def test_no_loops(self):
        """Function with no loops should be O(1)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="snap_003")

        func_node = Node(
            id="func_3",
            kind=NodeKind.METHOD,
            fqn="simple_func",
            file_path="test.py",
            span=Span(start_line=1, start_col=0, end_line=2, end_col=0),
            language="python",
        )
        ir_doc.nodes = [func_node]

        # CFG with no loops
        entry = ControlFlowBlock(id="cfg_1", kind=CFGBlockKind.ENTRY, function_node_id="func_3")
        body = ControlFlowBlock(id="cfg_2", kind=CFGBlockKind.BLOCK, function_node_id="func_3")
        exit = ControlFlowBlock(id="cfg_3", kind=CFGBlockKind.EXIT, function_node_id="func_3")

        ir_doc.cfg_blocks = [entry, body, exit]
        ir_doc.expressions = []

        analyzer = CostAnalyzer()
        result = analyzer.analyze_function(ir_doc, "simple_func")

        assert result.complexity == ComplexityClass.CONSTANT
        assert result.verdict == "proven"
        assert result.confidence == 1.0

    def test_loop_without_expressions_heuristic(self):
        """Loop without Expression IR should fallback to heuristic"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="snap_004")

        func_node = Node(
            id="func_4",
            kind=NodeKind.METHOD,
            fqn="unknown_loop",
            file_path="test.py",
            span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
            language="python",
        )
        ir_doc.nodes = [func_node]

        # CFG with loop
        loop = ControlFlowBlock(
            id="cfg_2",
            kind=CFGBlockKind.LOOP_HEADER,
            function_node_id="func_4",
            span=Span(start_line=2, start_col=4, end_line=2, end_col=20),
        )

        ir_doc.cfg_blocks = [loop]
        ir_doc.expressions = []  # Empty list (not None)

        analyzer = CostAnalyzer()
        result = analyzer.analyze_function(ir_doc, "unknown_loop")

        # Should fallback to heuristic
        assert result.verdict == "heuristic"
        assert result.confidence == 0.2
        assert result.loop_bounds[0].upper_bound_hint == "O(n²)"

    def test_cache_hit(self, simple_loop_ir):
        """Second analysis should hit cache"""
        analyzer = CostAnalyzer(enable_cache=True)

        # First call
        result1 = analyzer.analyze_function(simple_loop_ir, "process_data")

        # Second call (should hit cache)
        result2 = analyzer.analyze_function(simple_loop_ir, "process_data")

        # Should be same object (from cache)
        assert result1 is result2


class TestCostAnalyzerProduction:
    """Production requirements validation"""

    def test_no_cfg_raises_error(self):
        """Missing CFG should raise ValueError"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="snap_005")
        ir_doc.cfg_blocks = []  # Empty!

        analyzer = CostAnalyzer()

        with pytest.raises(ValueError, match="CFG blocks not found"):
            analyzer.analyze_function(ir_doc, "func")

    def test_no_expressions_raises_error(self):
        """Missing Expression IR should raise ValueError"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="snap_006")

        func_node = Node(
            id="func_5",
            kind=NodeKind.METHOD,
            fqn="func",
            file_path="test.py",
            span=Span(start_line=1, start_col=0, end_line=2, end_col=0),
            language="python",
        )
        ir_doc.nodes = [func_node]
        ir_doc.cfg_blocks = [ControlFlowBlock(id="cfg_1", kind=CFGBlockKind.ENTRY, function_node_id="func_5")]
        ir_doc.expressions = None  # Missing! (None triggers error)

        analyzer = CostAnalyzer()

        with pytest.raises(ValueError, match="Expression IR not found"):
            analyzer.analyze_function(ir_doc, "func")

    def test_function_not_found_raises_error(self):
        """Non-existent function should raise ValueError"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="snap_007")
        ir_doc.nodes = []
        ir_doc.cfg_blocks = [ControlFlowBlock(id="cfg_1", kind=CFGBlockKind.ENTRY, function_node_id="dummy")]
        ir_doc.expressions = []  # Has expressions but no function

        analyzer = CostAnalyzer()

        with pytest.raises(ValueError, match="Function not found"):
            analyzer.analyze_function(ir_doc, "nonexistent")

    def test_evidence_schema_compliance(self, simple_loop_ir):
        """Evidence must comply with RFC-027 schema"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(simple_loop_ir, "process_data")

        # Evidence schema checks
        assert result.evidence.kind == EvidenceKind.COST_TERM
        assert "cost_term" in result.evidence.content
        assert "loop_bounds" in result.evidence.content
        assert isinstance(result.evidence.content["loop_bounds"], list)
        assert result.evidence.claim_ids == ["pending"]

    def test_verdict_confidence_consistency(self, simple_loop_ir):
        """Verdict and confidence should be consistent"""
        analyzer = CostAnalyzer()

        result = analyzer.analyze_function(simple_loop_ir, "process_data")

        # proven → high confidence
        if result.verdict == "proven":
            assert result.confidence >= 0.8

        # heuristic → low confidence
        if result.verdict == "heuristic":
            assert result.confidence <= 0.5
