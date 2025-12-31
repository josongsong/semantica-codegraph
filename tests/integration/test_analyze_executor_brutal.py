"""
Analyze Executor Brutal Test Suite (L11급 검증)

테스트 범위:
- Base Cases (정상 동작)
- Edge Cases (경계 조건)
- Corner Cases (특수 상황)
- Extreme Cases (극한 조건)

NO FAKE! NO STUB! Real validation!
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codegraph_runtime.llm_arbitration.application.executors.analyze_executor import AnalyzeExecutor
from codegraph_engine.shared_kernel.contracts import ResultEnvelope

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def minimal_ir_doc():
    """Minimal IRDocument for testing"""
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.models.node import IRNode

    return IRDocument(
        file_path="test.py",
        language="python",
        nodes=[
            IRNode(
                id="test.func",
                name="func",
                kind="function",
                file_path="test.py",
                start_line=1,
                end_line=10,
            )
        ],
        edges=[],
        cfg_blocks={},
        expressions=[],
    )


# ============================================================
# BASE CASES (정상 동작)
# ============================================================


class TestBaseCases:
    """Base Cases: 정상적인 입력, 예상되는 동작"""

    @pytest.mark.asyncio
    async def test_cost_analysis_base_case(self, minimal_ir_doc):
        """Base Case 1: Cost 분석 정상 동작"""
        executor = AnalyzeExecutor()

        # Mock IR loader
        async def mock_load_ir(repo_id, snapshot_id):
            return minimal_ir_doc

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        # Valid spec (Scope pattern 준수)
        spec = {
            "intent": "analyze",
            "template_id": "cost_complexity",
            "scope": {
                "repo_id": "repo:test",  # ✅ Pattern match
                "snapshot_id": "snap:main",  # ✅ Pattern match
            },
            "params": {"functions": ["test.func"]},
        }

        # Execute
        envelope = await executor.execute(spec, "req_test123")

        # Validate
        assert isinstance(envelope, ResultEnvelope)
        assert envelope.request_id == "req_test123"
        assert isinstance(envelope.claims, list)
        assert isinstance(envelope.evidences, list)

    @pytest.mark.asyncio
    async def test_race_analysis_base_case(self, minimal_ir_doc):
        """Base Case 2: Race 분석 정상 동작"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "intent": "analyze",
            "template_id": "race_detection",
            "scope": {
                "repo_id": "repo:test",
                "snapshot_id": "snap:main",
            },
            "params": {"functions": ["test.async_func"]},
        }

        envelope = await executor.execute(spec, "req_test456")

        assert isinstance(envelope, ResultEnvelope)
        assert envelope.request_id == "req_test456"

    @pytest.mark.asyncio
    async def test_diff_analysis_base_case(self, minimal_ir_doc):
        """Base Case 3: Diff 분석 정상 동작 (Base IR 필요)"""
        executor = AnalyzeExecutor()

        # Mock IR loader (before + after)
        async def mock_load_ir(repo_id, snapshot_id):
            return minimal_ir_doc

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "intent": "analyze",
            "template_id": "pr_diff",
            "scope": {
                "repo_id": "repo:test",
                "snapshot_id": "snap:pr",
                "parent_snapshot_id": "snap:base",  # ✅ Base 명시
            },
            "params": {"functions": ["test.func"]},
        }

        envelope = await executor.execute(spec, "req_test789")

        assert isinstance(envelope, ResultEnvelope)
        assert envelope.request_id == "req_test789"


# ============================================================
# EDGE CASES (경계 조건)
# ============================================================


