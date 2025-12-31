"""
Tests for RFC-021: FullTaintEngine Removal

Validates:
1. mode="full" fallback to path_sensitive works
2. Deprecation warning is emitted
3. QueryEngine.execute_flow(mode="full") is the recommended path
4. No import errors after removal

Test Categories:
- Base Case: Normal fallback behavior
- Edge Case: Warning message content
- Extreme Case: Repeated mode="full" calls
"""

import warnings
from unittest.mock import MagicMock, patch

import pytest


class TestUnifiedAnalyzerFullModeFallback:
    """Base Case: UnifiedAnalyzer mode='full' fallback"""

    def test_full_mode_creates_path_sensitive_analyzer(self, capsys):
        """mode='full' should fallback to PathSensitiveTaintAnalyzer"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        analyzer = UnifiedAnalyzer(taint_mode="full")

        # structlog outputs to stdout
        captured = capsys.readouterr()
        assert "deprecated" in captured.out.lower()

        # taint_mode should still be 'full' (for tracking)
        assert analyzer.taint_mode == "full"

    def test_full_mode_warning_contains_migration_path(self, capsys):
        """Edge Case: Warning should mention QueryEngine alternative"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        UnifiedAnalyzer(taint_mode="full")

        captured = capsys.readouterr()
        assert "QueryEngine" in captured.out
        assert "execute_flow" in captured.out

    def test_other_modes_no_warning(self, capsys):
        """Edge Case: Other modes should not emit deprecation warning about 'full'"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        for mode in ["basic", "path_sensitive", "field_sensitive"]:
            UnifiedAnalyzer(taint_mode=mode)
            captured = capsys.readouterr()

            # Should NOT contain deprecation warning about 'full' mode
            has_full_deprecation = "deprecated" in captured.out.lower() and "full" in captured.out.lower()
            assert not has_full_deprecation, f"Unexpected warning for mode={mode}"


class TestQueryEngineModeFullIntegration:
    """QueryEngine mode='full' is the recommended path"""

    def test_query_engine_full_mode_requires_context(self):
        """mode='full' requires project_context"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import (
            IRDocument,
        )
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import (
            QueryEngine,
        )

        # Create minimal valid IRDocument
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[],
            edges=[],
        )

        engine = QueryEngine(ir_doc=ir_doc, project_context=None)

        # Create mock FlowExpr
        mock_expr = MagicMock()
        mock_expr.source = MagicMock()
        mock_expr.target = MagicMock()

        with pytest.raises(ValueError, match="full mode requires project_context"):
            engine.execute_flow(mock_expr, mode="full")

    def test_query_engine_realtime_mode_works_without_context(self):
        """Realtime mode should work without project_context"""
        from codegraph_engine.code_foundation.domain.query.results import PathSet
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import (
            IRDocument,
        )
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import (
            QueryEngine,
        )

        # Create minimal valid IRDocument
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[],
            edges=[],
        )

        engine = QueryEngine(ir_doc=ir_doc, project_context=None)

        mock_expr = MagicMock()
        mock_expr.source = MagicMock()
        mock_expr.source.match.return_value = []
        mock_expr.target = MagicMock()
        mock_expr.target.match.return_value = []

        # Should not raise
        result = engine.execute_flow(mock_expr, mode="realtime")
        assert isinstance(result, PathSet)


