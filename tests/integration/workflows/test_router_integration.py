"""Router 통합 테스트 (Day 9-10)

IntentClassifier + ConfidenceScorer + Router 통합 검증
"""

import asyncio
import sys
from pathlib import Path

# PYTHONPATH 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.router.confidence_scorer import ConfidenceScorer
from src.agent.router.models import Intent, IntentResult

# Router만 import (IntentClassifier는 Mock으로 대체)
from src.agent.router.router import Router


async def test_router_basic():
    """Router 기본 동작 테스트 (Mock Classifier)"""
    print("🧪 Testing Router Basic...")

    # Mock Classifier (LLM 없이 테스트)
    class MockClassifier:
        async def classify(self, user_input, context=None):
            # "fix", "bug" 키워드 → FIX_BUG
            if "fix" in user_input.lower() or "bug" in user_input.lower():
                return IntentResult(
                    intent=Intent.FIX_BUG,
                    confidence=0.85,
                    reasoning="Keywords detected: fix, bug",
                    context=context or {},
                )
            else:
                return IntentResult(
                    intent=Intent.UNKNOWN, confidence=0.4, reasoning="No clear intent", context=context or {}
                )

    classifier = MockClassifier()
    scorer = ConfidenceScorer()
    router = Router(classifier, scorer)

    # Test 1: 명확한 버그 수정
    result = await router.route("Fix the bug in calculate_total")

    assert result.intent == Intent.FIX_BUG
    assert result.context["final_confidence"] >= 0.8  # LLM (0.85) + boost
    assert not result.context["should_ask_user"]  # High confidence
    assert result.context["confidence_level"] in ["high", "medium"]

    print("  ✅ Clear intent: FIX_BUG")
    print(f"     Confidence: {result.context['final_confidence']:.2f}")
    print(f"     Level: {result.context['confidence_level']}")

    # Test 2: 모호한 요청
    result = await router.route("Do something")

    assert result.intent == Intent.UNKNOWN
    assert result.context["final_confidence"] < 0.7
    assert result.context["should_ask_user"]  # Low confidence
    assert result.context["confidence_level"] == "low"

    print("  ✅ Unclear intent: UNKNOWN")
    print(f"     Confidence: {result.context['final_confidence']:.2f}")
    print(f"     Should ask: {result.context['should_ask_user']}")

    print("  ✅ Router Basic 통과!\n")


async def test_router_with_context():
    """Router에 컨텍스트 전달 테스트"""
    print("🧪 Testing Router with Context...")

    class MockClassifier:
        async def classify(self, user_input, context=None):
            return IntentResult(intent=Intent.FIX_BUG, confidence=0.75, reasoning="Test", context=context or {})

    router = Router(MockClassifier())

    # 컨텍스트 전달
    result = await router.route(
        "Fix bug", context={"repo_id": "my_repo", "file_path": "src/app.py", "user_id": "user123"}
    )

    # 컨텍스트가 유지되는지 확인
    assert result.context["repo_id"] == "my_repo"
    assert result.context["file_path"] == "src/app.py"
    assert result.context["user_id"] == "user123"
    assert "user_input" in result.context  # Router가 추가
    assert "final_confidence" in result.context  # Router가 추가

    print("  ✅ Context 전달 및 유지")
    print(f"     Keys: {list(result.context.keys())}")
    print("  ✅ Router with Context 통과!\n")


async def test_router_confidence_scenarios():
    """Router 신뢰도 시나리오 테스트"""
    print("🧪 Testing Router Confidence Scenarios...")

    class ConfigurableClassifier:
        def __init__(self, confidence):
            self.confidence = confidence

        async def classify(self, user_input, context=None):
            return IntentResult(
                intent=Intent.FIX_BUG, confidence=self.confidence, reasoning="Test", context=context or {}
            )

    scorer = ConfidenceScorer()

    # Scenario 1: High confidence (0.9)
    router_high = Router(ConfigurableClassifier(0.9), scorer)
    result_high = await router_high.route("Fix bug")

    assert not result_high.context["should_ask_user"]
    assert result_high.context["confidence_level"] == "high"

    print("  ✅ High confidence (0.9): Execute immediately")

    # Scenario 2: Medium confidence (0.7)
    router_medium = Router(ConfigurableClassifier(0.7), scorer)
    result_medium = await router_medium.route("Fix bug")

    # 0.7 == threshold → borderline
    # Heuristic이 없으면 should_ask_user == False (경계선)
    print(f"  ✅ Medium confidence (0.7): {result_medium.context['confidence_level']}")

    # Scenario 3: Low confidence (0.5)
    router_low = Router(ConfigurableClassifier(0.5), scorer)
    result_low = await router_low.route("Do something")  # No keywords → no boost

    assert result_low.context["should_ask_user"]
    assert result_low.context["confidence_level"] == "low"

    print("  ✅ Low confidence (0.5): Ask user")

    print("  ✅ Router Confidence Scenarios 통과!\n")


