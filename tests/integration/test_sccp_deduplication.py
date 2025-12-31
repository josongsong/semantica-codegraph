"""
RFC-021 Day 1: SCCP Deduplication Tests

L11 SOTA Integration Testing:
- DeepSecurityAnalyzer + QueryEngine 중복 실행 방지
- IRDocument.meta 공유 검증
- Fallback 동작 검증
- 성능 향상 검증

Critical:
- SCCP가 1번만 실행되는지
- 재사용 로그 확인
- Fallback 동작 확인
"""

import pytest

from codegraph_engine.code_foundation.domain.query.factories import E, Q
from codegraph_engine.code_foundation.infrastructure.analyzers.deep_security_analyzer import (
    AnalysisMode,
    DeepSecurityAnalyzer,
)
from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot, VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind, ControlFlowBlock

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def ir_doc_with_cfg_dfg():
    """CFG와 DFG가 있는 IRDocument (SCCP 실행 가능)"""
    ir_doc = IRDocument(repo_id="test", snapshot_id="dedup_test")
    span = Span(start_line=1, start_col=0, end_line=1, end_col=10)

    # CFG
    b1 = ControlFlowBlock(id="b1", kind=CFGBlockKind.ENTRY, function_node_id="f1")
    b2 = ControlFlowBlock(id="b2", kind=CFGBlockKind.BLOCK, function_node_id="f1")
    ir_doc.cfg_blocks = [b1, b2]

    # DFG
    var1 = VariableEntity(
        id="v1", repo_id="test", file_path="test.py", function_fqn="test.func", name="x", kind="local"
    )
    var2 = VariableEntity(
        id="v2", repo_id="test", file_path="test.py", function_fqn="test.func", name="y", kind="local"
    )
    ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1, var2])

    # Nodes
    n1 = Node(
        id="n1",
        kind=NodeKind.VARIABLE,
        fqn="test.func.x",
        name="x",
        file_path="test.py",
        span=span,
        language="python",
        attrs={"block_id": "b1"},
    )
    n2 = Node(
        id="n2",
        kind=NodeKind.VARIABLE,
        fqn="test.func.y",
        name="y",
        file_path="test.py",
        span=span,
        language="python",
        attrs={"block_id": "b2"},
    )
    ir_doc.nodes = [n1, n2]

    # Edge
    e1 = Edge(id="e1", kind=EdgeKind.READS, source_id="n1", target_id="n2")
    ir_doc.edges = [e1]

    ir_doc.build_indexes()
    return ir_doc


# ============================================================
# Deduplication Tests
# ============================================================


class TestSCCPDeduplication:
    """SCCP 중복 실행 방지 검증"""

    def test_query_engine_first_then_deep_security_reuses(self, ir_doc_with_cfg_dfg):
        """
        Critical: QueryEngine 먼저 실행 → DeepSecurityAnalyzer 재사용

        Scenario:
        1. QueryEngine.execute_flow() → SCCP 실행 → meta 저장
        2. DeepSecurityAnalyzer.analyze() → meta에서 재사용

        Expected:
        - SCCP 1번만 실행
        - DeepSecurityAnalyzer는 재사용 로그
        """
        # Given
        engine = QueryEngine(ir_doc_with_cfg_dfg)
        analyzer = DeepSecurityAnalyzer(ir_doc_with_cfg_dfg)

        # When: QueryEngine 먼저 실행
        expr = (Q.Var("x") >> Q.Var("y")).via(E.DFG)
        engine.execute_flow(expr, mode="realtime")

        # Then: SCCP 결과가 meta에 저장됨
        assert "constant_propagation" in ir_doc_with_cfg_dfg.meta
        sccp_from_query = ir_doc_with_cfg_dfg.meta["constant_propagation"]

        # When: DeepSecurityAnalyzer 실행
        result = analyzer.analyze(mode=AnalysisMode.REALTIME)

        # Then: 같은 SCCP 결과 재사용
        sccp_from_deep = ir_doc_with_cfg_dfg.meta["constant_propagation"]
        assert sccp_from_query is sccp_from_deep, "Should reuse same SCCP instance"

        # Analysis result is valid
        assert result is not None
        assert isinstance(result.issues, list)

    def test_deep_security_standalone_executes_sccp(self, ir_doc_with_cfg_dfg):
        """
        Critical: DeepSecurityAnalyzer 단독 사용 시 SCCP 직접 실행 (Fallback)

        Scenario:
        - QueryEngine 사용 안 함
        - DeepSecurityAnalyzer만 사용

        Expected:
        - SCCP 직접 실행
        - meta에 저장
        """
        # Given: No QueryEngine (DeepSecurityAnalyzer only)
        analyzer = DeepSecurityAnalyzer(ir_doc_with_cfg_dfg)

        # meta에 SCCP 없음
        assert "constant_propagation" not in ir_doc_with_cfg_dfg.meta

        # When: DeepSecurityAnalyzer 실행
        result = analyzer.analyze(mode=AnalysisMode.REALTIME)

        # Then: SCCP 실행되어 meta에 저장됨
        assert "constant_propagation" in ir_doc_with_cfg_dfg.meta
        sccp_result = ir_doc_with_cfg_dfg.meta["constant_propagation"]
        assert sccp_result is not None
        assert sccp_result.constants_found >= 0

        # Analysis result is valid
        assert result is not None

    def test_sccp_result_shared_between_components(self, ir_doc_with_cfg_dfg):
        """
        Critical: SCCP 결과가 컴포넌트 간 공유되는지 검증

        Verification:
        - QueryEngine → meta 저장
        - DeepSecurityAnalyzer → meta 재사용
        - Same instance (not re-executed)
        """
        # Given
        engine = QueryEngine(ir_doc_with_cfg_dfg)
        analyzer = DeepSecurityAnalyzer(ir_doc_with_cfg_dfg)

        # When: QueryEngine 먼저 실행
        expr = (Q.Var("x") >> Q.Var("y")).via(E.DFG)
        engine.execute_flow(expr, mode="realtime")

        # Get SCCP result from QueryEngine
        sccp_from_query = engine._sccp_result
        sccp_id_from_query = id(sccp_from_query)

        # When: DeepSecurityAnalyzer 실행
        analyzer.analyze(mode=AnalysisMode.REALTIME)

        # Get SCCP result from meta
        sccp_from_meta = ir_doc_with_cfg_dfg.meta["constant_propagation"]
        sccp_id_from_meta = id(sccp_from_meta)

        # Then: Same instance (shared, not duplicated)
        assert sccp_id_from_query == sccp_id_from_meta, (
            f"SCCP should be shared! QueryEngine ID: {sccp_id_from_query}, Meta ID: {sccp_id_from_meta}"
        )


