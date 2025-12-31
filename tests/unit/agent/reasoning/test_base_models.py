"""
Agent Reasoning Base Models Tests

Test Coverage:
- Enums: ReasoningPath
- Domain Models: QueryFeatures
- Business Logic: calculate_complexity_score, calculate_risk_score
"""

from datetime import datetime

import pytest

from apps.orchestrator.orchestrator.shared.reasoning.base.models import (
    QueryFeatures,
    ReasoningPath,
)


class TestReasoningPath:
    """ReasoningPath enum tests"""

    def test_system_1_fast(self):
        """System 1 is fast path"""
        assert ReasoningPath.SYSTEM_1.value == "fast"

    def test_system_2_slow(self):
        """System 2 is slow path"""
        assert ReasoningPath.SYSTEM_2.value == "slow"

    def test_enum_count(self):
        """Two reasoning paths"""
        assert len(ReasoningPath) == 2


class TestQueryFeatures:
    """QueryFeatures model tests"""

    def test_create_basic_features(self):
        """Create basic query features"""
        features = QueryFeatures(
            file_count=5,
            impact_nodes=20,
            cyclomatic_complexity=10.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )
        assert features.file_count == 5
        assert features.impact_nodes == 20
        assert features.previous_attempts == 0  # default

    def test_timestamp_auto_generated(self):
        """Timestamp is auto-generated"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        assert isinstance(features.timestamp, datetime)


class TestCalculateComplexityScore:
    """Complexity score calculation tests"""

    def test_minimal_complexity(self):
        """Minimal complexity returns low score"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_complexity_score()
        assert 0.0 <= score <= 0.3  # Low complexity

    def test_high_complexity(self):
        """High complexity returns high score"""
        features = QueryFeatures(
            file_count=20,  # > 10, caps at 1.0
            impact_nodes=200,  # > 100, caps at 1.0
            cyclomatic_complexity=100.0,  # > 50, caps at 1.0
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_complexity_score()
        assert score == pytest.approx(1.0)  # Capped at max

    def test_medium_complexity(self):
        """Medium complexity returns mid-range score"""
        features = QueryFeatures(
            file_count=5,  # 0.5
            impact_nodes=50,  # 0.5
            cyclomatic_complexity=25.0,  # 0.5
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_complexity_score()
        assert 0.4 <= score <= 0.6


class TestCalculateRiskScore:
    """Risk score calculation tests"""

    def test_no_risk(self):
        """No risk factors returns low score"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_risk_score()
        assert score == pytest.approx(0.0)

    def test_test_failure_adds_risk(self):
        """Test failure adds 0.3 to risk"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=True,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_risk_score()
        assert score == pytest.approx(0.3)

    def test_security_sink_adds_risk(self):
        """Security sink adds 0.2 to risk"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=True,
            regression_risk=0.0,
            similar_success_rate=1.0,
        )
        score = features.calculate_risk_score()
        assert score == pytest.approx(0.2)

    def test_previous_attempts_adds_risk(self):
        """Previous attempts > 2 adds risk"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=1.0,
            previous_attempts=5,
        )
        score = features.calculate_risk_score()
        # 0.1 * (5 - 2) = 0.3
        assert score == pytest.approx(0.3)

    def test_combined_risk_factors(self):
        """Multiple risk factors combine"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=True,  # +0.3
            touches_security_sink=True,  # +0.2
            regression_risk=0.5,  # * 0.5 = 0.25
            similar_success_rate=0.5,
        )
        score = features.calculate_risk_score()
        # 0.25 + 0.3 + 0.2 = 0.75
        assert score == pytest.approx(0.75)

    def test_high_regression_risk(self):
        """High regression risk dominates"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=1,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=1.0,  # Max
            similar_success_rate=0.0,
        )
        score = features.calculate_risk_score()
        # 1.0 * 0.5 = 0.5
        assert score == pytest.approx(0.5)


class TestEdgeCases:
    """Edge case tests"""

    def test_zero_all_features(self):
        """All zero values"""
        features = QueryFeatures(
            file_count=0,
            impact_nodes=0,
            cyclomatic_complexity=0.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.0,
            similar_success_rate=0.0,
        )
        assert features.calculate_complexity_score() == pytest.approx(0.0)
        assert features.calculate_risk_score() == pytest.approx(0.0)

    def test_negative_values(self):
        """Negative values (edge case)"""
        features = QueryFeatures(
            file_count=-1,  # Invalid but model doesn't validate
            impact_nodes=-10,
            cyclomatic_complexity=-5.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=-0.5,
            similar_success_rate=-1.0,
        )
        # Should not crash
        _ = features.calculate_complexity_score()
        _ = features.calculate_risk_score()

    def test_very_large_values(self):
        """Very large values (capped)"""
        features = QueryFeatures(
            file_count=1000000,
            impact_nodes=1000000,
            cyclomatic_complexity=1000000.0,
            has_test_failure=True,
            touches_security_sink=True,
            regression_risk=1.0,
            similar_success_rate=0.0,
            previous_attempts=100,
        )
        complexity = features.calculate_complexity_score()
        risk = features.calculate_risk_score()
        # Should be capped appropriately
        assert complexity <= 1.0
        assert risk >= 0.0
