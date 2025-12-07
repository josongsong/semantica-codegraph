"""
Dynamic Reasoning Router Tests

순수 Domain Logic 테스트 - Mock 불필요
"""

import pytest

from src.agent.domain.reasoning import (
    DynamicReasoningRouter,
    QueryFeatures,
    ReasoningPath,
)

# ============================================================================
# Fake Adapters (not Mocks)
# ============================================================================


class FakeComplexityAnalyzer:
    """Fake Complexity Analyzer for testing"""

    def __init__(self, cyclomatic=5.0, cognitive=3.0, impact_nodes=10):
        self.cyclomatic = cyclomatic
        self.cognitive = cognitive
        self.impact_nodes = impact_nodes

    def analyze_cyclomatic(self, code: str) -> float:
        return self.cyclomatic

    def analyze_cognitive(self, code: str) -> float:
        return self.cognitive

    def count_impact_nodes(self, file_path: str) -> int:
        return self.impact_nodes


class FakeRiskAssessor:
    """Fake Risk Assessor for testing"""

    def __init__(self, regression_risk=0.2, has_security_sink=False, has_test_failure=False):
        self.regression_risk = regression_risk
        self.has_security_sink = has_security_sink
        self.has_test_failure = has_test_failure

    def assess_regression_risk(self, problem_description: str, file_paths: list[str]) -> float:
        return self.regression_risk

    def check_security_sink(self, code: str) -> bool:
        return self.has_security_sink

    def check_test_failure(self, file_paths: list[str]) -> bool:
        return self.has_test_failure


# ============================================================================
# Domain Tests
# ============================================================================