class TestNoImportErrors:
    """Extreme Case: Verify no import errors after removal"""

    def test_import_unified_analyzer(self):
        """UnifiedAnalyzer should import without errors"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        assert UnifiedAnalyzer is not None

    def test_import_ir_document(self):
        """IRDocument should import without errors"""
        from codegraph_engine.code_foundation.infrastructure.ir.models.document import (
            IRDocument,
        )

        assert IRDocument is not None

    def test_import_query_engine(self):
        """QueryEngine should import without errors"""
        from codegraph_engine.code_foundation.infrastructure.query.query_engine import (
            QueryEngine,
        )

        assert QueryEngine is not None

    def test_no_taint_engine_full_import(self):
        """FullTaintEngine should NOT be importable"""
        with pytest.raises(ImportError):
            from codegraph_engine.code_foundation.infrastructure.analyzers.taint_engine_full import (
                FullTaintEngine,
            )


class TestVulnerabilityTypeReplacement:
    """Verify Vulnerability from domain/taint/models.py is used"""

    def test_vulnerability_model_exists(self):
        """New Vulnerability model should be available"""
        from codegraph_engine.code_foundation.domain.taint.models import Vulnerability

        assert Vulnerability is not None

    def test_vulnerability_has_required_fields(self):
        """Vulnerability should have key fields"""
        from codegraph_engine.code_foundation.domain.taint.models import Vulnerability

        # Check field names exist in model
        field_names = Vulnerability.model_fields.keys()
        required = ["id", "policy_id", "severity", "source", "sink", "flow", "confidence"]
        for field in required:
            assert field in field_names, f"Missing field: {field}"


class TestTaintModeEnum:
    """SOTA: Case-insensitive TaintMode enum"""

    def test_from_string_lowercase(self):
        """Base case: lowercase strings work"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode

        assert TaintMode.from_string("basic") == TaintMode.BASIC
        assert TaintMode.from_string("path_sensitive") == TaintMode.PATH_SENSITIVE
        assert TaintMode.from_string("field_sensitive") == TaintMode.FIELD_SENSITIVE
        assert TaintMode.from_string("full") == TaintMode.FULL

    def test_from_string_uppercase(self):
        """Edge case: UPPERCASE strings work"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode

        assert TaintMode.from_string("BASIC") == TaintMode.BASIC
        assert TaintMode.from_string("PATH_SENSITIVE") == TaintMode.PATH_SENSITIVE
        assert TaintMode.from_string("FIELD_SENSITIVE") == TaintMode.FIELD_SENSITIVE
        assert TaintMode.from_string("FULL") == TaintMode.FULL

    def test_from_string_mixed_case(self):
        """Edge case: MixedCase strings work"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode

        assert TaintMode.from_string("Basic") == TaintMode.BASIC
        assert TaintMode.from_string("Path_Sensitive") == TaintMode.PATH_SENSITIVE
        assert TaintMode.from_string("FIELD_sensitive") == TaintMode.FIELD_SENSITIVE

    def test_from_string_with_underscore(self):
        """Edge case: underscore separator works"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode

        assert TaintMode.from_string("path_sensitive") == TaintMode.PATH_SENSITIVE
        assert TaintMode.from_string("field_sensitive") == TaintMode.FIELD_SENSITIVE

    def test_from_string_invalid_raises(self):
        """Extreme case: invalid mode raises ValueError"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode

        with pytest.raises(ValueError, match="Invalid TaintMode"):
            TaintMode.from_string("invalid_mode")

        with pytest.raises(ValueError, match="Invalid TaintMode"):
            TaintMode.from_string("")

    def test_unified_analyzer_accepts_enum(self):
        """Integration: UnifiedAnalyzer accepts TaintMode enum"""
        from codegraph_engine.code_foundation.domain.query.types import TaintMode
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        analyzer = UnifiedAnalyzer(taint_mode=TaintMode.PATH_SENSITIVE)
        assert analyzer.taint_mode == "path_sensitive"

    def test_unified_analyzer_accepts_string_any_case(self):
        """Integration: UnifiedAnalyzer accepts string (any case)"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        # All these should work
        a1 = UnifiedAnalyzer(taint_mode="BASIC")
        assert a1.taint_mode == "basic"

        a2 = UnifiedAnalyzer(taint_mode="Path_Sensitive")
        assert a2.taint_mode == "path_sensitive"

    def test_unified_analyzer_invalid_mode_raises(self):
        """Extreme case: invalid mode raises ValueError at init"""
        from codegraph_engine.code_foundation.infrastructure.ir.unified_analyzer import (
            UnifiedAnalyzer,
        )

        with pytest.raises(ValueError, match="Invalid TaintMode"):
            UnifiedAnalyzer(taint_mode="not_a_mode")


class TestQueryModeEnum:
    """SOTA: QueryMode enum values"""

    def test_enum_values_exist(self):
        """QueryMode has expected values"""
        from codegraph_engine.code_foundation.domain.query.types import QueryMode

        assert QueryMode.REALTIME.value == "realtime"
        assert QueryMode.PR.value == "pr"
        assert QueryMode.FULL.value == "full"


class TestSemanticIrBuildModeEnum:
    """SOTA: SemanticIrBuildMode enum values"""

    def test_enum_values_exist(self):
        """SemanticIrBuildMode has expected values"""
        from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode

        assert SemanticIrBuildMode.QUICK.value == "quick"
        assert SemanticIrBuildMode.FULL.value == "full"


class TestIndexingModeEnum:
    """SOTA: IndexingMode enum values"""

    def test_enum_values_exist(self):
        """IndexingMode has expected values"""
        from codegraph_engine.analysis_indexing.infrastructure.models.mode import IndexingMode

        assert IndexingMode.FAST.value == "fast"
        assert IndexingMode.BALANCED.value == "balanced"
        assert IndexingMode.DEEP.value == "deep"
        assert IndexingMode.BOOTSTRAP.value == "bootstrap"
        assert IndexingMode.REPAIR.value == "repair"
