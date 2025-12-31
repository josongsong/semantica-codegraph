"""
Type Inference Metrics Tests

RFC-030: Metrics and Gap Analysis for Engine Improvements

Tests for:
- InferenceMetrics tracking
- Gap analysis for missing types/methods
- Per-file statistics
- JSON export
"""

import json
import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import (
    ExpressionTypeRequest,
    InferContext,
    InferResult,
    InferSource,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.metrics import (
    InferenceMetrics,
    MissingTypeRecord,
    PyrightFallbackRecord,
    reset_global_metrics,
)


@pytest.fixture(autouse=True)
def reset_global():
    """Reset global metrics before each test."""
    reset_global_metrics()
    yield
    reset_global_metrics()


@pytest.fixture
def metrics():
    """Fresh metrics instance for each test."""
    return InferenceMetrics()


class TestInferenceMetricsBasic:
    """Basic metrics recording tests."""

    def test_record_annotation_hit(self, metrics):
        """Record annotation inference."""
        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="x",
            kind="variable",
        )
        result = InferResult.from_annotation("int")

        metrics.record_inference(request, result, "test.py")

        report = metrics.get_coverage_report()
        assert report["total_inferences"] == 1
        assert report["self_contained_rate"] == 1.0
        assert report["by_source"]["annotation"] == 1.0

    def test_record_builtin_method_hit(self, metrics):
        """Record builtin method inference."""
        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="y",
            kind="method_call",
            receiver_type="str",
            method_name="upper",
        )
        result = InferResult.from_builtin_method("str")

        metrics.record_inference(request, result, "test.py")

        report = metrics.get_coverage_report()
        assert report["by_source"]["builtin_method"] == 1.0

    def test_record_pyright_fallback(self, metrics):
        """Record Pyright fallback."""
        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="df",
            kind="method_call",
            receiver_type="DataFrame",
            method_name="groupby",
        )
        result = InferResult.from_pyright("DataFrameGroupBy")

        metrics.record_inference(request, result, "analysis.py")

        report = metrics.get_coverage_report()
        assert report["pyright_fallback_rate"] == 1.0

        # Check fallback is recorded
        summary = metrics.get_fallback_summary()
        assert summary["total_fallbacks"] == 1
        assert summary["by_receiver"]["DataFrame"] == 1

    def test_record_unknown(self, metrics):
        """Record unknown (failed) inference."""
        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="mystery",
            kind="attribute",
        )
        result = InferResult.unknown()

        metrics.record_inference(request, result, "test.py")

        report = metrics.get_coverage_report()
        assert report["unknown_rate"] == 1.0


class TestMissingMethodTracking:
    """Tests for missing method tracking."""

    def test_track_missing_method_via_pyright(self):
        """Track methods resolved by Pyright (should be in builtin table)."""
        # Use a fresh instance to avoid pollution
        metrics = InferenceMetrics()

        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="result",
            kind="method_call",
            receiver_type="Path",
            method_name="with_suffix",
        )
        result = InferResult.from_pyright("Path")

        metrics.record_inference(request, result, "file1.py")
        metrics.record_inference(request, result, "file2.py")

        gaps = metrics.get_gap_analysis()
        missing = gaps["missing_methods"]
        assert len(missing) >= 1

        path_method = next(
            (m for m in missing if m["receiver_type"] == "Path" and m["method_name"] == "with_suffix"), None
        )
        assert path_method is not None
        assert path_method["count"] == 2
        assert "Path" in path_method["pyright_types"]

    def test_track_missing_method_via_unknown(self):
        """Track completely failed inferences."""
        # Use a fresh instance
        metrics = InferenceMetrics()

        request = ExpressionTypeRequest(
            expr_id="expr_1",
            var_name="result",
            kind="method_call",
            receiver_type="CustomClass",
            method_name="custom_method",
        )
        result = InferResult.unknown()

        for _ in range(5):
            metrics.record_inference(request, result, "test.py")

        gaps = metrics.get_gap_analysis()
        missing = gaps["missing_methods"]
        custom = next((m for m in missing if m["receiver_type"] == "CustomClass"), None)
        assert custom is not None
        assert custom["count"] == 5


class TestPerFileStats:
    """Tests for per-file statistics."""

    def test_per_file_tracking(self, metrics):
        """Track statistics per file."""
        # File A: mostly self-contained
        for _ in range(8):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="literal"),
                InferResult.from_literal(42),
                "file_a.py",
            )
        for _ in range(2):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="call"),
                InferResult.from_pyright("SomeType"),
                "file_a.py",
            )

        # File B: high Pyright dependency
        for _ in range(3):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="literal"),
                InferResult.from_literal("str"),
                "file_b.py",
            )
        for _ in range(7):
            metrics.record_inference(
                ExpressionTypeRequest(
                    expr_id="e",
                    kind="method_call",
                    receiver_type="DataFrame",
                    method_name="merge",
                ),
                InferResult.from_pyright("DataFrame"),
                "file_b.py",
            )

        report = metrics.get_coverage_report()

        # file_b should be in top files by Pyright usage
        top_files = report.get("top_files_by_pyright", {})
        assert "file_b.py" in top_files
        assert top_files["file_b.py"]["pyright_rate"] == 0.7

    def test_high_fallback_files_in_gap_analysis(self, metrics):
        """High fallback files appear in gap analysis."""
        # Create file with >20% Pyright dependency
        for _ in range(5):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="literal"),
                InferResult.from_literal(42),
                "high_fallback.py",
            )
        for _ in range(5):
            metrics.record_inference(
                ExpressionTypeRequest(
                    expr_id="e",
                    kind="method_call",
                    receiver_type="pd.Series",
                    method_name="apply",
                ),
                InferResult.from_pyright("Series"),
                "high_fallback.py",
            )

        gaps = metrics.get_gap_analysis()
        high_files = gaps["high_fallback_files"]

        assert any(f["file"] == "high_fallback.py" for f in high_files)


