"""Agent Phase 0 최소 테스트 (의존성 최소화)

Prompt Manager와 Context Adapter만 독립적으로 테스트
LLM이나 infra 의존성 없음
"""

import sys
from pathlib import Path

# PYTHONPATH 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.adapters.context_adapter import ContextAdapter
from src.agent.prompts.manager import PromptManager
from src.agent.router.models import Intent, IntentResult


def test_prompt_manager():
    """Prompt Manager 기본 동작 테스트"""
    print("🧪 Testing Prompt Manager...")

    pm = PromptManager()

    # 1. Intent 프롬프트
    prompt = pm.get_intent_prompt("Fix the bug in calculate_total")
    assert "User input: Fix the bug in calculate_total" in prompt
    assert "FIX_BUG" in prompt
    assert "JSON" in prompt

    # 2. Code generation 프롬프트
    code_prompt = pm.get_code_gen_prompt(
        context="some context", plan="fix the bug", task="add null check", language="python"
    )
    assert "senior python developer" in code_prompt
    assert "some context" in code_prompt
    assert "fix the bug" in code_prompt

    # 3. Review 프롬프트
    review_prompt = pm.get_review_prompt("app.py", "diff content here")
    assert "File: app.py" in review_prompt
    assert "diff content here" in review_prompt
    assert "Security" in review_prompt

    print("  ✅ Intent 프롬프트 생성")
    print("  ✅ Code generation 프롬프트 생성")
    print("  ✅ Review 프롬프트 생성")
    print("  ✅ Prompt Manager 통과!\n")


def test_context_adapter():
    """Context Adapter Mock 동작 테스트"""
    print("🧪 Testing Context Adapter...")

    adapter = ContextAdapter()  # Mock mode (no dependencies)

    # 1. 관련 코드 검색 (Mock)
    code = adapter.get_relevant_code("fix bug in calculate_total", "test_repo")
    assert "Relevant Code" in code
    assert "calculate_total" in code
    assert "Result 1" in code
    assert "```python" in code  # Markdown 포맷 확인

    # 2. 심볼 정의 (Mock)
    symbol = adapter.get_symbol_definition("calculate_total", "test_repo")
    assert symbol["name"] == "calculate_total"
    assert symbol["type"] == "function"
    assert "file_path" in symbol
    assert "line" in symbol

    # 3. 호출 그래프 (Mock)
    call_graph = adapter.get_call_graph("calculate_total", "test_repo")
    assert call_graph["function"] == "calculate_total"
    assert isinstance(call_graph["called_by"], list)
    assert len(call_graph["called_by"]) > 0

    # 4. 영향 범위 (Mock)
    impact = adapter.get_impact_scope("src/app.py", "test_repo")
    assert isinstance(impact, list)
    assert len(impact) > 0

    # 5. 관련 테스트 (Mock)
    tests = adapter.get_related_tests("src/app.py", "test_repo")
    assert isinstance(tests, list)
    assert len(tests) > 0

    print("  ✅ 관련 코드 검색 (Markdown 포맷)")
    print("  ✅ 심볼 정의 조회")
    print("  ✅ 호출 그래프 조회")
    print("  ✅ 영향 범위 분석")
    print("  ✅ 관련 테스트 찾기")
    print("  ✅ Context Adapter 통과!\n")


def test_intent_models():
    """Intent 모델 기본 동작 테스트"""
    print("🧪 Testing Intent Models...")

    # 1. Intent enum
    assert Intent.FIX_BUG.value == "fix_bug"
    assert Intent.ADD_FEATURE.value == "add_feature"
    assert Intent.REFACTOR.value == "refactor"
    assert Intent.EXPLAIN_CODE.value == "explain_code"
    assert Intent.REVIEW_CODE.value == "review_code"

    # 2. IntentResult
    result = IntentResult(
        intent=Intent.FIX_BUG,
        confidence=0.95,
        reasoning="User explicitly mentions fixing a bug",
        context={"repo_id": "test"},
    )

    assert result.intent == Intent.FIX_BUG
    assert result.confidence == 0.95
    assert "bug" in result.reasoning
    assert result.context["repo_id"] == "test"

    print("  ✅ Intent enum 정의")
    print("  ✅ IntentResult 데이터 클래스")
    print("  ✅ Intent Models 통과!\n")


def test_integration():
    """통합 시나리오 테스트"""
    print("🧪 Testing Integration Scenario...")

    # 시나리오: "Fix bug in calculate_total"
    user_input = "Fix the bug in calculate_total function"

    # 1. Prompt 생성
    pm = PromptManager()
    intent_prompt = pm.get_intent_prompt(user_input)
    assert user_input in intent_prompt

    # 2. Context 검색 (Mock)
    adapter = ContextAdapter()
    relevant_code = adapter.get_relevant_code("calculate_total bug", "my_repo")
    assert "calculate_total" in relevant_code

    # 3. 심볼 정의 조회
    symbol_def = adapter.get_symbol_definition("calculate_total", "my_repo")
    assert symbol_def["name"] == "calculate_total"

    # 4. 영향 범위 확인
    impact = adapter.get_impact_scope(symbol_def["file_path"], "my_repo")
    assert len(impact) > 0

    print("  ✅ End-to-end 시나리오 (Mock)")
    print("     User Input → Prompt → Context → Impact")
    print("  ✅ Integration 통과!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("🎯 Phase 0 Week 1 - 최소 테스트 실행")
    print("=" * 60)
    print()

    try:
        test_prompt_manager()
        test_context_adapter()
        test_intent_models()
        test_integration()

        print("=" * 60)
        print("🎉 모든 테스트 통과!")
        print("=" * 60)
        print()
        print("✅ 완료된 것:")
        print("  - Prompt Manager (중앙화된 프롬프트 관리)")
        print("  - Context Adapter (Facade 패턴)")
        print("  - Intent Models (데이터 구조)")
        print("  - Integration (Mock 기반 통합)")
        print()
        print("📋 다음 단계:")
        print("  - Day 6-8: Confidence Scorer 구현")
        print("  - Day 9-10: Router 통합")
        print("  - Week 3-4: Workflow + TaskGraph")
        print()

    except AssertionError as e:
        print(f"\n❌ 테스트 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
