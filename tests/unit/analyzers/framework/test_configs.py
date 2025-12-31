"""
Config Tests

RFC-024 Part 3: Config 검증

Coverage:
- Baseline Config 등록
- Mode Presets (Realtime, PR, Audit)
- Registry 통합
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.configs.modes import (
    create_audit_pipeline,
    create_pr_pipeline,
    create_realtime_pipeline,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.registry_v2 import get_registry
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class TestBaselineConfig:
    """Baseline Config (SCCP) 검증"""

    def test_sccp_baseline_registered(self):
        """SCCP baseline이 Registry에 등록됨"""
        # configs.baseline import 시 자동 등록
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import baseline  # noqa: F401

        registry = get_registry()

        # 등록 확인
        assert "sccp_baseline" in registry.list_all()

        builder = registry.get_builder("sccp_baseline")
        assert builder is not None
        assert builder._analyzer_cls.__name__ == "ConstantPropagationAnalyzer"


class TestTaintConfigs:
    """Taint Config 검증 (Option 2!)"""

    def test_all_taint_analyzers_registered(self):
        """3개 Taint 분석기 등록"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import taint  # noqa: F401

        registry = get_registry()
        analyzers = registry.list_all()

        # 3개 등록 확인
        assert "interprocedural_taint" in analyzers
        assert "field_sensitive_taint" in analyzers
        assert "path_sensitive_taint" in analyzers

    def test_taint_requires_sccp(self):
        """Taint 분석기는 SCCP 의존"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import taint  # noqa: F401
        from codegraph_engine.code_foundation.infrastructure.dfg.constant.analyzer import ConstantPropagationAnalyzer

        registry = get_registry()

        for name in ["interprocedural_taint", "field_sensitive_taint", "path_sensitive_taint"]:
            builder = registry.get_builder(name)
            deps = builder.get_dependencies()

            # SCCP baseline 의존 확인
            assert ConstantPropagationAnalyzer in deps, f"{name} must depend on SCCP!"


class TestHeapConfigs:
    """Heap Config 검증 (Option 2!)"""

    def test_all_heap_analyzers_registered(self):
        """2개 Heap 분석기 등록"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.configs import heap  # noqa: F401

        registry = get_registry()
        analyzers = registry.list_all()

        # 2개 등록 확인
        assert "realtime_null" in analyzers
        assert "audit_null" in analyzers


class TestModePresets:
    """Mode Presets 검증"""

    def test_realtime_pipeline_creation(self):
        """Realtime Pipeline 생성"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        pipeline = create_realtime_pipeline(ir_doc)

        assert pipeline is not None
        assert "sccp_baseline" in pipeline._analyzer_names

    def test_pr_pipeline_creation(self):
        """PR Pipeline 생성"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        pipeline = create_pr_pipeline(ir_doc)

        assert pipeline is not None
        assert "sccp_baseline" in pipeline._analyzer_names

    def test_audit_pipeline_creation(self):
        """Audit Pipeline 생성"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        pipeline = create_audit_pipeline(ir_doc)

        assert pipeline is not None
        assert "sccp_baseline" in pipeline._analyzer_names

    def test_all_modes_include_sccp(self):
        """모든 모드에 SCCP baseline 포함 (RFC-024 정책!)"""
        ir_doc = IRDocument(repo_id="test", snapshot_id="v1")

        modes = [
            ("Realtime", create_realtime_pipeline(ir_doc)),
            ("PR", create_pr_pipeline(ir_doc)),
            ("Audit", create_audit_pipeline(ir_doc)),
        ]

        for mode_name, pipeline in modes:
            assert "sccp_baseline" in pipeline._analyzer_names, f"{mode_name} mode must include SCCP baseline!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
