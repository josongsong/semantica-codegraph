"""
Test CWE Domain Ports (Pure Domain Logic)

Tests for domain models with NO infrastructure dependencies.
"""

from pathlib import Path

import pytest

from cwe.domain.ports import AnalysisResult, ConfusionMatrix, TestCase


class TestAnalysisResult:
    """Test AnalysisResult enum"""

    def test_values(self):
        """Base case: Enum has correct values"""
        assert AnalysisResult.VULNERABLE.value == "vulnerable"
        assert AnalysisResult.SAFE.value == "safe"
        assert AnalysisResult.ERROR.value == "error"

    def test_enum_comparison(self):
        """Base case: Enum comparison works"""
        result = AnalysisResult.VULNERABLE
        assert result == AnalysisResult.VULNERABLE
        assert result != AnalysisResult.SAFE


class TestConfusionMatrix:
    """Test ConfusionMatrix (Domain Model)"""

    # ========== BASE CASES ==========

    def test_init_valid(self):
        """Base case: Valid confusion matrix"""
        matrix = ConfusionMatrix(
            true_positive=8,
            false_positive=2,
            true_negative=5,
            false_negative=1,
            analysis_errors=0,
        )

        assert matrix.true_positive == 8
        assert matrix.false_positive == 2
        assert matrix.true_negative == 5
        assert matrix.false_negative == 1
        assert matrix.analysis_errors == 0

    def test_precision_calculation(self):
        """Base case: Precision calculation"""
        matrix = ConfusionMatrix(
            true_positive=8,
            false_positive=2,
            true_negative=5,
            false_negative=1,
        )

        assert matrix.precision == 0.8  # 8 / (8 + 2)

    def test_recall_calculation(self):
        """Base case: Recall calculation"""
        matrix = ConfusionMatrix(
            true_positive=8,
            false_positive=2,
            true_negative=5,
            false_negative=1,
        )

        assert matrix.recall == 8 / 9  # 8 / (8 + 1)

    def test_f1_score_calculation(self):
        """Base case: F1 score calculation"""
        matrix = ConfusionMatrix(
            true_positive=8,
            false_positive=2,
            true_negative=5,
            false_negative=1,
        )

        precision = 0.8
        recall = 8 / 9
        expected_f1 = 2 * (precision * recall) / (precision + recall)

        assert abs(matrix.f1_score - expected_f1) < 0.001

    # ========== EDGE CASES ==========

    def test_init_negative_value_raises(self):
        """Edge case: Negative values not allowed"""
        with pytest.raises(ValueError) as exc_info:
            ConfusionMatrix(
                true_positive=-1,  # ❌ Invalid
                false_positive=0,
                true_negative=0,
                false_negative=0,
            )

        assert "cannot be negative" in str(exc_info.value).lower()

    def test_precision_no_positive_predictions(self):
        """Edge case: Cannot calculate precision when no positive predictions"""
        matrix = ConfusionMatrix(
            true_positive=0,
            false_positive=0,  # No positive predictions
            true_negative=10,
            false_negative=5,
        )

        assert not matrix.can_calculate_precision

        with pytest.raises(ValueError) as exc_info:
            _ = matrix.precision

        error_msg = str(exc_info.value)
        assert "cannot calculate precision" in error_msg.lower()
        assert "no positive predictions" in error_msg.lower()

    def test_recall_no_actual_positives(self):
        """Edge case: Cannot calculate recall when no actual positives"""
        matrix = ConfusionMatrix(
            true_positive=0,
            false_positive=5,
            true_negative=10,
            false_negative=0,  # No actual positives
        )

        assert not matrix.can_calculate_recall

        with pytest.raises(ValueError) as exc_info:
            _ = matrix.recall

        error_msg = str(exc_info.value)
        assert "cannot calculate recall" in error_msg.lower()
        assert "no actual positives" in error_msg.lower()

    def test_f1_score_both_zero(self):
        """Edge case: F1 when both precision and recall are 0"""
        matrix = ConfusionMatrix(
            true_positive=0,
            false_positive=10,
            true_negative=10,
            false_negative=10,
        )

        # Precision and recall are both 0
        # F1 should be 0.0
        assert matrix.f1_score == 0.0

    # ========== CORNER CASES ==========

    def test_all_true_positives(self):
        """Corner case: Perfect detection (only TPs)"""
        matrix = ConfusionMatrix(
            true_positive=10,
            false_positive=0,
            true_negative=0,
            false_negative=0,
        )

        assert matrix.precision == 1.0
        assert matrix.recall == 1.0
        assert matrix.f1_score == 1.0

    def test_all_true_negatives(self):
        """Corner case: All safe files correctly identified"""
        matrix = ConfusionMatrix(
            true_positive=0,
            false_positive=0,
            true_negative=10,
            false_negative=0,
        )

        # Cannot calculate precision (no predictions)
        assert not matrix.can_calculate_precision
        # Cannot calculate recall (no actual positives)
        assert not matrix.can_calculate_recall

    def test_all_errors(self):
        """Corner case: All analyses failed"""
        matrix = ConfusionMatrix(
            true_positive=0,
            false_positive=0,
            true_negative=0,
            false_negative=0,
            analysis_errors=100,
        )

        assert matrix.total_cases == 100
        assert matrix.successful_analyses == 0

    def test_mixed_results_with_errors(self):
        """Corner case: Some successes, some errors"""
        matrix = ConfusionMatrix(
            true_positive=5,
            false_positive=2,
            true_negative=3,
            false_negative=1,
            analysis_errors=4,
        )

        assert matrix.total_cases == 15
        assert matrix.successful_analyses == 11
        assert matrix.precision == 5 / 7
        assert matrix.recall == 5 / 6

    # ========== EXTREME CASES ==========

    def test_very_large_numbers(self):
        """Extreme case: Large test suite (10K+ files)"""
        matrix = ConfusionMatrix(
            true_positive=5000,
            false_positive=500,
            true_negative=4500,
            false_negative=100,
        )

        # Should handle without overflow
        assert matrix.total_cases == 10100
        assert 0 < matrix.precision < 1
        assert 0 < matrix.recall < 1
        assert 0 < matrix.f1_score < 1

    def test_immutability(self):
        """Extreme case: Verify immutability (frozen dataclass)"""
        matrix = ConfusionMatrix(
            true_positive=8,
            false_positive=2,
            true_negative=5,
            false_negative=1,
        )

        with pytest.raises(AttributeError):
            matrix.true_positive = 10  # Should raise - frozen


class TestTestCase:
    """Test TestCase domain model"""

    def test_init_valid(self, tmp_path):
        """Base case: Valid test case"""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")

        test_case = TestCase(
            file_path=test_file,
            is_vulnerable=True,
            cwe_id="CWE-89",
        )

        assert test_case.file_path == test_file
        assert test_case.is_vulnerable is True
        assert test_case.cwe_id == "CWE-89"

    def test_init_file_not_found_raises(self):
        """Edge case: File doesn't exist"""
        with pytest.raises(ValueError) as exc_info:
            TestCase(
                file_path=Path("/nonexistent/file.py"),
                is_vulnerable=True,
                cwe_id="CWE-89",
            )

        assert "not found" in str(exc_info.value).lower()

    def test_immutability(self, tmp_path):
        """Extreme case: Verify immutability"""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")

        test_case = TestCase(
            file_path=test_file,
            is_vulnerable=True,
            cwe_id="CWE-89",
        )

        with pytest.raises(AttributeError):
            test_case.is_vulnerable = False  # Should raise - frozen
