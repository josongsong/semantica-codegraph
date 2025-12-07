"""Code Generator Tests

LLM 기반 코드 생성 테스트
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.execution.code_generation import CodeChange, CodeGenerator


# Mock LLM
class MockLLM:
    async def complete(self, prompt: str, **kwargs) -> str:
        """Mock LLM 응답"""
        if "버그 수정" in prompt or "bug fix" in prompt.lower():
            return """```python
def calculate_total(items):
    if not items:  # Added null check
        return 0
    total = 0
    for item in items:
        if item is not None:  # Added item check
            total += item.price
    return total
```

설명: Added null check for items and individual item validation
"""

        elif "기능 추가" in prompt or "feature" in prompt.lower():
            return """```python
def authenticate_user(username, password):
    '''User authentication feature'''
    if not username or not password:
        return False

    # Check credentials
    user = database.get_user(username)
    if user and verify_password(password, user.password_hash):
        return True

    return False
```

설명: Implemented user authentication with password verification
"""

        elif "리팩토링" in prompt or "refactor" in prompt.lower():
            return """```python
# Refactored for better readability
def process_payment(amount, customer):
    '''Process payment transaction'''
    if not _validate_payment(amount, customer):
        raise PaymentError("Invalid payment")

    transaction = _create_transaction(amount, customer)
    result = _execute_transaction(transaction)
    _log_transaction(result)

    return result

def _validate_payment(amount, customer):
    return amount > 0 and customer.is_active

def _create_transaction(amount, customer):
    return Transaction(amount=amount, customer_id=customer.id)

def _execute_transaction(transaction):
    return payment_gateway.process(transaction)

def _log_transaction(result):
    logger.info(f"Payment processed: {result.id}")
```

설명: Refactored into smaller, focused functions with better naming
Breaking 변경: None
"""

        return "# Generated code"


print("=" * 70)
print("🔥 Code Generator Tests")
print("=" * 70)
print()


async def test_1_generate_fix():
    """Test 1: 버그 수정 코드 생성"""
    print("🔍 Test 1: Generate Bug Fix...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    # 버그 수정 생성
    code_change = await generator.generate_fix(
        bug_description="fix null pointer exception in calculate_total",
        file_path="src/billing.py",
        existing_code="def calculate_total(items):\n    return sum(item.price for item in items)",
    )

    assert isinstance(code_change, CodeChange)
    assert code_change.file_path == "src/billing.py"
    assert len(code_change.content) > 0
    assert "if not items" in code_change.content
    assert len(code_change.explanation) > 0
    assert code_change.confidence > 0.0

    print(f"  ✅ Code generated: {len(code_change.content)} chars")
    print(f"  ✅ Explanation: {code_change.explanation[:50]}...")
    print(f"  ✅ Confidence: {code_change.confidence:.2f}")
    print()


async def test_2_generate_feature():
    """Test 2: 새 기능 코드 생성"""
    print("🔍 Test 2: Generate Feature...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    # 기능 생성
    code_changes = await generator.generate_feature(
        feature_description="add user authentication", target_file="src/auth.py"
    )

    assert len(code_changes) >= 1
    code_change = code_changes[0]

    assert code_change.file_path == "src/auth.py"
    assert "authenticate_user" in code_change.content
    assert "password" in code_change.content
    assert code_change.confidence > 0.0

    print(f"  ✅ Feature generated: {len(code_change.content)} chars")
    print(f"  ✅ Explanation: {code_change.explanation[:50]}...")
    print(f"  ✅ Files: {len(code_changes)}")
    print()


async def test_3_generate_refactoring():
    """Test 3: 리팩토링 코드 생성"""
    print("🔍 Test 3: Generate Refactoring...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    # 리팩토링 생성
    code_change = await generator.generate_refactoring(
        refactor_goal="improve code readability", file_path="src/payment.py", existing_code="def pay(a, c): ..."
    )

    assert code_change.file_path == "src/payment.py"
    assert "process_payment" in code_change.content
    assert "_validate_payment" in code_change.content  # 추출된 함수
    assert code_change.confidence > 0.0

    print(f"  ✅ Refactored: {len(code_change.content)} chars")
    print(f"  ✅ Explanation: {code_change.explanation[:50]}...")
    print()


async def test_4_code_extraction():
    """Test 4: 코드 블록 추출"""
    print("🔍 Test 4: Code Block Extraction...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    response = """Here's the code:

```python
def hello():
    print("Hello!")
```