class TestQueryFeatures:
    """QueryFeatures Domain Model 테스트"""

    def test_calculate_complexity_score_simple(self):
        """간단한 Query의 복잡도 점수"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=5,
            cyclomatic_complexity=2.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )

        complexity = features.calculate_complexity_score()

        # 1 file, 5 nodes, 2 complexity → 낮은 점수
        assert complexity < 0.2

    def test_calculate_complexity_score_complex(self):
        """복잡한 Query의 복잡도 점수"""
        features = QueryFeatures(
            file_count=8,
            impact_nodes=80,
            cyclomatic_complexity=40.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )

        complexity = features.calculate_complexity_score()

        # 8 files, 80 nodes, 40 complexity → 높은 점수
        assert complexity > 0.7

    def test_calculate_risk_score_safe(self):
        """안전한 Query의 위험도 점수"""
        features = QueryFeatures(
            file_count=1,
            impact_nodes=5,
            cyclomatic_complexity=2.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )

        risk = features.calculate_risk_score()

        assert risk < 0.2

    def test_calculate_risk_score_risky(self):
        """위험한 Query의 위험도 점수"""
        features = QueryFeatures(
            file_count=5,
            impact_nodes=50,
            cyclomatic_complexity=20.0,
            has_test_failure=True,
            touches_security_sink=True,
            regression_risk=0.6,
            similar_success_rate=0.9,
        )

        risk = features.calculate_risk_score()

        # regression_risk 0.6 * 0.5 + test failure 0.3 + security sink 0.2
        assert risk >= 0.8


class TestDynamicReasoningRouter:
    """DynamicReasoningRouter Domain Logic 테스트"""

    def test_simple_query_goes_to_system_1(self):
        """간단한 Query는 System 1으로 라우팅"""
        # Arrange
        router = DynamicReasoningRouter(
            complexity_analyzer=FakeComplexityAnalyzer(cyclomatic=2.0, cognitive=1.0, impact_nodes=5),
            risk_assessor=FakeRiskAssessor(regression_risk=0.1, has_security_sink=False, has_test_failure=False),
        )

        features = QueryFeatures(
            file_count=1,
            impact_nodes=5,
            cyclomatic_complexity=2.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )

        # Act
        decision = router.decide(features)

        # Assert
        assert decision.path == ReasoningPath.SYSTEM_1
        assert decision.is_fast_path()
        assert decision.confidence > 0.8
        assert decision.estimated_cost == 0.01
        assert decision.estimated_time == 5.0

    def test_complex_query_goes_to_system_2(self):
        """복잡한 Query는 System 2로 라우팅"""
        # Arrange
        router = DynamicReasoningRouter()

        features = QueryFeatures(
            file_count=8,
            impact_nodes=80,
            cyclomatic_complexity=40.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.2,
            similar_success_rate=0.9,
        )

        # Act
        decision = router.decide(features)

        # Assert
        assert decision.path == ReasoningPath.SYSTEM_2
        assert decision.is_slow_path()
        assert decision.confidence > 0.5
        assert decision.estimated_cost == 0.15
        assert decision.estimated_time == 45.0

    def test_risky_query_goes_to_system_2(self):
        """위험한 Query는 System 2로 라우팅"""
        # Arrange
        router = DynamicReasoningRouter()

        features = QueryFeatures(
            file_count=2,
            impact_nodes=10,
            cyclomatic_complexity=5.0,
            has_test_failure=True,
            touches_security_sink=True,
            regression_risk=0.6,
            similar_success_rate=0.9,
        )

        # Act
        decision = router.decide(features)

        # Assert
        assert decision.path == ReasoningPath.SYSTEM_2
        assert decision.risk_score > 0.8

    def test_previous_failures_penalty(self):
        """이전 실패가 많으면 System 2로"""
        # Arrange
        router = DynamicReasoningRouter()

        features = QueryFeatures(
            file_count=1,
            impact_nodes=5,
            cyclomatic_complexity=2.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
            previous_attempts=5,  # 많은 실패
        )

        # Act
        decision = router.decide(features)

        # Assert
        # 원래는 System 1이지만, 실패가 많아서 System 2
        assert decision.path == ReasoningPath.SYSTEM_2

    def test_threshold_tuning(self):
        """임계값 튜닝 가능"""
        # Arrange
        router = DynamicReasoningRouter()

        # Act
        router.adjust_thresholds(complexity_threshold=0.5, risk_threshold=0.6)

        config = router.get_current_config()

        # Assert
        assert config["complexity_threshold"] == 0.5
        assert config["risk_threshold"] == 0.6

    def test_threshold_validation(self):
        """임계값은 0.0 ~ 1.0 범위"""
        router = DynamicReasoningRouter()

        with pytest.raises(ValueError):
            router.adjust_thresholds(complexity_threshold=1.5)

        with pytest.raises(ValueError):
            router.adjust_thresholds(risk_threshold=-0.1)

    def test_decision_reasoning_text(self):
        """Decision에 reasoning 텍스트 포함"""
        router = DynamicReasoningRouter()

        features = QueryFeatures(
            file_count=1,
            impact_nodes=5,
            cyclomatic_complexity=2.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.1,
            similar_success_rate=0.9,
        )

        decision = router.decide(features)

        assert "Fast Path" in decision.reasoning or "Slow Path" in decision.reasoning
        assert f"{decision.complexity_score:.2f}" in decision.reasoning
        assert f"{decision.risk_score:.2f}" in decision.reasoning


# ============================================================================
# Integration Scenarios (여전히 Domain Layer)
# ============================================================================


class TestReasoningScenarios:
    """실제 시나리오 테스트"""

    def test_scenario_simple_bugfix(self):
        """시나리오: 간단한 버그 수정 (NPE 방어)"""
        router = DynamicReasoningRouter()

        # NPE 방어 코드 추가: 1개 파일, 낮은 복잡도, 안전
        features = QueryFeatures(
            file_count=1,
            impact_nodes=3,
            cyclomatic_complexity=1.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.05,
            similar_success_rate=0.95,
        )

        decision = router.decide(features)

        assert decision.path == ReasoningPath.SYSTEM_1
        assert decision.estimated_time < 10.0

    def test_scenario_complex_refactoring(self):
        """시나리오: 대규모 리팩토링"""
        router = DynamicReasoningRouter()

        # 10개 파일, 높은 복잡도, 위험
        features = QueryFeatures(
            file_count=10,
            impact_nodes=100,
            cyclomatic_complexity=45.0,
            has_test_failure=True,
            touches_security_sink=False,
            regression_risk=0.7,
            similar_success_rate=0.6,
        )

        decision = router.decide(features)

        assert decision.path == ReasoningPath.SYSTEM_2
        assert decision.estimated_time > 30.0

    def test_scenario_security_fix(self):
        """시나리오: 보안 취약점 수정"""
        router = DynamicReasoningRouter()

        # 보안 sink 접근: 무조건 System 2
        features = QueryFeatures(
            file_count=2,
            impact_nodes=10,
            cyclomatic_complexity=8.0,
            has_test_failure=False,
            touches_security_sink=True,  # Security!
            regression_risk=0.3,
            similar_success_rate=0.8,
        )

        decision = router.decide(features)

        assert decision.path == ReasoningPath.SYSTEM_2
        assert decision.risk_score > 0.4