async def test_router_end_to_end():
    """End-to-End 통합 테스트"""
    print("🧪 Testing Router End-to-End...")

    # Real components (but Mock Classifier)
    class MockClassifier:
        async def classify(self, user_input, context=None):
            user_lower = user_input.lower()

            if "fix" in user_lower and "bug" in user_lower:
                return IntentResult(
                    intent=Intent.FIX_BUG,
                    confidence=0.6,  # Borderline
                    reasoning="Bug fix keywords detected",
                    context=context or {},
                )
            elif "add" in user_lower and "feature" in user_lower:
                return IntentResult(
                    intent=Intent.ADD_FEATURE,
                    confidence=0.7,  # Medium
                    reasoning="Feature addition detected",
                    context=context or {},
                )
            else:
                return IntentResult(
                    intent=Intent.UNKNOWN, confidence=0.3, reasoning="Unclear intent", context=context or {}
                )

    classifier = MockClassifier()
    scorer = ConfidenceScorer(enable_heuristic=True)
    router = Router(classifier, scorer)

    # Test 1: "Fix the bug" with keywords
    result1 = await router.route("Fix the critical bug in payment module")

    # LLM: 0.6 + Heuristic (bug, fix): +0.2 = 0.8
    # Threshold (FIX_BUG): 0.7
    # 0.8 > 0.7 → Execute immediately
    assert result1.intent == Intent.FIX_BUG
    assert result1.context["final_confidence"] >= 0.7
    assert not result1.context["should_ask_user"]

    print("  ✅ Scenario 1: Fix bug with keywords")
    print(f"     Intent: {result1.intent.value}")
    print(f"     Confidence: {result1.context['final_confidence']:.2f}")
    print("     Decision: Execute")

    # Test 2: "Add feature" - high threshold
    result2 = await router.route("Add a new feature for user authentication")

    # LLM: 0.7 + Heuristic (add, feature): +0.2 = 0.9
    # Threshold (ADD_FEATURE): 0.8
    # 0.9 > 0.8 → Execute
    assert result2.intent == Intent.ADD_FEATURE
    assert result2.context["final_confidence"] >= 0.8

    print("  ✅ Scenario 2: Add feature")
    print(f"     Confidence: {result2.context['final_confidence']:.2f}")

    # Test 3: Unknown intent
    result3 = await router.route("Just do something random")

    # LLM: 0.3, No keywords
    # Threshold (UNKNOWN): 0.9
    # 0.3 < 0.9 → Ask user
    assert result3.intent == Intent.UNKNOWN
    assert result3.context["should_ask_user"]

    print("  ✅ Scenario 3: Unknown intent")
    print(f"     Confidence: {result3.context['final_confidence']:.2f}")
    print("     Decision: Ask user")

    print("  ✅ Router End-to-End 통과!\n")


async def main():
    print("=" * 60)
    print("🎯 Day 9-10: Router 통합 테스트")
    print("=" * 60)
    print()

    try:
        await test_router_basic()
        await test_router_with_context()
        await test_router_confidence_scenarios()
        await test_router_end_to_end()

        print("=" * 60)
        print("🎉 모든 Router 통합 테스트 통과!")
        print("=" * 60)
        print()
        print("✅ 완료된 것:")
        print("  - Router 기본 동작")
        print("  - IntentClassifier + ConfidenceScorer 통합")
        print("  - Context 전달 및 유지")
        print("  - 신뢰도 기반 의사결정")
        print("  - End-to-End 시나리오")
        print()
        print("🎊 Week 1 완료!")
        print("=" * 60)
        print()
        print("📋 Week 1 성과:")
        print("  ✅ Prompt Manager (중앙화)")
        print("  ✅ Context Adapter (Facade)")
        print("  ✅ Intent Classifier (LLM 기반)")
        print("  ✅ Confidence Scorer (휴리스틱)")
        print("  ✅ Router (통합)")
        print()
        print("📋 다음 단계 (Week 3-4):")
        print("  - Workflow State Machine")
        print("  - Task Graph Planner")
        print("  - Orchestrator 통합")
        print()

    except AssertionError as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
