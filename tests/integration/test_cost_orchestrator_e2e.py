"""
Cost Analyzer Orchestrator End-to-End Test (RFC-028 Point 1)

실제 Orchestrator를 사용한 극한 검증.

CRITICAL: DI가 실제로 작동하는지 확인
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingConfig, IndexingStatus
from codegraph_engine.analysis_indexing.infrastructure.orchestrator_slim import IndexingOrchestratorSlim
from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer


class TestOrchestratorDIIntegration:
    """Orchestrator DI 검증"""

    def test_cost_analyzer_di_through_kwargs(self):
        """kwargs로 cost_analyzer 주입 가능해야 함"""
        cost_analyzer = CostAnalyzer()

        # Legacy initialization (kwargs)
        orchestrator = IndexingOrchestratorSlim(
            parser_registry=Mock(),
            ir_builder=Mock(),
            semantic_ir_builder=Mock(),
            graph_builder=Mock(),
            chunk_builder=Mock(),
            graph_store=Mock(),
            chunk_store=Mock(),
            repomap_store=Mock(),
            lexical_index=Mock(),
            vector_index=Mock(),
            symbol_index=Mock(),
            fuzzy_index=Mock(),
            domain_index=Mock(),
            cost_analyzer=cost_analyzer,  # ← DI!
        )

        # Stage should have cost_analyzer
        assert orchestrator._stages.semantic_ir.cost_analyzer is not None
        assert orchestrator._stages.semantic_ir.cost_analyzer is cost_analyzer

    def test_cost_analyzer_optional(self):
        """cost_analyzer 없어도 crash 안 해야 함"""
        orchestrator = IndexingOrchestratorSlim(
            parser_registry=Mock(),
            ir_builder=Mock(),
            semantic_ir_builder=Mock(),
            graph_builder=Mock(),
            chunk_builder=Mock(),
            graph_store=Mock(),
            chunk_store=Mock(),
            repomap_store=Mock(),
            lexical_index=Mock(),
            vector_index=Mock(),
            symbol_index=Mock(),
            fuzzy_index=Mock(),
            domain_index=Mock(),
            # cost_analyzer 안 줌!
        )

        # Should not crash
        assert orchestrator._stages.semantic_ir is not None
        # cost_analyzer는 None
        assert orchestrator._stages.semantic_ir.cost_analyzer is None


class TestCostAnalyzerConfigCheck:
    """Config enable_realtime_analysis 검증"""

    def test_config_enable_realtime_analysis_exists(self):
        """IndexingConfig에 enable_realtime_analysis 필드 있어야 함"""
        from codegraph_engine.analysis_indexing.infrastructure.models import IndexingConfig

        config = IndexingConfig()

        # Should have field (or be settable)
        try:
            config.enable_realtime_analysis = True
            assert config.enable_realtime_analysis == True
        except AttributeError:
            pytest.fail("IndexingConfig에 enable_realtime_analysis 필드 없음!")


class TestCostAnalyzerNonBlocking:
    """Non-blocking 검증 (극한)"""

    @pytest.mark.asyncio
    async def test_cost_analysis_exception_does_not_break_indexing(self):
        """Cost 분석 실패해도 indexing 계속되어야 함"""
        from codegraph_engine.analysis_indexing.infrastructure.models import IndexingResult
        from codegraph_engine.analysis_indexing.infrastructure.stages.base import StageContext
        from codegraph_engine.analysis_indexing.infrastructure.stages.ir_stage import SemanticIRStage
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

        # Mock analyzer that always fails
        failing_analyzer = Mock()
        failing_analyzer.analyze_function = Mock(side_effect=RuntimeError("Forced failure"))

        components = Mock()
        components.semantic_ir_builder = Mock()
        components.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))
        components.cost_analyzer = failing_analyzer  # Always fails!

        stage = SemanticIRStage(components)

        config = IndexingConfig()
        config.enable_realtime_analysis = True

        ctx = StageContext(
            repo_path=Path("/tmp"),
            repo_id="test",
            snapshot_id="snap",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=True,
        )

        ctx.ir_doc = IRDocument(repo_id="test", snapshot_id="snap")
        ctx.ir_doc.nodes = []
        ctx.ir_doc.cfg_blocks = []
        ctx.ir_doc.expressions = []

        change_set = Mock()
        change_set.changed_functions = ["func"]
        ctx.change_set = change_set

        # Should NOT crash (non-blocking)
        await stage.execute(ctx)

        # Semantic IR should be built (indexing continued)
        assert ctx.semantic_ir is not None
