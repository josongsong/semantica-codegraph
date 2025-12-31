"""Confidence Scorer 테스트

Day 6-8: Confidence 측정 및 사용자 확인 로직 검증
"""

import sys
from pathlib import Path

# PYTHONPATH 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.orchestrator.orchestrator.router.confidence_scorer import ConfidenceScorer
from apps.orchestrator.orchestrator.router.models import Intent, IntentResult


def test_basic_scoring():
    """기본 신뢰도 계산 테스트"""
    print("🧪 Testing Basic Scoring...")

    scorer = ConfidenceScorer()

    # High confidence (LLM만)
    result_high = IntentResult(
        intent=Intent.FIX_BUG, confidence=0.95, reasoning="Very clear", context={"user_input": "Fix the bug"}
    )

    score = scorer.score(result_high)
    assert 0.95 <= score <= 1.0
    print(f"  ✅ High confidence: {score:.2f}")

    # Low confidence
    result_low = IntentResult(
        intent=Intent.FIX_BUG, confidence=0.4, reasoning="Unclear", context={"user_input": "Do something"}
    )

    score = scorer.score(result_low)
    assert 0.3 <= score <= 0.6
    print(f"  ✅ Low confidence: {score:.2f}")

    print("  ✅ Basic Scoring 통과!\n")


def test_heuristic_boost():
    """휴리스틱 boost 테스트"""
    print("🧪 Testing Heuristic Boost...")

    scorer = ConfidenceScorer(enable_heuristic=True)

    # 키워드 매칭 ("bug", "fix")
    result_with_keywords = IntentResult(
        intent=Intent.FIX_BUG,
        confidence=0.7,
        reasoning="Detected keywords",
        context={"user_input": "Fix the bug in calculate_total"},
    )

    score_with_boost = scorer.score(result_with_keywords)

    # 키워드 없음
    result_no_keywords = IntentResult(
        intent=Intent.FIX_BUG, confidence=0.7, reasoning="No keywords", context={"user_input": "Do something"}
    )

    score_no_boost = scorer.score(result_no_keywords)

    # Boost 확인 (최소 0.1 차이)
    assert score_with_boost > score_no_boost
    assert score_with_boost - score_no_boost >= 0.1

    print(f"  ✅ With keywords: {score_with_boost:.2f}")
    print(f"  ✅ Without keywords: {score_no_boost:.2f}")
    print(f"  ✅ Boost: +{score_with_boost - score_no_boost:.2f}")
    print("  ✅ Heuristic Boost 통과!\n")


def test_should_ask_user():
    """사용자 확인 필요 여부 테스트"""
    print("🧪 Testing Should Ask User...")

    scorer = ConfidenceScorer()

    # High confidence → 즉시 실행
    result_high = IntentResult(
        intent=Intent.FIX_BUG,  # threshold=0.7
        confidence=0.85,
        reasoning="Clear intent",
        context={"user_input": "Fix the bug"},
    )

    should_ask = scorer.should_ask_user(result_high)
    assert not should_ask  # 즉시 실행 가능
    print("  ✅ High confidence (0.85 > 0.7): No ask needed")

    # Low confidence → 사용자 확인
    result_low = IntentResult(
        intent=Intent.FIX_BUG,  # threshold=0.7
        confidence=0.5,
        reasoning="Unclear intent",
        context={"user_input": "Do something"},
    )

    should_ask = scorer.should_ask_user(result_low)
    assert should_ask  # 사용자 확인 필요
    print("  ✅ Low confidence (0.5 < 0.7): Ask needed")

    print("  ✅ Should Ask User 통과!\n")


def test_intent_specific_thresholds():
    """Intent별 threshold 테스트"""
    print("🧪 Testing Intent-Specific Thresholds...")

    scorer = ConfidenceScorer()

    # FIX_BUG: 0.7 (관대)
    assert scorer.get_threshold(Intent.FIX_BUG) == 0.7

    # ADD_FEATURE: 0.8 (엄격)
    assert scorer.get_threshold(Intent.ADD_FEATURE) == 0.8

    # EXPLAIN_CODE: 0.5 (매우 관대)
    assert scorer.get_threshold(Intent.EXPLAIN_CODE) == 0.5

    # 동일한 confidence (0.75)로 다른 결과
    result_fix = IntentResult(
        intent=Intent.FIX_BUG,  # threshold=0.7
        confidence=0.75,
        reasoning="Test",
        context={},
    )

    result_add = IntentResult(
        intent=Intent.ADD_FEATURE,  # threshold=0.8
        confidence=0.75,
        reasoning="Test",
        context={},
    )

    # FIX_BUG: 0.75 > 0.7 → 즉시 실행
    assert not scorer.should_ask_user(result_fix)

    # ADD_FEATURE: 0.75 < 0.8 → 사용자 확인
    assert scorer.should_ask_user(result_add)

    print("  ✅ FIX_BUG threshold: 0.7")
    print("  ✅ ADD_FEATURE threshold: 0.8")
    print("  ✅ EXPLAIN_CODE threshold: 0.5")
    print("  ✅ Intent-Specific Thresholds 통과!\n")


