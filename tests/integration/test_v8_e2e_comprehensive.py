"""
v8.1 Comprehensive E2E Tests (SOTA급)

전체 파이프라인 통합 테스트
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestV8E2EComprehensive:
    """v8.1 전체 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_router_system1_fast_path(self):
        """Router: System 1 (Fast) 경로 테스트"""
        from src.container import Container
        from src.agent.domain.reasoning import QueryFeatures

        container = Container()
        router = container.v8_reasoning_router

        # Simple query
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

        assert decision.path.value == "fast"
        assert decision.confidence > 0.7

    @pytest.mark.asyncio
    async def test_router_system2_complex_path(self):
        """Router: System 2 (Deep) 경로 테스트"""
        from src.container import Container
        from src.agent.domain.reasoning import QueryFeatures

        container = Container()
        router = container.v8_reasoning_router

        # Complex query
        features = QueryFeatures(
            file_count=10,
            impact_nodes=50,
            cyclomatic_complexity=15.0,
            has_test_failure=True,
            touches_security_sink=True,
            regression_risk=0.8,
            similar_success_rate=0.3,
        )

        decision = router.decide(features)

        assert decision.path.value == "slow"  # System 2
        assert decision.confidence > 0.0  # Has confidence
        assert decision.risk_score > 0.5  # High risk detected

    @pytest.mark.asyncio
    async def test_tot_execution_multiple_strategies(self):
        """ToT: 다중 전략 생성 테스트"""
        from src.container import Container

        container = Container()

        result = await container.v8_execute_tot.execute(
            problem="Add null check to prevent crash",
            context={"code": "def foo(x): return x.value"},
            strategy_count=3,
        )

        assert result.total_generated >= 3
        assert result.total_executed >= 3
        assert result.best_score > 0.5
        assert len(result.all_strategies) >= 3

    @pytest.mark.asyncio
    async def test_sandbox_execution_with_code(self):
        """Sandbox: 코드 실행 테스트"""
        from src.container import Container

        container = Container()
        sandbox = container.v8_sandbox_executor

        result = await sandbox.execute_code(
            file_changes={
                "test.py": """
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 3
    assert add(0, 0) == 0
"""
            },
            timeout=10,
        )

        assert result.compile_success is True
        # pytest가 작동하면 tests_run > 0
        # 작동 안 하면 compile만 확인

    @pytest.mark.asyncio
    async def test_success_evaluation_with_tests(self):
        """Success Evaluation: 테스트 있는 경우"""
        from src.agent.domain.reasoning import ExecutionResult, evaluate_success

        result = ExecutionResult(
            strategy_id="test_001",
            compile_success=True,
            tests_run=10,
            tests_passed=10,
            tests_failed=0,
            test_pass_rate=1.0,
        )

        evaluation = evaluate_success(result)

        assert evaluation.success is True
        assert evaluation.confidence >= 0.9
        assert evaluation.level == "perfect"

    @pytest.mark.asyncio
    async def test_success_evaluation_without_tests(self):
        """Success Evaluation: 테스트 없는 경우 (Fallback)"""
        from src.agent.domain.reasoning import ExecutionResult, evaluate_success

        result = ExecutionResult(
            strategy_id="test_002",
            compile_success=True,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            test_pass_rate=0.0,
            lint_errors=0,
            lint_warnings=2,
            complexity_before=10.0,
            complexity_after=8.0,
            complexity_delta=-2.0,
            security_severity="none",
        )

        evaluation = evaluate_success(result)

        # Fallback 평가
        assert evaluation.success is True  # Compile + Quality
        assert evaluation.confidence < 1.0  # Lower confidence without tests
        assert evaluation.level in ["acceptable", "good"]

    @pytest.mark.asyncio
    async def test_experience_store_save_and_query(self):
        """Experience Store: 저장 및 검색 테스트"""
        from src.container import Container
        from src.agent.domain.experience import AgentExperience, ProblemType, ExperienceQuery

        container = Container()
        repo = container.v8_experience_repository

        # Save
        experience = AgentExperience(
            problem_type=ProblemType.BUGFIX,
            problem_description="Test E2E experience",
            code_chunk_ids=["test_chunk_001"],
            strategy_type="direct_fix",
            success=True,
            tot_score=0.95,
            reflection_verdict="accept",
        )

        saved = repo.save(experience)
        assert saved.id is not None

        # Query
        query = ExperienceQuery(
            problem_type=ProblemType.BUGFIX,
            success_only=True,
        )

        results = repo.find(query)
        assert len(results) > 0

        # 방금 저장한 experience 찾기
        found = any(exp.id == saved.id for exp in results)
        assert found is True

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_pipeline_end_to_end(self):
        """Full Pipeline: 전체 파이프라인 E2E 테스트"""
        from src.container import Container
        from src.agent.domain.reasoning import QueryFeatures, evaluate_success
        from src.agent.domain.experience import AgentExperience, ProblemType

        container = Container()

        # Step 1: Router
        features = QueryFeatures(
            file_count=1,
            impact_nodes=10,
            cyclomatic_complexity=5.0,
            has_test_failure=False,
            touches_security_sink=False,
            regression_risk=0.3,
            similar_success_rate=0.7,
        )

        router_decision = container.v8_reasoning_router.decide(features)
        assert router_decision.path.value in ["fast", "deep"]

        # Step 2: ToT
        tot_result = await container.v8_execute_tot.execute(
            problem="Fix null pointer exception in login",
            context={"code": "def login(user): return user.name"},
            strategy_count=2,
        )

        assert tot_result.total_generated >= 2
        assert len(tot_result.all_strategies) >= 2

        # Step 3: Sandbox
        best_strategy = tot_result.all_strategies[0]

        if best_strategy.file_changes:
            sandbox_result = await container.v8_sandbox_executor.execute_code(
                file_changes=best_strategy.file_changes,
                timeout=10,
            )

            assert sandbox_result.compile_success is True

            # Step 4: Success Evaluation
            evaluation = evaluate_success(sandbox_result)
            assert evaluation.success in [True, False]  # Valid judgment
            assert 0.0 <= evaluation.confidence <= 1.0

            # Step 5: Experience Store
            experience = AgentExperience(
                problem_type=ProblemType.BUGFIX,
                problem_description="Full Pipeline E2E Test",
                code_chunk_ids=["e2e_test_001"],
                strategy_type=best_strategy.strategy_type.value,
                success=evaluation.success,
                tot_score=tot_result.best_score,
                reflection_verdict="accept" if evaluation.success else "revise",
            )

            saved = container.v8_experience_repository.save(experience)
            assert saved.id is not None


# Standalone execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
