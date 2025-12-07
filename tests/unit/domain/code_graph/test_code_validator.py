"""Code Validator Tests"""

import asyncio
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.execution.code_generation.models import CodeChange
from src.execution.validation import CodeValidator, ValidationResult

print("=" * 70)
print("🔥 Code Validator Tests")
print("=" * 70)
print()


async def test_1_valid_syntax():
    """Test 1: 유효한 Syntax"""
    print("🔍 Test 1: Valid Syntax...")

    validator = CodeValidator()

    code = """
def hello():
    print("Hello, World!")
    return True
"""

    result = validator.validate_sync(code)

    assert result.is_valid
    assert len(result.errors) == 0
    assert result.metadata["syntax"] == "valid"

    print("  ✅ Syntax valid")
    print(f"  ✅ Result: {result}")
    print()


async def test_2_invalid_syntax():
    """Test 2: 잘못된 Syntax"""
    print("🔍 Test 2: Invalid Syntax...")

    validator = CodeValidator()

    code = """
def hello()
    print("Missing colon")
"""

    result = validator.validate_sync(code)

    assert not result.is_valid
    assert len(result.errors) > 0
    assert "Syntax error" in result.errors[0]
    assert result.metadata["syntax"] == "invalid"

    print("  ✅ Syntax error detected")
    print(f"  ✅ Error: {result.errors[0]}")
    print()


async def test_3_import_validation():
    """Test 3: Import 검증"""
    print("🔍 Test 3: Import Validation...")

    validator = CodeValidator()

    # 유효한 imports
    valid_code = """
import os
import sys
from pathlib import Path

def func():
    pass
"""

    result = validator.validate_sync(valid_code)

    assert result.is_valid
    assert result.metadata["imports"]["total"] == 3
    print(f"  ✅ Valid imports detected: {result.metadata['imports']['total']}")

    # 잘못된 imports
    invalid_code = """
import nonexistent_module_xyz
from fake_package import FakeClass

def func():
    pass
"""

    result2 = validator.validate_sync(invalid_code)

    assert result2.is_valid  # Syntax는 유효
    assert len(result2.warnings) > 0  # Warning만
    assert "missing imports" in result2.warnings[0].lower()

    print(f"  ✅ Invalid imports warned: {len(result2.warnings)} warnings")
    print()


async def test_4_code_change_validation():
    """Test 4: CodeChange 검증"""
    print("🔍 Test 4: CodeChange Validation...")

    validator = CodeValidator()

    code_change = CodeChange(
        file_path="src/test.py",
        content="""
def calculate(a, b):
    if a is None or b is None:
        return 0
    return a + b
""",
        explanation="Added null check",
        confidence=0.9,
    )

    result = await validator.validate(code_change)

    assert result.is_valid
    assert len(result.errors) == 0

    print("  ✅ CodeChange validated")
    print(f"  ✅ Result: {result}")
    print()


async def test_5_multiple_validations():
    """Test 5: 여러 코드 검증"""
    print("🔍 Test 5: Multiple Validations...")

    validator = CodeValidator()

    test_codes = [
        ("Valid simple", "def func(): pass", True),
        ("Valid complex", "class MyClass:\n    def method(self): return True", True),
        ("Invalid syntax", "def func( pass", False),
        ("Invalid indent", "def func():\npass", False),
    ]

    results = []
    for name, code, expected_valid in test_codes:
        result = validator.validate_sync(code)
        results.append((name, result.is_valid))
        assert result.is_valid == expected_valid, f"{name} failed"

    print(f"  ✅ {len(test_codes)} codes validated")
    for name, is_valid in results:
        status = "✅" if is_valid else "❌"
        print(f"     {status} {name}")
    print()


async def test_6_validation_levels():
    """Test 6: 검증 레벨"""
    print("🔍 Test 6: Validation Levels...")

    # Level 1+2 only (기본)
    validator_basic = CodeValidator(enable_type_check=False, enable_lint=False, enable_tests=False)

    code = "def func(): pass"
    code_change = CodeChange("test.py", code, "test", 1.0)

    result = await validator_basic.validate(code_change)

    assert result.is_valid
    assert "syntax" in result.metadata
    assert "imports" in result.metadata
    assert "type_check" not in result.metadata  # Not enabled
    assert "lint" not in result.metadata  # Not enabled

    print("  ✅ Basic validation (Syntax + Imports)")
    print(f"  ✅ Metadata: {list(result.metadata.keys())}")
    print()


async def test_7_error_accumulation():
    """Test 7: 에러 누적"""
    print("🔍 Test 7: Error Accumulation...")

    validator = CodeValidator()

    result = ValidationResult(is_valid=True)

    # 에러 추가
    result.add_error("Error 1")
    assert not result.is_valid
    assert len(result.errors) == 1

    result.add_error("Error 2")
    assert len(result.errors) == 2

    # 경고 추가 (is_valid 영향 없음)
    result.add_warning("Warning 1")
    assert len(result.warnings) == 1
    assert not result.is_valid  # 여전히 invalid

    print(f"  ✅ Errors: {len(result.errors)}")
    print(f"  ✅ Warnings: {len(result.warnings)}")
    print(f"  ✅ Status: {result}")
    print()


async def test_8_to_dict():
    """Test 8: Dict 변환"""
    print("🔍 Test 8: Dict Conversion...")

    result = ValidationResult(is_valid=True)
    result.add_warning("Test warning")
    result.metadata["test_key"] = "test_value"

    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["is_valid"]
    assert len(result_dict["warnings"]) == 1
    assert result_dict["metadata"]["test_key"] == "test_value"

    print("  ✅ Dict conversion successful")
    print(f"  ✅ Keys: {list(result_dict.keys())}")
    print()


def main():
    print("Starting Code Validator Tests...\n")

    tests = [
        test_1_valid_syntax,
        test_2_invalid_syntax,
        test_3_import_validation,
        test_4_code_change_validation,
        test_5_multiple_validations,
        test_6_validation_levels,
        test_7_error_accumulation,
        test_8_to_dict,
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
            print("\n🎉 Code Validator 테스트 성공!")
            print("\n✅ 검증된 기능:")
            print("  1. Valid syntax detection")
            print("  2. Invalid syntax detection")
            print("  3. Import validation")
            print("  4. CodeChange validation")
            print("  5. Multiple validations")
            print("  6. Validation levels")
            print("  7. Error accumulation")
            print("  8. Dict conversion")
            print("\n🏆 Code Validator 구현 완료!")
        else:
            print("\n⚠️  테스트 실패")

    asyncio.run(run_tests())


if __name__ == "__main__":
    main()
