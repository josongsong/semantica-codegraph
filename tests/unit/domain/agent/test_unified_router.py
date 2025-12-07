"""
UnifiedRouter 테스트
"""

import pytest

from src.agent.router.unified_router import UnifiedRouter


class TestUnifiedRouter:
    def setup_method(self):
        self.router = UnifiedRouter()

    def test_simple_symbol_query(self):
        """Simple symbol query - fast path"""
        plan = self.router.route("User class", budget_ms=500)

        assert plan.intent == "symbol"
        assert plan.complexity == "simple"
        assert plan.workflow_mode == "fast"
        assert plan.estimated_latency_ms < 500
        assert plan.strategy_path == ["symbol"]

    def test_complex_concept_query(self):
        """Complex concept query - deep path"""
        plan = self.router.route(
            "how does the authentication and authorization system work in this codebase",
            budget_ms=10000,
        )

        assert plan.intent in ["concept", "flow"]
        assert plan.complexity == "complex"
        assert plan.workflow_mode == "deep"
        assert plan.use_cross_encoder is True

    def test_medium_code_query(self):
        """Medium code query - standard path"""
        plan = self.router.route("find functions that process user input", budget_ms=3000)

        assert plan.intent == "code"
        assert plan.complexity in ["medium", "complex"]
        assert plan.workflow_mode == "standard"

    def test_budget_constraints(self):
        """Budget 제약 준수"""
        # 500ms budget
        plan = self.router.route("find User class", budget_ms=500)
        assert plan.estimated_latency_ms <= 500
        assert plan.workflow_mode == "fast"

        # 3000ms budget
        plan = self.router.route("find User class", budget_ms=3000)
        assert plan.workflow_mode == "standard"

        # 10000ms budget
        plan = self.router.route("find User class", budget_ms=10000)
        assert plan.workflow_mode == "deep"

    def test_adaptive_k_selection(self):
        """Adaptive K 선택"""
        # Simple query → small k
        plan = self.router.route("User", budget_ms=1000)
        assert plan.adaptive_k <= 20

        # Complex query → larger k
        plan = self.router.route("explain the architecture of the authentication system", budget_ms=5000)
        # adaptive_k는 complexity에 따라 달라짐
        assert plan.adaptive_k >= 10

    def test_advanced_features_activation(self):
        """Advanced features 조건부 활성화"""
        # Simple + low budget → no advanced features
        plan = self.router.route("User class", budget_ms=500)
        assert plan.use_hyde is False
        assert plan.use_cross_encoder is False

        # Complex + high budget → advanced features
        plan = self.router.route("explain how authentication works", budget_ms=10000)
        # concept + complex → HyDE 활성화
        if plan.intent == "concept":
            assert plan.use_hyde is True
        assert plan.use_cross_encoder is True