def test_confidence_level():
    """신뢰도 레벨 문자열 테스트"""
    print("🧪 Testing Confidence Level...")

    scorer = ConfidenceScorer()

    # High
    result_high = IntentResult(intent=Intent.FIX_BUG, confidence=0.9, reasoning="Test", context={})
    assert scorer.get_confidence_level(result_high) == "high"

    # Medium
    result_medium = IntentResult(intent=Intent.FIX_BUG, confidence=0.7, reasoning="Test", context={})
    assert scorer.get_confidence_level(result_medium) == "medium"

    # Low
    result_low = IntentResult(intent=Intent.FIX_BUG, confidence=0.4, reasoning="Test", context={})
    assert scorer.get_confidence_level(result_low) == "low"

    print("  ✅ High level (0.9)")
    print("  ✅ Medium level (0.7)")
    print("  ✅ Low level (0.4)")
    print("  ✅ Confidence Level 통과!\n")


def test_calibration():
    """Threshold 조정 테스트 (Phase 1 기능)"""
    print("🧪 Testing Calibration...")

    scorer = ConfidenceScorer()

    # 기본 threshold
    original = scorer.get_threshold(Intent.FIX_BUG)
    assert original == 0.7

    # 조정
    scorer.calibrate(Intent.FIX_BUG, 0.6)
    new = scorer.get_threshold(Intent.FIX_BUG)
    assert new == 0.6

    # 잘못된 값
    try:
        scorer.calibrate(Intent.FIX_BUG, 1.5)
        assert False, "Should raise ValueError"
    except ValueError:
        pass

    print("  ✅ Original threshold: 0.7")
    print("  ✅ Calibrated to: 0.6")
    print("  ✅ Invalid value rejected")
    print("  ✅ Calibration 통과!\n")


def test_integration_scenario():
    """통합 시나리오 테스트"""
    print("🧪 Testing Integration Scenario...")

    scorer = ConfidenceScorer(enable_heuristic=True)

    # Scenario 1: 명확한 버그 수정 요청
    result1 = IntentResult(
        intent=Intent.FIX_BUG,
        confidence=0.6,  # LLM confidence (경계선)
        reasoning="Bug fix requested",
        context={"user_input": "Fix the critical bug in payment processing"},
    )

    # Heuristic boost: "bug" + "fix" → +0.2
    # Final: 0.6 + 0.2 = 0.8
    score1 = scorer.score(result1)
    should_ask1 = scorer.should_ask_user(result1)
    level1 = scorer.get_confidence_level(result1)

    assert score1 >= 0.8  # Boosted
    assert not should_ask1  # 즉시 실행 (0.8 > 0.7)
    assert level1 == "high"

    print("  ✅ Scenario 1 (명확한 버그 수정)")
    print(f"     LLM: 0.6 → Boosted: {score1:.2f}")
    print("     Decision: Execute immediately")

    # Scenario 2: 모호한 요청
    result2 = IntentResult(
        intent=Intent.UNKNOWN,
        confidence=0.5,
        reasoning="Unclear intent",
        context={"user_input": "Do something with the code"},
    )

    score2 = scorer.score(result2)
    should_ask2 = scorer.should_ask_user(result2)
    level2 = scorer.get_confidence_level(result2)

    assert score2 <= 0.5  # No boost
    assert should_ask2  # 사용자 확인 (0.5 < 0.9)
    assert level2 == "low"

    print("  ✅ Scenario 2 (모호한 요청)")
    print(f"     Score: {score2:.2f}")
    print("     Decision: Ask user for clarification")

    print("  ✅ Integration Scenario 통과!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("🎯 Day 6-8: Confidence Scorer 테스트")
    print("=" * 60)
    print()

    try:
        test_basic_scoring()
        test_heuristic_boost()
        test_should_ask_user()
        test_intent_specific_thresholds()
        test_confidence_level()
        test_calibration()
        test_integration_scenario()

        print("=" * 60)
        print("🎉 모든 Confidence Scorer 테스트 통과!")
        print("=" * 60)
        print()
        print("✅ 완료된 것:")
        print("  - 기본 신뢰도 계산 (LLM self-report)")
        print("  - 휴리스틱 boost (키워드 기반)")
        print("  - Intent별 threshold")
        print("  - 사용자 확인 필요 여부 판단")
        print("  - 신뢰도 레벨 (high/medium/low)")
        print("  - Calibration (Phase 1 준비)")
        print()
        print("📋 다음 단계:")
        print("  - Day 9-10: Router 통합")
        print("  - IntentClassifier + ConfidenceScorer 결합")
        print()

    except AssertionError as e:
        print(f"\n❌ 테스트 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
