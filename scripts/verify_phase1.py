#!/usr/bin/env python3
"""
Phase 1 검증 스크립트

Tree-of-Thought Scoring Engine
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.agent.domain.reasoning import (
    ToTScoringEngine,
    CodeStrategy,
    ExecutionResult,
    StrategyType,
    ScoringWeights,
)
from src.container import Container


async def test_tot_scorer_direct():
    """ToT Scorer 직접 테스트"""
    print("=" * 80)
    print("Phase 1 검증: Tree-of-Thought Scoring Engine")
    print("=" * 80)

    # Scorer 생성
    scorer = ToTScoringEngine()
    print(f"\n✅ ToT Scorer initialized")
    print(f"   Weights: {scorer.weights}")

    # Test Strategy
    strategy = CodeStrategy(
        strategy_id="test_001",
        strategy_type=StrategyType.DIRECT_FIX,
        title="Direct NPE Fix",
        description="Add null check before usage",
        rationale="Defensive programming to prevent NullPointerException",
        llm_confidence=0.85,
    )

    # Test Execution Result (High Quality)
    result_good = ExecutionResult(
        strategy_id="test_001",
        compile_success=True,
        tests_run=10,
        tests_passed=10,
        tests_failed=0,
        test_pass_rate=1.0,
        lint_errors=0,
        lint_warnings=1,
        type_errors=0,
        security_issues=0,
        security_severity="none",
        complexity_before=15.0,
        complexity_after=12.0,
        complexity_delta=-3.0,
        execution_time=2.5,
    )

    # Score
    score = scorer.score_strategy(strategy, result_good)

    print(f"\n[Test 1] High Quality Strategy")
    print(f"  Correctness: {score.correctness_score:.2f}")
    print(f"  Quality: {score.quality_score:.2f}")
    print(f"  Security: {score.security_score:.2f}")
    print(f"  Maintainability: {score.maintainability_score:.2f}")
    print(f"  Performance: {score.performance_score:.2f}")
    print(f"  Total: {score.total_score:.2f}")
    print(f"  Confidence: {score.confidence:.2f}")
    print(f"  Recommendation: {score.recommendation}")

    assert score.total_score > 0.8, "High quality should score > 0.8"
    assert score.is_acceptable(), "Should be acceptable"
    print("  ✅ PASS")

    # Test 2: Low Quality
    result_bad = ExecutionResult(
        strategy_id="test_002",
        compile_success=True,
        tests_run=10,
        tests_passed=4,
        test_pass_rate=0.4,
        lint_errors=10,
        security_severity="high",
        complexity_delta=15.0,
    )

    strategy2 = CodeStrategy(
        strategy_id="test_002",
        strategy_type=StrategyType.REFACTOR_THEN_FIX,
        title="Complex Refactor",
        description="...",
        rationale="...",
        llm_confidence=0.5,
    )

    score2 = scorer.score_strategy(strategy2, result_bad)

    print(f"\n[Test 2] Low Quality Strategy")
    print(f"  Total: {score2.total_score:.2f}")
    print(f"  Security: {score2.security_score:.2f} (High severity)")
    print(f"  Recommendation: {score2.recommendation}")

    assert score2.total_score < 0.7, "Low quality should score < 0.7"
    assert not score2.is_acceptable(threshold=0.6), "Should NOT be acceptable"
    assert score2.security_score < 0.5, "High security issue should score low"
    print("  ✅ PASS")


async def test_tot_full_pipeline():
    """ToT Full Pipeline 테스트"""
    print("\n" + "=" * 80)
    print("ToT Full Pipeline (UseCase)")
    print("=" * 80)

    container = Container()
    use_case = container.v8_execute_tot

    print(f"✅ ExecuteToTUseCase from Container")

    # Execute
    result = await use_case.execute(
        problem="Fix NullPointerException in UserService.login()",
        context={
            "files": ["src/user/service.py"],
            "code": "def login(user): return user.name",
        },
        strategy_count=3,
        top_k=2,
    )

    print(f"\n📊 ToT Results:")
    print(f"  Generated: {result.total_generated}")
    print(f"  Executed: {result.total_executed}")
    print(f"  Passed: {result.total_passed}")
    print(f"  Best Score: {result.best_score:.2f}")
    print(f"  Time: {result.total_time:.2f}s")

    # Top-K
    top_k = result.get_top_k(2)
    print(f"\n🏆 Top {len(top_k)} Strategies:")
    for i, (sid, score) in enumerate(top_k, 1):
        print(f"  {i}. {sid}")
        print(f"     Total: {score.total_score:.2f}")
        print(f"     Confidence: {score.confidence:.2f}")
        print(f"     {score.recommendation}")

    assert result.total_executed >= 3, "Should execute all strategies"
    assert result.best_score > 0.0, "Should have best score"
    print("\n✅ PASS")


async def test_scoring_weights():
    """Scoring Weights 테스트"""
    print("\n" + "=" * 80)
    print("Scoring Weights Validation")
    print("=" * 80)

    weights = ScoringWeights.get_weights()
    print(f"Weights: {weights}")

    total = sum(weights.values())
    print(f"Total: {total:.3f}")

    assert ScoringWeights.validate(), "Weights must sum to 1.0"
    print("✅ PASS")


async def main():
    """Main"""
    try:
        await test_tot_scorer_direct()
        await test_tot_full_pipeline()
        await test_scoring_weights()

        print("\n" + "=" * 80)
        print("🎉 Phase 1 검증 완료!")
        print("=" * 80)
        print("\n성공:")
        print("  ✅ Domain Layer (CodeStrategy, ExecutionResult, StrategyScore)")
        print("  ✅ ToTScoringEngine (Multi-Criteria Scoring)")
        print("  ✅ LangGraphToTExecutor (Strategy Generation & Execution)")
        print("  ✅ ExecuteToTUseCase (Full Pipeline)")
        print("  ✅ Container DI 통합")
        print("  ✅ Scoring Weights (MCDM)")
        print("\nSOTA 특징:")
        print("  ⭐ Multi-Criteria Decision Making (5개 기준)")
        print("  ⭐ Weighted Sum Model (커스터마이징 가능)")
        print("  ⭐ Code Domain 특화 (Compile, Test, Lint, Security)")
        print("  ⭐ Async Parallel Execution")
        print("  ⭐ Hexagonal Architecture")
        print("\n다음 단계: Phase 2 - Self-Reflection Judge")

        return 0

    except Exception as e:
        print(f"\n❌ 검증 실패: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
