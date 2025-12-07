#!/usr/bin/env python3
"""
LLM Integration 검증

OpenAI로 실제 전략 생성
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.agent.adapters.llm.strategy_generator import (
    StrategyGeneratorLLM,
    StrategyGeneratorFactory,
)
from src.agent.domain.reasoning import StrategyType
from src.container import Container


async def test_strategy_generator():
    """Strategy Generator 테스트"""
    print("=" * 80)
    print("LLM Integration: Strategy Generator")
    print("=" * 80)

    # Generator 생성
    generator = StrategyGeneratorFactory.create(use_llm=True)

    print(f"\n✅ Generator created")
    print(f"   Model: {generator.model}")
    print(f"   Has API Key: {bool(generator.api_key)}")
    print(f"   Has Client: {bool(generator.client)}")

    # 전략 생성
    problem = "Fix NullPointerException in UserService.login() method"
    context = {
        "code": """
def login(user):
    return user.name.upper()
""",
        "files": ["src/user/service.py"],
    }

    print(f"\n📝 Problem: {problem}")
    print(f"   Code: {context['code'][:50]}...")

    # Direct Fix Strategy
    print(f"\n🤖 Generating strategy (direct_fix)...")

    strategy = await generator.generate_strategy(
        problem=problem,
        context=context,
        strategy_type=StrategyType.DIRECT_FIX,
        index=0,
    )

    print(f"\n✅ Strategy generated:")
    print(f"   ID: {strategy.strategy_id}")
    print(f"   Type: {strategy.strategy_type.value}")
    print(f"   Title: {strategy.title}")
    print(f"   Description: {strategy.description[:80]}...")
    print(f"   Rationale: {strategy.rationale[:80]}...")
    print(f"   Confidence: {strategy.llm_confidence:.2f}")

    assert len(strategy.title) > 0, "Should have title"
    assert strategy.llm_confidence > 0, "Should have confidence"
    print("\n✅ PASS")


async def test_tot_with_llm():
    """ToT + LLM 통합 테스트"""
    print("\n" + "=" * 80)
    print("ToT + LLM Integration")
    print("=" * 80)

    container = Container()
    use_case = container.v8_execute_tot

    print(f"\n✅ ExecuteToT UseCase from Container")

    # LLM으로 전략 생성
    result = await use_case.execute(
        problem="Add null check to prevent NullPointerException",
        context={
            "code": "def process(user): return user.name",
            "files": ["service.py"],
        },
        strategy_count=2,  # 2개만 (빠르게)
        top_k=1,
    )

    print(f"\n📊 ToT Results (with LLM):")
    print(f"  Generated: {result.total_generated}")
    print(f"  Executed: {result.total_executed}")
    print(f"  Best Score: {result.best_score:.2f}")
    print(f"  Time: {result.total_time:.2f}s")

    # Best Strategy
    if result.best_strategy_id:
        strategy = next((s for s in result.all_strategies if s.strategy_id == result.best_strategy_id), None)

        if strategy:
            print(f"\n🏆 Best Strategy (LLM-generated):")
            print(f"  Title: {strategy.title}")
            print(f"  Type: {strategy.strategy_type.value}")
            print(f"  Confidence: {strategy.llm_confidence:.2f}")

    assert result.total_executed >= 1, "Should execute"
    print("\n✅ PASS")


async def test_fallback_mode():
    """Fallback 모드 테스트 (API Key 없이)"""
    print("\n" + "=" * 80)
    print("Fallback Mode (No API Key)")
    print("=" * 80)

    # No API Key
    generator = StrategyGeneratorLLM(api_key=None)

    print(f"\n✅ Generator (Fallback mode)")
    print(f"   Has Client: {bool(generator.client)}")

    strategy = await generator.generate_strategy(
        problem="Test problem",
        context={},
        strategy_type=StrategyType.TEST_DRIVEN,
        index=0,
    )

    print(f"\n✅ Fallback strategy:")
    print(f"   ID: {strategy.strategy_id}")
    print(f"   Type: {strategy.strategy_type.value}")

    assert "fallback" in strategy.strategy_id, "Should use fallback"
    print("\n✅ PASS (Fallback works)")


async def main():
    """Main"""
    try:
        await test_strategy_generator()
        await test_tot_with_llm()
        await test_fallback_mode()

        print("\n" + "=" * 80)
        print("🎉 LLM Integration 검증 완료!")
        print("=" * 80)
        print("\n성공:")
        print("  ✅ Strategy Generator (OpenAI)")
        print("  ✅ LLM으로 전략 생성")
        print("  ✅ ToT Executor 통합")
        print("  ✅ Fallback 모드")
        print("\nLLM 활용:")
        print("  🤖 문제 분석 → 전략 생성")
        print("  🤖 Context 기반 맞춤형")
        print("  🤖 Confidence 점수")
        print("\n전체 파이프라인:")
        print("  User Problem")
        print("    ↓")
        print("  Router → System 1/2")
        print("    ↓")
        print("  LLM → 3-5 Strategies")
        print("    ↓")
        print("  Sandbox → Execute")
        print("    ↓")
        print("  Scorer → Multi-Criteria")
        print("    ↓")
        print("  Reflection → ACCEPT/REVISE")
        print("    ↓")
        print("  Experience → Save")
        print("\n🔥 v8.1 COMPLETE!")

        return 0

    except Exception as e:
        print(f"\n❌ 검증 실패: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