class TestGapAnalysis:
    """Tests for gap analysis and recommendations."""

    def test_recommendations_generated(self, metrics):
        """Recommendations are generated based on gaps."""
        # Add missing methods
        for _ in range(20):
            metrics.record_inference(
                ExpressionTypeRequest(
                    expr_id="e",
                    kind="method_call",
                    receiver_type="numpy.ndarray",
                    method_name="reshape",
                ),
                InferResult.from_pyright("ndarray"),
                "analysis.py",
            )

        gaps = metrics.get_gap_analysis()

        assert len(gaps["recommendations"]) > 0
        # Should recommend adding numpy.ndarray.reshape
        rec = gaps["recommendations"][0]
        assert "numpy.ndarray" in rec or "reshape" in rec

    def test_by_receiver_type_analysis(self):
        """Aggregate gaps by receiver type."""
        # Use a fresh instance
        metrics = InferenceMetrics()

        # Multiple methods missing for same type
        for method in ["groupby", "merge", "pivot", "join"]:
            for _ in range(10):
                metrics.record_inference(
                    ExpressionTypeRequest(
                        expr_id="e",
                        kind="method_call",
                        receiver_type="DataFrame",
                        method_name=method,
                    ),
                    InferResult.from_pyright("SomeType"),
                    "test.py",
                )

        gaps = metrics.get_gap_analysis()
        by_receiver = gaps["by_receiver_type"]

        assert "DataFrame" in by_receiver
        assert by_receiver["DataFrame"] == 40  # 4 methods × 10 calls


class TestJsonExport:
    """Tests for JSON export functionality."""

    def test_export_to_json(self, metrics):
        """Export metrics to JSON file."""
        # Add some data
        metrics.record_inference(
            ExpressionTypeRequest(expr_id="e", kind="literal"),
            InferResult.from_literal(42),
            "test.py",
        )
        metrics.record_inference(
            ExpressionTypeRequest(
                expr_id="e",
                kind="method_call",
                receiver_type="str",
                method_name="center",
            ),
            InferResult.from_pyright("str"),
            "test.py",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            metrics.export_to_json(temp_path)

            # Read and verify
            with open(temp_path) as f:
                data = json.load(f)

            assert "timestamp" in data
            assert "coverage_report" in data
            assert "gap_analysis" in data
            assert "fallback_summary" in data
            assert data["coverage_report"]["total_inferences"] == 2
        finally:
            temp_path.unlink(missing_ok=True)


class TestFallbackSummary:
    """Tests for fallback summary."""

    def test_fallback_by_kind(self, metrics):
        """Group fallbacks by expression kind."""
        # Method calls
        for _ in range(5):
            metrics.record_inference(
                ExpressionTypeRequest(
                    expr_id="e",
                    kind="method_call",
                    receiver_type="T",
                    method_name="m",
                ),
                InferResult.from_pyright("T"),
                "test.py",
            )

        # Regular calls
        for _ in range(3):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="call"),
                InferResult.from_pyright("R"),
                "test.py",
            )

        summary = metrics.get_fallback_summary()
        assert summary["by_kind"]["method_call"] == 5
        assert summary["by_kind"]["call"] == 3

    def test_recent_fallbacks(self, metrics):
        """Recent fallbacks are tracked."""
        for i in range(15):
            metrics.record_inference(
                ExpressionTypeRequest(
                    expr_id=f"e_{i}",
                    kind="method_call",
                    receiver_type=f"Type{i}",
                    method_name="method",
                ),
                InferResult.from_pyright("Result"),
                "test.py",
            )

        summary = metrics.get_fallback_summary()
        recent = summary["recent"]

        # Should only keep last 10
        assert len(recent) == 10
        # Most recent should be Type14
        assert recent[-1]["receiver_type"] == "Type14"


class TestMetricsReset:
    """Tests for metrics reset."""

    def test_reset_clears_all(self, metrics):
        """Reset clears all metrics."""
        # Add data
        for _ in range(10):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="literal"),
                InferResult.from_literal(42),
                "test.py",
            )

        metrics.reset()

        report = metrics.get_coverage_report()
        assert report["total_inferences"] == 0

        gaps = metrics.get_gap_analysis()
        assert len(gaps["missing_methods"]) == 0


class TestCoverageRates:
    """Tests for coverage rate calculations."""

    def test_mixed_sources(self, metrics):
        """Calculate rates with multiple sources."""
        # 5 annotations
        for _ in range(5):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", var_name="x", kind="var"),
                InferResult.from_annotation("int"),
                "test.py",
            )

        # 3 literals
        for _ in range(3):
            metrics.record_inference(
                ExpressionTypeRequest(expr_id="e", kind="literal"),
                InferResult.from_literal(42),
                "test.py",
            )

        # 1 Pyright
        metrics.record_inference(
            ExpressionTypeRequest(expr_id="e", kind="call"),
            InferResult.from_pyright("SomeType"),
            "test.py",
        )

        # 1 unknown
        metrics.record_inference(
            ExpressionTypeRequest(expr_id="e", kind="attr"),
            InferResult.unknown(),
            "test.py",
        )

        report = metrics.get_coverage_report()

        assert report["total_inferences"] == 10
        assert report["self_contained_rate"] == 0.8  # 8/10
        assert report["pyright_fallback_rate"] == 0.1  # 1/10
        assert report["unknown_rate"] == 0.1  # 1/10

        assert report["by_source"]["annotation"] == 0.5  # 5/10
        assert report["by_source"]["literal"] == 0.3  # 3/10