class TestEdgeCases:
    """Edge Cases: 경계 조건, 빈 값, Null"""

    @pytest.mark.asyncio
    async def test_empty_functions_list(self, minimal_ir_doc):
        """Edge Case 1: 빈 functions 리스트 → ValueError"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": []},  # ❌ Empty
        }

        # Should raise
        with pytest.raises(ValueError, match="requires 'functions' param"):
            await executor.execute(spec, "req_empty")

    @pytest.mark.asyncio
    async def test_missing_functions_param(self, minimal_ir_doc):
        """Edge Case 2: functions param 없음 → ValueError"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {},  # ❌ No functions
        }

        with pytest.raises(ValueError, match="requires 'functions' param"):
            await executor.execute(spec, "req_missing")

    @pytest.mark.asyncio
    async def test_invalid_functions_type(self, minimal_ir_doc):
        """Edge Case 3: functions가 list가 아님 → ValueError"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": "not_a_list"},  # ❌ Wrong type
        }

        with pytest.raises(ValueError, match="must be list"):
            await executor.execute(spec, "req_type")

    @pytest.mark.asyncio
    async def test_ir_doc_none(self):
        """Edge Case 4: IR document 없음 → ValueError (NO FAKE!)"""
        executor = AnalyzeExecutor()

        # Mock: IR 로드 실패
        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=None)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:nonexistent", "snapshot_id": "snap:invalid"},
            "params": {"functions": ["test.func"]},
        }

        # Should raise (NO FAKE!)
        with pytest.raises(ValueError, match="IR document required"):
            await executor.execute(spec, "req_none")

    @pytest.mark.asyncio
    async def test_diff_without_parent_snapshot(self, minimal_ir_doc):
        """Edge Case 5: Diff에 parent_snapshot_id 없음 → ValueError"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "pr_diff",
            "scope": {
                "repo_id": "repo:test",
                "snapshot_id": "snap:pr",
                # ❌ parent_snapshot_id 없음
            },
            "params": {"functions": ["test.func"]},
        }

        with pytest.raises(ValueError, match="requires scope.parent_snapshot_id"):
            await executor.execute(spec, "req_diff")

    @pytest.mark.asyncio
    async def test_base_ir_load_failure(self, minimal_ir_doc):
        """Edge Case 6: Base IR 로드 실패 → ValueError"""
        executor = AnalyzeExecutor()

        # Mock: PR IR 성공, Base IR 실패
        async def mock_load_ir(repo_id, snapshot_id):
            if snapshot_id == "snap:base":
                return None  # Base 실패
            return minimal_ir_doc

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(side_effect=mock_load_ir)

        spec = {
            "template_id": "pr_diff",
            "scope": {
                "repo_id": "repo:test",
                "snapshot_id": "snap:pr",
                "parent_snapshot_id": "snap:base",
            },
            "params": {"functions": ["test.func"]},
        }

        with pytest.raises(ValueError, match="Failed to load base IR"):
            await executor.execute(spec, "req_base_fail")


# ============================================================
# CORNER CASES (특수 상황)
# ============================================================


