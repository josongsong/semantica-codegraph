"""
Pipeline End-to-End Tests (L11 Production)

RFC-024: Pipeline 실제 실행 검증

Coverage:
- Pipeline.run() 실제 호출
- SCCP 실행 순서
- Context 전달
- 결과 저장
- 증분 모드
"""

import pytest

# Config import → 자동 등록!
from codegraph_engine.code_foundation.infrastructure.analyzers.configs import baseline  # noqa: F401
from codegraph_engine.code_foundation.infrastructure.analyzers.configs.modes import create_realtime_pipeline
from codegraph_engine.code_foundation.infrastructure.analyzers.pipeline_v2 import AnalyzerPipeline
from codegraph_engine.code_foundation.infrastructure.analyzers.registry_v2 import get_registry
from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class TestPipelineE2E:
    """Pipeline E2E (Production Critical!)"""

    def setup_method(self):
        """Config 재등록 (다른 테스트가 clear할 수 있음)"""
        # Registry 재등록
        from codegraph_engine.code_foundation.domain.analyzers.builder import AnalyzerBuilder
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        registry = get_registry()
        # 이미 등록되어 있으면 skip
        try:
            registry.get_builder("sccp_baseline")
        except KeyError:
            # 등록 안 되어 있으면 등록
            builder = AnalyzerBuilder(ConstantPropagationAnalyzer)
            registry.register_builder("sccp_baseline", builder)

    def test_sccp_only_execution(self):
        """SCCP만 실행 (최소 케이스)"""
        # Mock IRDocument (DFG, CFG 있다고 가정)
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=[ControlFlowBlock("entry", CFGBlockKind.ENTRY, "func1", Span(1, 0, 1, 0))],
            cfg_edges=[],
            expressions=[],
        )

        pipeline = AnalyzerPipeline(ir_doc)
        pipeline.add("sccp_baseline")

        result = pipeline.run()

        # 검증
        assert "sccp_baseline" in result.results
        assert len(result.execution_order) == 1
        assert result.execution_order[0] == "sccp_baseline"

        # SCCP 결과
        sccp_result = result.results["sccp_baseline"]
        assert sccp_result is not None
        assert hasattr(sccp_result, "constants_found")

    def test_realtime_mode_preset(self):
        """Realtime 모드 Preset"""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=[ControlFlowBlock("entry", CFGBlockKind.ENTRY, "func1", Span(1, 0, 1, 0))],
            cfg_edges=[],
            expressions=[],
        )

        pipeline = create_realtime_pipeline(ir_doc)

        result = pipeline.run(incremental=True)

        # Realtime에는 SCCP 포함
        assert "sccp_baseline" in result.results

    def test_context_propagation(self):
        """Context가 분석기 간 전달됨"""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=[ControlFlowBlock("entry", CFGBlockKind.ENTRY, "func1", Span(1, 0, 1, 0))],
            cfg_edges=[],
            expressions=[],
        )

        pipeline = AnalyzerPipeline(ir_doc)
        pipeline.add("sccp_baseline")

        result = pipeline.run()

        # Context에 SCCP 결과 저장됨
        assert pipeline._context.has(ConstantPropagationAnalyzer)

        sccp_from_context = pipeline._context.get(ConstantPropagationAnalyzer)
        assert sccp_from_context is result.results["sccp_baseline"]


class TestIncrementalMode:
    """증분 모드 실행"""

    def test_incremental_flag_propagated(self):
        """증분 플래그가 Context에 전달됨"""
        from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
            CFGBlockKind,
            ControlFlowBlock,
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="v1",
            dfg_snapshot=DfgSnapshot(),
            cfg_blocks=[ControlFlowBlock("entry", CFGBlockKind.ENTRY, "func1", Span(1, 0, 1, 0))],
            cfg_edges=[],
            expressions=[],
        )

        pipeline = AnalyzerPipeline(ir_doc)
        pipeline.add("sccp_baseline")

        result = pipeline.run(incremental=True)

        # Context에 증분 플래그 설정됨
        assert pipeline._context.incremental is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
