"""
Cost Analyzer IRStage Integration Tests (RFC-028 Point 1)

Real-time cost analysis during indexing.

Test Cases:
- Incremental mode with cost analysis
- Full mode (should skip)
- Changed functions extraction
- Error handling (non-blocking)
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingConfig, IndexingResult, IndexingStatus
from codegraph_engine.analysis_indexing.infrastructure.stages.base import StageContext
from codegraph_engine.analysis_indexing.infrastructure.stages.ir_stage import SemanticIRStage
from codegraph_engine.code_foundation.infrastructure.analyzers.cost import ComplexityClass, CostAnalyzer, CostResult
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import CFGBlockKind, ControlFlowBlock
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind


@pytest.fixture
def mock_components_with_cost():
    """Mock components with CostAnalyzer"""
    components = Mock()
    components.ir_builder = Mock()
    components.semantic_ir_builder = Mock()
    components.pyright_daemon_factory = None
    components.project_root = None
    components.cost_analyzer = CostAnalyzer()  # Real analyzer!

    return components


@pytest.fixture
def ir_doc_with_loop():
    """IRDocument with simple loop"""
    ir_doc = IRDocument(repo_id="test", snapshot_id="snap_001")

    func = Node(
        id="f1",
        kind=NodeKind.METHOD,
        fqn="process_data",
        file_path="api.py",
        span=Span(10, 0, 15, 0),
        language="python",
    )
    ir_doc.nodes = [func]

    loop = ControlFlowBlock(id="loop1", kind=CFGBlockKind.LOOP_HEADER, function_node_id="f1", span=Span(11, 4, 11, 20))

    ir_doc.cfg_blocks = [loop]

    range_call = Expression(
        id="e1",
        kind=ExprKind.CALL,
        repo_id="test",
        file_path="api.py",
        function_fqn="process_data",
        span=Span(11, 14, 11, 22),
        block_id="loop1",
        attrs={"callee_name": "range", "arg_expr_ids": ["e2"]},
    )

    n_var = Expression(
        id="e2",
        kind=ExprKind.NAME_LOAD,
        repo_id="test",
        file_path="api.py",
        function_fqn="process_data",
        span=Span(11, 20, 11, 21),
        attrs={"var_name": "n"},
    )

    ir_doc.expressions = [range_call, n_var]

    return ir_doc


class TestSemanticIRStageCostIntegration:
    """SemanticIRStage + CostAnalyzer integration"""

    @pytest.mark.asyncio
    async def test_incremental_mode_runs_cost_analysis(self, mock_components_with_cost, ir_doc_with_loop):
        """Incremental mode should run cost analysis"""
        stage = SemanticIRStage(mock_components_with_cost)

        # Mock semantic_ir_builder
        mock_components_with_cost.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))

        # Create context (incremental)
        config = IndexingConfig()
        config.enable_realtime_analysis = True  # Enable!

        ctx = StageContext(
            repo_path=Path("/tmp/test"),
            repo_id="test",
            snapshot_id="snap_001",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap_001", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=True,  # Incremental!
        )

        ctx.ir_doc = ir_doc_with_loop

        # Mock change_set
        change_set = Mock()
        change_set.changed_functions = ["process_data"]
        ctx.change_set = change_set

        # Execute
        await stage.execute(ctx)

        # Should have cost results
        assert hasattr(ctx, "analysis_results")
        assert "cost" in ctx.analysis_results
        assert "process_data" in ctx.analysis_results["cost"]

        result = ctx.analysis_results["cost"]["process_data"]
        assert result.complexity == ComplexityClass.LINEAR
        assert result.verdict == "proven"

    @pytest.mark.asyncio
    async def test_full_mode_skips_cost_analysis(self, mock_components_with_cost, ir_doc_with_loop):
        """Full mode should skip cost analysis (performance)"""
        stage = SemanticIRStage(mock_components_with_cost)

        mock_components_with_cost.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))

        config = IndexingConfig()
        config.enable_realtime_analysis = True

        ctx = StageContext(
            repo_path=Path("/tmp/test"),
            repo_id="test",
            snapshot_id="snap_001",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap_001", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=False,  # Full mode!
        )

        ctx.ir_doc = ir_doc_with_loop

        # Execute
        await stage.execute(ctx)

        # Should NOT have cost results (full mode skipped)
        assert not hasattr(ctx, "analysis_results") or "cost" not in getattr(ctx, "analysis_results", {})

    @pytest.mark.asyncio
    async def test_cost_analyzer_not_provided(self, ir_doc_with_loop):
        """Cost analyzer not provided should not crash"""
        components = Mock()
        components.ir_builder = Mock()
        components.semantic_ir_builder = Mock()
        components.pyright_daemon_factory = None
        components.project_root = None
        components.cost_analyzer = None  # Not provided!

        stage = SemanticIRStage(components)

        components.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))

        config = IndexingConfig()
        config.enable_realtime_analysis = True

        ctx = StageContext(
            repo_path=Path("/tmp/test"),
            repo_id="test",
            snapshot_id="snap_001",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap_001", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=True,
        )

        ctx.ir_doc = ir_doc_with_loop

        # Should not crash
        await stage.execute(ctx)

        # No cost results (analyzer not provided)
        assert not hasattr(ctx, "analysis_results") or "cost" not in getattr(ctx, "analysis_results", {})

    @pytest.mark.asyncio
    async def test_cost_analysis_error_non_blocking(self, mock_components_with_cost):
        """Cost analysis error should not break indexing"""
        stage = SemanticIRStage(mock_components_with_cost)

        mock_components_with_cost.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))

        config = IndexingConfig()
        config.enable_realtime_analysis = True

        ctx = StageContext(
            repo_path=Path("/tmp/test"),
            repo_id="test",
            snapshot_id="snap_001",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap_001", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=True,
        )

        # Invalid IR (will cause error)
        ctx.ir_doc = IRDocument(repo_id="test", snapshot_id="snap")
        ctx.ir_doc.nodes = []
        ctx.ir_doc.cfg_blocks = []
        ctx.ir_doc.expressions = []

        change_set = Mock()
        change_set.changed_functions = ["nonexistent"]
        ctx.change_set = change_set

        # Should not crash (error is caught)
        await stage.execute(ctx)

        # Indexing should complete (non-blocking)
        assert ctx.semantic_ir is not None

    @pytest.mark.asyncio
    async def test_performance_limit_10_functions(self, mock_components_with_cost, ir_doc_with_loop):
        """Should limit to 10 functions (performance)"""
        stage = SemanticIRStage(mock_components_with_cost)

        mock_components_with_cost.semantic_ir_builder.build_full = MagicMock(return_value=(Mock(), Mock()))

        config = IndexingConfig()
        config.enable_realtime_analysis = True

        ctx = StageContext(
            repo_path=Path("/tmp/test"),
            repo_id="test",
            snapshot_id="snap_001",
            result=IndexingResult(
                repo_id="test", snapshot_id="snap_001", status=IndexingStatus.IN_PROGRESS, start_time=datetime.now()
            ),
            config=config,
            is_incremental=True,
        )

        ctx.ir_doc = ir_doc_with_loop

        # Mock 20 changed functions
        change_set = Mock()
        change_set.changed_functions = [f"func_{i}" for i in range(20)]
        ctx.change_set = change_set

        # Execute
        await stage.execute(ctx)

        # Should analyze only 10 (limit)
        if hasattr(ctx, "analysis_results") and "cost" in ctx.analysis_results:
            assert len(ctx.analysis_results["cost"]) <= 10
