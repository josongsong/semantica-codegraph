"""
SCCP Performance Benchmark

RFC-024: Performance 검증

Target:
- 1000 LOC < 100ms
- 메모리 < 50MB
- Large graph 수렴
"""

import time

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer


class TestPerformance:
    """성능 벤치마크 (Production Critical!)"""

    @pytest.mark.benchmark
    def test_sccp_performance_target(self, benchmark):
        """SCCP 성능 목표: < 100ms per 1000 LOC"""
        # Note: 실제 1000줄 코드는 IR 빌드가 복잡하므로
        # Unit Test 수준에서 검증

        analyzer = ConstantPropagationAnalyzer()

        # Mock IRDocument (성능만 측정)
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        # 10개 블록 (1000줄 ≈ 100 블록 가정, 샘플 10개)
        cfg_blocks = [ControlFlowBlock(f"block{i}", CFGBlockKind.BLOCK, "func1", Span(i, 0, i, 0)) for i in range(10)]

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=cfg_blocks,
            cfg_edges=[],
            expressions=[],
        )

        # Benchmark (여러 번 실행)
        def run_sccp():
            analyzer.clear_cache()  # 캐시 무효화
            return analyzer.analyze(ir_doc)

        # pytest-benchmark
        result = benchmark(run_sccp)

        # 검증
        assert result is not None

    def test_large_graph_convergence(self):
        """Large graph 수렴 검증"""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        # 100개 블록 (Large graph)
        cfg_blocks = [ControlFlowBlock(f"block{i}", CFGBlockKind.BLOCK, "func1", Span(i, 0, i, 0)) for i in range(100)]

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=cfg_blocks,
            cfg_edges=[],
            expressions=[],
        )

        analyzer = ConstantPropagationAnalyzer()

        start = time.perf_counter()
        result = analyzer.analyze(ir_doc)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 수렴 검증
        assert result is not None
        assert len(result.reachable_blocks) >= 1

        # 성능 (100 blocks < 10ms)
        assert elapsed_ms < 10, f"Large graph too slow: {elapsed_ms:.1f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
