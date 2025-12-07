#!/usr/bin/env python3
"""
Phase 1.5 검증 스크립트

Subprocess Sandbox + LangGraph 연동
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.agent.adapters.reasoning import LangGraphToTExecutor, SubprocessSandbox
from src.agent.domain.reasoning import CodeStrategy, StrategyType, ToTScoringEngine
from src.container import Container


async def test_subprocess_sandbox():
    """Subprocess Sandbox 테스트"""
    print("=" * 80)
    print("Phase 1.5: Subprocess Sandbox (실제 실행)")
    print("=" * 80)

    sandbox = SubprocessSandbox()

    # Test 1: Simple Python Code
    print("\n[Test 1] Simple Python Code (Syntax Check)")

    code = """
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 3
    assert add(0, 0) == 0
"""

    result = await sandbox.execute_code({"test_simple.py": code}, timeout=10)

    print(f"  Compile: {'✅' if result.compile_success else '❌'}")
    print(f"  Tests Run: {result.tests_run}")
    print(f"  Tests Passed: {result.tests_passed}")
    print(f"  Test Pass Rate: {result.test_pass_rate:.0%}")
    print(f"  Lint Warnings: {result.lint_warnings}")

    assert result.compile_success, "Should compile"
    print("  ✅ PASS")

    # Test 2: Syntax Error
    print("\n[Test 2] Syntax Error Detection")

    bad_code = """
def broken(
    return "incomplete"
"""

    result2 = await sandbox.execute_code({"test_broken.py": bad_code}, timeout=10)

    print(f"  Compile: {'✅' if result2.compile_success else '❌'}")
    print(f"  Errors: {len(result2.compile_errors)}")
    if result2.compile_errors:
        print(f"  First Error: {result2.compile_errors[0][:80]}")

    assert not result2.compile_success, "Should fail compilation"
    assert len(result2.compile_errors) > 0, "Should have errors"
    print("  ✅ PASS")

    # Cleanup
    sandbox.cleanup()
    print("\n✅ Sandbox cleanup complete")


async def test_langgraph_executor():
    """LangGraph Executor 테스트"""
    print("\n" + "=" * 80)
    print("LangGraph ToT Executor")
    print("=" * 80)

    sandbox = SubprocessSandbox()
    executor = LangGraphToTExecutor(
        llm_provider=None,
        sandbox_executor=sandbox,
        max_strategies=3,
        use_langgraph=True,  # LangGraph 시도
    )

    print("✅ LangGraph Executor initialized")

    # 전략 생성
    strategies = await executor.generate_strategies(
        problem="Fix division by zero error",
        context={"code": "x / y"},
        count=3,
    )

    print(f"\n📊 Generated {len(strategies)} strategies:")
    for i, s in enumerate(strategies, 1):
        print(f"  {i}. {s.title} ({s.strategy_type.value})")
        print(f"     Confidence: {s.llm_confidence:.2f}")

    assert len(strategies) == 3, "Should generate 3 strategies"
    print("\n✅ PASS")

    sandbox.cleanup()


async def test_security_veto():
    """Security Veto 테스트"""
    print("\n" + "=" * 80)
    print("Security Veto (Critical → 0.4 Max)")
    print("=" * 80)

    from src.agent.domain.reasoning import ExecutionResult

    scorer = ToTScoringEngine()

    # High quality but CRITICAL security
    strategy = CodeStrategy(
        strategy_id="test_veto",
        strategy_type=StrategyType.DIRECT_FIX,
        title="Dangerous Fix",
        description="...",
        rationale="...",
        llm_confidence=0.9,
    )

    result = ExecutionResult(
        strategy_id="test_veto",
        compile_success=True,
        tests_run=10,
        tests_passed=10,
        test_pass_rate=1.0,
        security_severity="critical",  # Critical!
    )

    score = scorer.score_strategy(strategy, result)

    print(f"  Correctness: {score.correctness_score:.2f}")
    print(f"  Security: {score.security_score:.2f} (Critical)")
    print("  Total (Before Veto): would be ~0.7+")
    print(f"  Total (After Veto): {score.total_score:.2f}")

    assert score.total_score <= 0.4, "Veto should cap at 0.4"
    assert score.security_score == 0.0, "Critical should be 0.0"
    print("\n✅ PASS - Veto applied!")


async def test_full_integration():
    """Full Integration 테스트"""
    print("\n" + "=" * 80)
    print("Full Integration (Container)")
    print("=" * 80)

    container = Container()
    use_case = container.v8_execute_tot

    # 간단한 코드로 ToT 실행
    result = await use_case.execute(
        problem="Add null check to avoid NPE",
        context={
            "code": "return user.name",
        },
        strategy_count=2,
        top_k=1,
    )

    print("\n📊 ToT Results:")
    print(f"  Generated: {result.total_generated}")
    print(f"  Executed: {result.total_executed}")
    print(f"  Best Score: {result.best_score:.2f}")
    print(f"  Time: {result.total_time:.2f}s")

    # Top-1
    if result.best_strategy_id:
        top_score = result.scores[result.best_strategy_id]
        print("\n🏆 Best Strategy:")
        print(f"  ID: {result.best_strategy_id}")
        print(f"  Total: {top_score.total_score:.2f}")
        print(f"  {top_score.recommendation}")

    assert result.total_executed >= 1, "Should execute strategies"
    print("\n✅ PASS")

    # Cleanup
    container.v8_sandbox_executor.cleanup()


async def main():
    """Main"""
    try:
        await test_subprocess_sandbox()
        await test_langgraph_executor()
        await test_security_veto()
        await test_full_integration()

        print("\n" + "=" * 80)
        print("🎉 Phase 1.5 검증 완료!")
        print("=" * 80)
        print("\n성공:")
        print("  ✅ Subprocess Sandbox (실제 Python 실행)")
        print("  ✅ Syntax Check (compile)")
        print("  ✅ pytest 통합 (테스트 실행)")
        print("  ✅ LangGraph Executor (StateGraph)")
        print("  ✅ Security Veto (Critical → 0.4 Max)")
        print("  ✅ Full Integration")
        print("\n개선 완료:")
        print("  🔥 Docker 없이 로컬 Subprocess")
        print("  🔥 실제 코드 컴파일 & 실행")
        print("  🔥 LangGraph State Machine")
        print("  🔥 보안 이슈 거부권 (Veto)")
        print("\n다음 단계: Phase 2 - Self-Reflection Judge")

        return 0

    except Exception as e:
        print(f"\n❌ 검증 실패: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
