"""
ReasoningAdapter Tests (RFC-027)

Test coverage:
- ReasoningResult → Conclusion conversion
- RiskLevel → Coverage mapping
- Breaking changes → Counterevidence
- Recommended actions → Recommendation
- Edge cases (no recommendations, many breaking changes)

Testing Strategy:
- Base case (normal reasoning result)
- Edge cases (empty, extreme values)
- Risk level mapping (all levels)
"""

from datetime import datetime

import pytest

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
from codegraph_runtime.llm_arbitration.infrastructure.adapters.reasoning_adapter import (
    ReasoningAdapter,
)
from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningContext, ReasoningResult
from codegraph_engine.reasoning_engine.domain.impact_models import ImpactLevel
from codegraph_engine.reasoning_engine.domain.speculative_models import RiskLevel

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def reasoning_result_safe():
    """ReasoningResult with safe risk"""
    return ReasoningResult(
        summary="Analysis complete: no issues",
        total_risk=RiskLevel.SAFE,
        total_impact=ImpactLevel.LOW,
        breaking_changes=[],
        impacted_symbols=["func1", "func2"],
        recommended_actions=["Continue with changes"],
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )


@pytest.fixture
def reasoning_result_breaking():
    """ReasoningResult with breaking changes"""
    return ReasoningResult(
        summary="Breaking changes detected",
        total_risk=RiskLevel.BREAKING,
        total_impact=ImpactLevel.HIGH,
        breaking_changes=["Signature changed: func1", "Return type changed: func2"],
        impacted_symbols=["func1", "func2", "func3"],
        recommended_actions=["Review breaking changes", "Update tests", "Notify consumers"],
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )


# ============================================================
# Base Case Tests
# ============================================================


def test_to_conclusion_safe(reasoning_result_safe):
    """Test conversion with safe risk (base case)"""
    adapter = ReasoningAdapter()

    conclusion = adapter.to_conclusion(reasoning_result_safe)

    # Summary (adapter uses result.summary directly)
    assert "Analysis complete" in conclusion.reasoning_summary

    # Coverage (based on ImpactLevel.LOW → 0.9)
    assert conclusion.coverage == 0.9

    # No counterevidence (adapter doesn't map breaking_changes to counterevidence)
    assert len(conclusion.counterevidence) == 0

    # Recommendation
    assert "Continue with changes" in conclusion.recommendation


def test_to_conclusion_breaking(reasoning_result_breaking):
    """Test conversion with breaking changes"""
    adapter = ReasoningAdapter()

    conclusion = adapter.to_conclusion(reasoning_result_breaking)

    # Summary (adapter uses result.summary directly)
    assert "Breaking changes detected" in conclusion.reasoning_summary

    # Coverage (based on ImpactLevel.HIGH → 0.5)
    assert conclusion.coverage == 0.5

    # Counterevidence (adapter sets empty - breaking_changes not mapped)
    assert len(conclusion.counterevidence) == 0

    # Recommendation
    assert "Review breaking changes" in conclusion.recommendation
    assert "Update tests" in conclusion.recommendation


# ============================================================
# Risk Level Mapping Tests
# ============================================================


@pytest.mark.parametrize(
    "impact_level,expected_coverage",
    [
        (ImpactLevel.NONE, 1.0),
        (ImpactLevel.LOW, 0.9),
        (ImpactLevel.MEDIUM, 0.7),
        (ImpactLevel.HIGH, 0.5),
        (ImpactLevel.CRITICAL, 0.3),
    ],
)
def test_impact_to_coverage_mapping(impact_level, expected_coverage):
    """Test impact level → coverage mapping (all levels)

    Note: Adapter uses total_impact for coverage, not total_risk
    """
    result = ReasoningResult(
        summary="Test",
        total_risk=RiskLevel.LOW,
        total_impact=impact_level,
        breaking_changes=[],
        impacted_symbols=[],
        recommended_actions=[],
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )

    adapter = ReasoningAdapter()
    conclusion = adapter.to_conclusion(result)

    assert conclusion.coverage == expected_coverage


# ============================================================
# Edge Cases
# ============================================================


def test_no_recommended_actions():
    """Test with no recommended actions"""
    result = ReasoningResult(
        summary="Analysis complete",
        total_risk=RiskLevel.LOW,
        total_impact=ImpactLevel.LOW,
        breaking_changes=[],
        impacted_symbols=[],
        recommended_actions=[],  # Empty
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )

    adapter = ReasoningAdapter()
    conclusion = adapter.to_conclusion(result)

    assert conclusion.recommendation == "No specific recommendations"


def test_many_breaking_changes():
    """Test with many breaking changes (>5)

    Note: Current adapter does NOT map breaking_changes to counterevidence
    This test verifies the adapter behavior (empty counterevidence)
    """
    # 10 breaking changes
    breaking = [f"Breaking change {i}" for i in range(10)]

    result = ReasoningResult(
        summary="Many breaking changes",
        total_risk=RiskLevel.BREAKING,
        total_impact=ImpactLevel.HIGH,
        breaking_changes=breaking,
        impacted_symbols=[],
        recommended_actions=["Review all"],
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )

    adapter = ReasoningAdapter()
    conclusion = adapter.to_conclusion(result)

    # Adapter currently does not map breaking_changes → counterevidence
    assert len(conclusion.counterevidence) == 0
    # Recommendation is present
    assert "Review all" in conclusion.recommendation


def test_invalid_reasoning_result_type():
    """Test with invalid reasoning_result type"""
    adapter = ReasoningAdapter()

    with pytest.raises(TypeError, match="Expected ReasoningResult"):
        adapter.to_conclusion("invalid")


# ============================================================
# Stateless Tests
# ============================================================


def test_adapter_stateless(reasoning_result_safe):
    """Test adapter is stateless (thread-safe)"""
    adapter = ReasoningAdapter()

    # Call twice
    conclusion1 = adapter.to_conclusion(reasoning_result_safe)
    conclusion2 = adapter.to_conclusion(reasoning_result_safe)

    # Same input → same output (deterministic)
    assert conclusion1.reasoning_summary == conclusion2.reasoning_summary
    assert conclusion1.coverage == conclusion2.coverage