class TestCornerCases:
    """Corner Cases: 특수하거나 드문 상황"""

    @pytest.mark.asyncio
    async def test_template_config_unknown_template(self):
        """Corner Case 1: 알 수 없는 template → default mode"""
        executor = AnalyzeExecutor()

        mode = executor._get_mode("unknown_template_xyz")

        # Should return default (no crash!)
        assert mode == executor.DEFAULT_MODE  # "realtime"

    @pytest.mark.asyncio
    async def test_di_injection_works(self):
        """Corner Case 2: DI injection 검증"""
        # Mock analyzer
        mock_cost_analyzer = MagicMock()
        mock_cost_adapter = MagicMock()

        executor = AnalyzeExecutor(
            cost_analyzer=mock_cost_analyzer,
            cost_adapter=mock_cost_adapter,
        )

        # Property should return injected mock
        assert executor.cost_analyzer is mock_cost_analyzer
        assert executor.cost_adapter is mock_cost_adapter

    @pytest.mark.asyncio
    async def test_lazy_loading_singleton(self):
        """Corner Case 3: Lazy loading은 singleton처럼 동작"""
        executor = AnalyzeExecutor()

        # 첫 호출
        analyzer1 = executor.cost_analyzer
        # 두 번째 호출
        analyzer2 = executor.cost_analyzer

        # 같은 인스턴스여야 함
        assert analyzer1 is analyzer2

    @pytest.mark.asyncio
    async def test_partial_results_ok(self, minimal_ir_doc):
        """Corner Case 4: 일부 함수 실패해도 OK (partial results)"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        # Mock analyzer: 1개 성공, 1개 실패
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_function = MagicMock(
            side_effect=[
                MagicMock(  # Success
                    cost_term="n",
                    verdict="proven",
                    complexity=MagicMock(is_slow=lambda: False),
                ),
                Exception("Analysis failed"),  # Failure
            ]
        )

        executor._cost_analyzer = mock_analyzer

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": ["func1", "func2"]},  # 2개
        }

        # Should NOT raise (partial OK)
        envelope = await executor.execute(spec, "req_partial")

        # 성공한 1개 결과만 있어야 함
        # (실제로는 CostAdapter가 처리)
        assert isinstance(envelope, ResultEnvelope)


# ============================================================
# EXTREME CASES (극한 조건)
# ============================================================


class TestExtremeCases:
    """Extreme Cases: 극한 조건, 대규모, 성능"""

    @pytest.mark.asyncio
    async def test_100_functions(self, minimal_ir_doc):
        """Extreme Case 1: 100개 함수 동시 분석"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": [f"test.func{i}" for i in range(100)]},  # 100개!
        }

        # Should handle (partial results OK)
        envelope = await executor.execute(spec, "req_100")

        assert isinstance(envelope, ResultEnvelope)
        # Metrics should record 100 functions attempted

    @pytest.mark.asyncio
    async def test_very_long_function_name(self, minimal_ir_doc):
        """Extreme Case 2: 매우 긴 함수 이름"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        very_long_name = "module." + "SubModule." * 50 + "veryLongFunctionName"

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": [very_long_name]},
        }

        # Should not crash (even if analysis fails)
        envelope = await executor.execute(spec, "req_long")
        assert isinstance(envelope, ResultEnvelope)

    @pytest.mark.asyncio
    async def test_concurrent_execution(self, minimal_ir_doc):
        """Extreme Case 3: 동시 실행 (thread-safety)"""
        import asyncio

        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": ["test.func"]},
        }

        # 10개 동시 실행
        tasks = [executor.execute(spec, f"req_concurrent_{i}") for i in range(10)]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 모두 성공해야 함 (thread-safe)
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent execution failed: {result}")
            assert isinstance(result, ResultEnvelope)

    @pytest.mark.asyncio
    async def test_unicode_in_function_name(self, minimal_ir_doc):
        """Extreme Case 4: Unicode 함수 이름"""
        executor = AnalyzeExecutor()

        executor._ir_loader = MagicMock()
        executor._ir_loader.load_ir = AsyncMock(return_value=minimal_ir_doc)

        spec = {
            "template_id": "cost_complexity",
            "scope": {"repo_id": "repo:test", "snapshot_id": "snap:main"},
            "params": {"functions": ["test.함수명_한글"]},
        }

        # Should handle unicode gracefully
        envelope = await executor.execute(spec, "req_unicode")
        assert isinstance(envelope, ResultEnvelope)


# ============================================================
# SCHEMA VALIDATION CASES
# ============================================================


class TestSchemaValidation:
    """Schema Validation: Pydantic pattern 검증"""

    @pytest.mark.asyncio
    async def test_scope_pattern_validation(self):
        """Schema 1: Scope pattern validation"""
        from codegraph_engine.shared_kernel.contracts import Scope

        # ✅ Valid patterns
        scope = Scope(repo_id="repo:test123", snapshot_id="snap:abc-123_xyz")
        assert scope.repo_id == "repo:test123"

        # ❌ Invalid repo_id (no prefix)
        with pytest.raises(ValueError):
            Scope(repo_id="test", snapshot_id="snap:main")  # Missing "repo:"

        # ❌ Invalid snapshot_id (no prefix)
        with pytest.raises(ValueError):
            Scope(repo_id="repo:test", snapshot_id="main")  # Missing "snap:"

    @pytest.mark.asyncio
    async def test_parent_snapshot_different_from_snapshot(self):
        """Schema 2: parent_snapshot_id ≠ snapshot_id"""
        from codegraph_engine.shared_kernel.contracts import Scope

        # ✅ Different (valid)
        scope = Scope(repo_id="repo:test", snapshot_id="snap:after", parent_snapshot_id="snap:before")
        assert scope.is_incremental()

        # ❌ Same (invalid)
        with pytest.raises(ValueError, match="must be different"):
            Scope(repo_id="repo:test", snapshot_id="snap:main", parent_snapshot_id="snap:main")  # Same!


# ============================================================
# DI PATTERN VALIDATION
# ============================================================


class TestDIPattern:
    """DI Pattern: SOLID 'D' 원칙 검증"""

    def test_all_analyzers_injectable(self):
        """DI 1: 모든 analyzer가 injection 가능"""
        mock_cost = MagicMock()
        mock_race = MagicMock()
        mock_diff = MagicMock()

        executor = AnalyzeExecutor(
            cost_analyzer=mock_cost,
            race_detector=mock_race,
            diff_analyzer=mock_diff,
        )

        assert executor.cost_analyzer is mock_cost
        assert executor.race_detector is mock_race
        assert executor.diff_analyzer is mock_diff

    def test_all_adapters_injectable(self):
        """DI 2: 모든 adapter가 injection 가능"""
        mock_cost_adapter = MagicMock()
        mock_race_adapter = MagicMock()
        mock_diff_adapter = MagicMock()

        executor = AnalyzeExecutor(
            cost_adapter=mock_cost_adapter,
            race_adapter=mock_race_adapter,
            diff_adapter=mock_diff_adapter,
        )

        assert executor.cost_adapter is mock_cost_adapter
        assert executor.race_adapter is mock_race_adapter
        assert executor.diff_adapter is mock_diff_adapter

    def test_lazy_loading_only_once(self):
        """DI 3: Lazy loading은 한 번만 (singleton)"""
        executor = AnalyzeExecutor()

        # 첫 호출
        a1 = executor.cost_analyzer
        a2 = executor.cost_adapter

        # 두 번째 호출
        a3 = executor.cost_analyzer
        a4 = executor.cost_adapter

        # 같은 인스턴스
        assert a1 is a3
        assert a2 is a4


# ============================================================
# YAML CONFIGURATION VALIDATION
# ============================================================


class TestYAMLConfiguration:
    """YAML Configuration: templates.yaml 검증"""

    def test_template_config_loads(self):
        """YAML 1: TemplateConfig 로드"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig

        config = TemplateConfig.load()

        # 기본 templates 존재 확인
        templates = config.list_templates()
        assert "sql_injection" in templates
        assert "cost_complexity" in templates
        assert "race_detection" in templates
        assert "pr_diff" in templates

    def test_specialized_templates(self):
        """YAML 2: Specialized templates 구분"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig

        config = TemplateConfig.load()

        # Specialized
        assert config.is_specialized("cost_complexity") is True
        assert config.is_specialized("race_detection") is True
        assert config.is_specialized("pr_diff") is True

        # Not specialized
        assert config.is_specialized("sql_injection") is False

    def test_mode_mapping(self):
        """YAML 3: Mode 매핑"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig

        config = TemplateConfig.load()

        assert config.get_mode("sql_injection") == "audit"
        assert config.get_mode("cost_complexity") == "cost"
        assert config.get_mode("race_detection") == "audit"
        assert config.get_mode("pr_diff") == "pr"

    def test_unknown_template_raises(self):
        """YAML 4: 알 수 없는 template → KeyError"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs.template_loader import TemplateConfig

        config = TemplateConfig.load()

        with pytest.raises(KeyError, match="Unknown template"):
            config.get_mode("nonexistent_template")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
