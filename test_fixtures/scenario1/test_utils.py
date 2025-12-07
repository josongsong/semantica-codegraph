"""
utils.py에 대한 테스트
"""

from utils import calculate_total


def test_calculate_total_basic():
    """기본 할인 계산 테스트"""
    result = calculate_total(100, 0.1)
    assert result == 90.0, f"Expected 90.0, got {result}"


def test_calculate_total_no_discount():
    """할인 없을 때"""
    result = calculate_total(100, 0.0)
    assert result == 100.0, f"Expected 100.0, got {result}"


def test_calculate_total_full_discount():
    """100% 할인"""
    result = calculate_total(100, 1.0)
    assert result == 0.0, f"Expected 0.0, got {result}"


if __name__ == "__main__":
    test_calculate_total_basic()
    test_calculate_total_no_discount()
    test_calculate_total_full_discount()
    print("✅ All tests passed!")