class TestSCCPFallback:
    """SCCP Fallback 동작 검증"""

    def test_fallback_when_meta_empty(self, ir_doc_with_cfg_dfg):
        """
        Edge: meta가 비어있을 때 Fallback 동작
        """
        # Given: Empty meta
        ir_doc_with_cfg_dfg.meta.clear()
        analyzer = DeepSecurityAnalyzer(ir_doc_with_cfg_dfg)

        # When
        result = analyzer.analyze(mode=AnalysisMode.REALTIME)

        # Then: SCCP executed (fallback)
        assert "constant_propagation" in ir_doc_with_cfg_dfg.meta
        assert result is not None

    def test_fallback_when_meta_has_other_keys(self, ir_doc_with_cfg_dfg):
        """
        Edge: meta에 다른 키만 있을 때 Fallback
        """
        # Given: meta with other keys
        ir_doc_with_cfg_dfg.meta["other_analysis"] = {"foo": "bar"}
        # No "constant_propagation"

        analyzer = DeepSecurityAnalyzer(ir_doc_with_cfg_dfg)

        # When
        result = analyzer.analyze(mode=AnalysisMode.REALTIME)

        # Then: SCCP executed (fallback)
        assert "constant_propagation" in ir_doc_with_cfg_dfg.meta
        assert result is not None


class TestSCCPPerformanceImprovement:
    """SCCP 중복 제거로 인한 성능 향상 검증"""

    def test_deduplication_saves_time(self, ir_doc_with_cfg_dfg):
        """
        Performance: SCCP 재사용으로 시간 절약

        Measurement:
        - Scenario 1: DeepSecurity only (SCCP 1번)
        - Scenario 2: QueryEngine + DeepSecurity (SCCP 재사용)

        Expected:
        - Scenario 2가 더 빠름 (SCCP 중복 제거)
        """
        import time

        # Scenario 1: DeepSecurity only (fresh IR)
        ir_doc1 = self._create_fresh_ir()
        analyzer1 = DeepSecurityAnalyzer(ir_doc1)

        start1 = time.perf_counter()
        analyzer1.analyze(mode=AnalysisMode.REALTIME)
        time1 = (time.perf_counter() - start1) * 1000

        # Scenario 2: QueryEngine + DeepSecurity (reuse)
        ir_doc2 = self._create_fresh_ir()
        engine2 = QueryEngine(ir_doc2)
        analyzer2 = DeepSecurityAnalyzer(ir_doc2)

        # QueryEngine first (SCCP executed)
        expr = (Q.Var("x") >> Q.Var("y")).via(E.DFG)
        engine2.execute_flow(expr, mode="realtime")

        # DeepSecurity second (SCCP reused)
        start2 = time.perf_counter()
        analyzer2.analyze(mode=AnalysisMode.REALTIME)
        time2 = (time.perf_counter() - start2) * 1000

        # Then: Scenario 2 should be faster or similar
        # (SCCP already executed, so DeepSecurity skips it)
        # Note: Difference might be small for tiny graphs
        assert time2 <= time1 * 1.5, f"Deduplication should not be slower: time1={time1:.2f}ms, time2={time2:.2f}ms"

    def _create_fresh_ir(self):
        """Helper: Fresh IRDocument for each scenario"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="fresh")
        span = Span(start_line=1, start_col=0, end_line=1, end_col=10)

        b1 = ControlFlowBlock(id="b1", kind=CFGBlockKind.ENTRY, function_node_id="f1")
        ir_doc.cfg_blocks = [b1]

        var1 = VariableEntity(
            id="v1", repo_id="test", file_path="test.py", function_fqn="test.func", name="x", kind="local"
        )
        ir_doc.dfg_snapshot = DfgSnapshot(variables=[var1])

        n1 = Node(
            id="n1",
            kind=NodeKind.VARIABLE,
            fqn="test.func.x",
            name="x",
            file_path="test.py",
            span=span,
            language="python",
            attrs={"block_id": "b1"},
        )
        ir_doc.nodes = [n1]

        ir_doc.build_indexes()
        return ir_doc
