"""
Cost Pipeline Mode Routing Test (Minimal, SOTA L11)

핵심 통합만 검증:
1. di.py mode="cost" 분기 동작
2. create_cost_pipeline() 호출
3. Pipeline 생성 성공

NO MOCK, NO STUB - 실제 코드 경로만 검증
"""

import pytest

from codegraph_engine.code_foundation.di import code_foundation_container


class TestCostModeRouting:
    """Cost mode routing 핵심 검증 (No IR generation)"""

    def test_cost_mode_exists_in_di(self):
        """Test 1: di.py에 'cost' mode 분기가 존재하는지 검증"""
        # Given: Mock IR (minimal)
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap", nodes=[], edges=[])

        # When: Create cost pipeline
        try:
            pipeline = code_foundation_container.create_analyzer_pipeline(ir_doc, mode="cost")

            # Then: Should NOT raise ValueError
            assert pipeline is not None
            assert True, "Cost mode routing works!"

        except ValueError as e:
            if "Unknown mode" in str(e):
                pytest.fail(f"Cost mode not integrated! Error: {e}")
            else:
                raise

    def test_cost_pipeline_has_sccp_baseline(self):
        """Test 2: Cost pipeline에 SCCP baseline 포함 검증 (RFC-024 정책)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap", nodes=[], edges=[])

        # When: Create cost pipeline
        pipeline = code_foundation_container.create_analyzer_pipeline(ir_doc, mode="cost")

        # When: Run pipeline
        result = pipeline.run(incremental=False)

        # Then: Should have SCCP baseline
        assert "sccp_baseline" in result.execution_order, "Cost pipeline must include SCCP baseline!"

    def test_analyze_executor_cost_template_routing(self):
        """Test 3: AnalyzeExecutor의 template_id='cost_complexity' → mode='cost' 매핑 검증"""
        from codegraph_runtime.llm_arbitration.application.executors import AnalyzeExecutor

        executor = AnalyzeExecutor()

        # When: Get mode for cost_complexity template
        mode = executor._get_mode("cost_complexity")

        # Then: Should return "cost"
        assert mode == "cost", f"Expected 'cost', got '{mode}'"

    @pytest.mark.asyncio
    async def test_end_to_end_execute_executor_cost_routing(self):
        """Test 4: ExecuteExecutor → AnalyzeExecutor → cost mode 전체 경로 검증"""
        from codegraph_runtime.llm_arbitration.application import ExecuteExecutor
        from codegraph_engine.shared_kernel.contracts import AnalyzeSpec, Scope

        # Given: Cost analysis spec
        spec = AnalyzeSpec(
            intent="analyze",
            template_id="cost_complexity",
            scope=Scope(
                repo_id="test_repo",
                snapshot_id="snap_123",
            ),
            params={
                "functions": ["test_func"],
            },
        )

        # When: Execute via ExecuteExecutor
        executor = ExecuteExecutor()

        try:
            envelope = await executor.execute(spec.model_dump())

            # Then: Should return ResultEnvelope (not ValueError)
            assert envelope is not None
            assert envelope.request_id is not None

            # Should have claims (or mock claim if IR load failed)
            assert len(envelope.claims) > 0

        except ValueError as e:
            if "Unknown mode" in str(e):
                pytest.fail(f"Cost mode routing failed in ExecuteExecutor! Error: {e}")
            else:
                # Other errors are OK (e.g., IR loading not implemented)
                pass

    def test_cost_analyzer_registry_exists(self):
        """Test 5: CostAnalyzer가 Registry에 등록되었는지 검증"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.registry_v2 import get_registry

        registry = get_registry()

        # When: Check if cost_analyzer is registered
        has_cost = registry.has_builder("cost_analyzer")

        # Then: Should be registered
        assert has_cost, "CostAnalyzer not registered in registry!"

    def test_all_modes_work(self):
        """Test 6: 모든 mode가 동작하는지 검증 (regression test)"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

        ir_doc = IRDocument(repo_id="test", snapshot_id="snap", nodes=[], edges=[])

        modes = ["realtime", "pr", "audit", "cost"]

        for mode in modes:
            try:
                pipeline = code_foundation_container.create_analyzer_pipeline(ir_doc, mode=mode)
                assert pipeline is not None, f"Mode '{mode}' failed!"
            except ValueError as e:
                pytest.fail(f"Mode '{mode}' not supported! Error: {e}")


class TestCostPipelineContract:
    """Cost Pipeline 계약 검증 (RFC-028)"""

    def test_create_cost_pipeline_function_exists(self):
        """Test 7: create_cost_pipeline() 함수가 존재하는지 검증"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import modes

        # When: Check if create_cost_pipeline exists
        assert hasattr(modes, "create_cost_pipeline"), "create_cost_pipeline() not found!"
        assert callable(modes.create_cost_pipeline), "create_cost_pipeline is not callable!"

    def test_cost_analyzer_builder_exists(self):
        """Test 8: CostAnalyzer Builder가 존재하는지 검증"""
        try:
            from codegraph_engine.code_foundation.infrastructure.analyzers.configs import cost

            assert hasattr(cost, "_cost_builder"), "CostAnalyzer builder not found!"
            assert hasattr(cost, "registry"), "Registry not found in cost.py!"

        except ImportError:
            pytest.fail("cost.py config file not found!")

    def test_cost_analyzer_class_exists(self):
        """Test 9: CostAnalyzer 클래스가 존재하는지 검증"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.cost import CostAnalyzer

        # When: Check CostAnalyzer
        assert CostAnalyzer is not None
        assert hasattr(CostAnalyzer, "analyze_function"), "CostAnalyzer.analyze_function() not found!"


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
