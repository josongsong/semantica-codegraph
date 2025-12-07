"""Agent Router 기본 테스트

Phase 0 Week 1: Prompt Manager + Intent Classifier 검증
"""

import pytest

from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.prompts.manager import PromptManager
from src.agent.router.intent_classifier import IntentClassifier
from src.agent.router.models import Intent
from src.infra.llm.litellm_adapter import LiteLLMAdapter


def test_prompt_manager():
    """Prompt Manager 테스트"""
    pm = PromptManager()

    # Intent 프롬프트
    prompt = pm.get_intent_prompt("Fix the bug")
    assert "User input: Fix the bug" in prompt
    assert "FIX_BUG" in prompt

    # Code review 프롬프트
    review_prompt = pm.get_review_prompt("app.py", "diff content")
    assert "File: app.py" in review_prompt
    assert "diff content" in review_prompt

    print("✅ Prompt Manager 동작!")


def test_context_adapter_mock():
    """Context Adapter Mock 테스트"""
    adapter = ContextAdapter()

    # Mock 관련 코드 검색
    code = adapter.get_relevant_code("fix bug", "test_repo")
    assert "Relevant Code" in code
    assert "calculate_total" in code

    # Mock 심볼 정의
    symbol = adapter.get_symbol_definition("calculate_total", "test_repo")
    assert symbol["name"] == "calculate_total"
    assert symbol["type"] == "function"

    # Mock 영향 범위
    impact = adapter.get_impact_scope("src/app.py", "test_repo")
    assert len(impact) > 0

    print("✅ Context Adapter Mock 동작!")


@pytest.mark.skipif(
    True,  # Phase 0: LLM 호출은 선택적
    reason="LLM API 호출 필요 (비용 발생)",
)
def test_intent_classifier_with_llm():
    """Intent Classifier 테스트 (실제 LLM 호출)"""
    llm = LiteLLMAdapter()
    classifier = IntentClassifier(llm)

    # 명확한 버그 수정
    result = classifier.classify("Fix the bug in calculate_total function")

    print(f"Intent: {result.intent}")
    print(f"Confidence: {result.confidence}")
    print(f"Reasoning: {result.reasoning}")

    assert result.intent == Intent.FIX_BUG
    assert result.confidence > 0.5
    print("✅ Intent Classifier 동작!")


def test_intent_classifier_structure():
    """Intent Classifier 구조 테스트 (LLM 호출 없이)"""
    pm = PromptManager()

    # Prompt가 제대로 생성되는지만 확인
    prompt = pm.get_intent_prompt("Add a new feature")
    assert "Add a new feature" in prompt
    assert "ADD_FEATURE" in prompt

    # Intent enum 확인
    assert Intent.FIX_BUG.value == "fix_bug"
    assert Intent.ADD_FEATURE.value == "add_feature"
    assert Intent.REFACTOR.value == "refactor"

    print("✅ Intent Classifier 구조 검증!")


if __name__ == "__main__":
    print("🧪 Testing Phase 0 - Week 1 Components...\n")

    print("1. Testing Prompt Manager...")
    test_prompt_manager()

    print("\n2. Testing Context Adapter Mock...")
    test_context_adapter_mock()

    print("\n3. Testing Intent Classifier Structure...")
    test_intent_classifier_structure()

    print("\n4. Testing Intent Classifier with LLM (optional)...")
    print("   ⏭️  Skipped (set skipif=False to enable)")

    print("\n🎉 All Phase 0 Week 1 tests passed!")
    print("\n다음 단계:")
    print("- Confidence Scorer 구현 (Day 6-8)")
    print("- Router 통합 (Day 9-10)")