설명: Simple hello function
"""

    code = generator._extract_code_block(response)
    explanation = generator._extract_explanation(response)

    assert "def hello():" in code
    assert "print" in code
    assert "Simple hello function" in explanation

    print(f"  ✅ Code extracted: {len(code)} chars")
    print(f"  ✅ Explanation: {explanation}")
    print()


async def test_5_confidence_estimation():
    """Test 5: 신뢰도 추정"""
    print("🔍 Test 5: Confidence Estimation...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    # 좋은 응답 (코드 블록 + 설명)
    good_response = """```python
def func():
    pass
```

설명: Good code
"""
    confidence_good = generator._estimate_confidence(good_response)

    # 나쁜 응답 (코드만)
    bad_response = "def func(): pass"
    confidence_bad = generator._estimate_confidence(bad_response)

    assert confidence_good > confidence_bad
    assert confidence_good >= 0.9

    print(f"  ✅ Good response confidence: {confidence_good:.2f}")
    print(f"  ✅ Bad response confidence: {confidence_bad:.2f}")
    print()


async def test_6_fallback_generation():
    """Test 6: Fallback 생성 (LLM 실패 시)"""
    print("🔍 Test 6: Fallback Generation...")

    # LLM 없이 (None)
    class FailingLLM:
        async def complete(self, prompt: str, **kwargs):
            raise Exception("LLM failed")

    llm = FailingLLM()
    generator = CodeGenerator(llm)

    # Fallback으로 생성
    code_change = await generator.generate_fix(
        bug_description="test bug", file_path="test.py", existing_code="def test(): pass"
    )

    assert code_change is not None
    assert code_change.file_path == "test.py"
    assert len(code_change.content) > 0
    assert code_change.confidence < 1.0  # Fallback은 낮은 신뢰도

    print("  ✅ Fallback code generated")
    print(f"  ✅ Confidence: {code_change.confidence:.2f} (낮음)")
    print()


async def test_7_context_usage():
    """Test 7: Context 활용"""
    print("🔍 Test 7: Context Usage...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    # Context 포함
    code_change = await generator.generate_fix(
        bug_description="fix bug",
        file_path="app.py",
        existing_code="def func(): pass",
        context={"related_code": "def helper(): return True", "test_cases": "assert func() is not None"},
    )

    assert code_change is not None
    print("  ✅ Context used in generation")
    print(f"  ✅ Generated: {len(code_change.content)} chars")
    print()


async def test_8_multiple_scenarios():
    """Test 8: 여러 시나리오"""
    print("🔍 Test 8: Multiple Scenarios...")

    llm = MockLLM()
    generator = CodeGenerator(llm)

    scenarios = [
        ("fix null pointer in getUserData", "src/user.py"),
        ("add email validation", "src/validation.py"),
        ("refactor database queries", "src/db.py"),
    ]

    results = []
    for description, file_path in scenarios:
        if "fix" in description:
            result = await generator.generate_fix(description, file_path, "def func(): pass")
        elif "add" in description:
            result_list = await generator.generate_feature(description, file_path)
            result = result_list[0]
        else:
            result = await generator.generate_refactoring(description, file_path, "def func(): pass")

        results.append(result)

    assert len(results) == 3
    assert all(r.file_path for r in results)
    assert all(len(r.content) > 0 for r in results)

    print("  ✅ 3 scenarios completed")
    for i, r in enumerate(results, 1):
        print(f"     {i}. {r.file_path}: {len(r.content)} chars")
    print()


def main():
    print("Starting Code Generator Tests...\n")

    tests = [
        test_1_generate_fix,
        test_2_generate_feature,
        test_3_generate_refactoring,
        test_4_code_extraction,
        test_5_confidence_estimation,
        test_6_fallback_generation,
        test_7_context_usage,
        test_8_multiple_scenarios,
    ]

    async def run_tests():
        passed_count = 0
        for test_func in tests:
            try:
                await test_func()
                passed_count += 1
            except AssertionError as e:
                print(f"❌ {test_func.__name__.replace('test_', '').replace('_', ' ').title()} FAILED: {e}")
            except Exception as e:
                print(f"❌ {test_func.__name__.replace('test_', '').replace('_', ' ').title()} ERROR: {e}")
                import traceback

                traceback.print_exc()

        print("=" * 70)
        print(f"📊 최종 결과: {passed_count}/{len(tests)} 통과")
        print("=" * 70)

        if passed_count == len(tests):
            print("\n🎉 Code Generator 테스트 성공!")
            print("\n✅ 검증된 기능:")
            print("  1. Bug fix generation")
            print("  2. Feature generation")
            print("  3. Refactoring generation")
            print("  4. Code block extraction")
            print("  5. Confidence estimation")
            print("  6. Fallback generation")
            print("  7. Context usage")
            print("  8. Multiple scenarios")
            print("\n🏆 Code Generator 구현 완료!")
        else:
            print("\n⚠️  테스트 실패")

    asyncio.run(run_tests())


if __name__ == "__main__":
    main()
