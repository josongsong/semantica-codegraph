"""
SCCP Extreme Cases (L11 Production Hardening)

RFC-024: SOTA-grade 극한 검증

Coverage:
- Float special values (NaN, Infinity)
- Large containers (DoS 방지)
- Unicode, special characters
- Complex numbers
- Deep recursion
- Edge values (maxint, minint)
"""

import math

import pytest

pytestmark = pytest.mark.slow  # 모든 extreme 테스트에 slow 마커 적용

from codegraph_engine.code_foundation.domain.constant_propagation.models import (
    ConstantValue,
    LatticeValue,
)
from codegraph_engine.code_foundation.infrastructure.dfg.constant.lattice import ConstantLattice


class TestFloatSpecialValues:
    """Float 특수값 (NaN, Infinity)"""

    def test_nan_division(self):
        """0.0 / 0.0 → NaN → Bottom"""
        result = ConstantLattice.eval_binary("/", ConstantValue.constant(0.0), ConstantValue.constant(0.0))
        assert result.kind == LatticeValue.BOTTOM  # NaN은 bottom!

    def test_infinity_overflow(self):
        """Infinity → Bottom"""
        result = ConstantLattice.eval_binary("/", ConstantValue.constant(1.0), ConstantValue.constant(0.0))
        # 1.0 / 0.0 = inf in Python float
        assert result.kind == LatticeValue.BOTTOM  # Infinity는 bottom!

    def test_nan_is_truthy(self):
        """NaN is truthy in Python"""
        # Python: bool(float('nan')) == True
        nan_val = float("nan")
        assert ConstantLattice.is_truthy(nan_val) is True
        assert ConstantLattice.is_falsy(nan_val) is False

    def test_infinity_is_truthy(self):
        """Infinity is truthy"""
        inf_val = float("inf")
        assert ConstantLattice.is_truthy(inf_val) is True


class TestLargeContainers:
    """Large container (DoS 방지)"""

    def test_large_list_falsy_check(self):
        """거대 리스트 falsy 체크 (O(1)!)"""
        large_list = [1] * 10**6  # 100만 원소

        # O(1) 체크 (len 사용)
        import time

        start = time.perf_counter()
        result = ConstantLattice.is_falsy(large_list)
        elapsed = time.perf_counter() - start

        assert result is False
        assert elapsed < 0.001  # 1ms 이내 (DoS 방지!)

    def test_large_empty_list(self):
        """거대 빈 리스트는 없지만, 빈 리스트는 falsy"""
        assert ConstantLattice.is_falsy([]) is True

    def test_large_dict(self):
        """거대 dict falsy 체크"""
        large_dict = {i: i for i in range(10**5)}

        import time

        start = time.perf_counter()
        result = ConstantLattice.is_falsy(large_dict)
        elapsed = time.perf_counter() - start

        assert result is False
        assert elapsed < 0.001  # O(1)!


class TestUnicode:
    """Unicode, special characters"""

    def test_unicode_string(self):
        """Unicode 문자열"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant("안녕"), ConstantValue.constant("하세요"))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == "안녕하세요"

    def test_emoji(self):
        """Emoji"""
        result = ConstantLattice.eval_binary("*", ConstantValue.constant("🔥"), ConstantValue.constant(3))
        assert result.value == "🔥🔥🔥"

    def test_unicode_truthiness(self):
        """Unicode falsy/truthy"""
        assert ConstantLattice.is_truthy("한글") is True
        assert ConstantLattice.is_truthy("🚀") is True


class TestComplexNumbers:
    """Complex numbers"""

    def test_complex_add(self):
        """Complex 덧셈"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(1 + 2j), ConstantValue.constant(3 + 4j))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == (4 + 6j)

    def test_complex_multiply(self):
        """Complex 곱셈"""
        result = ConstantLattice.eval_binary("*", ConstantValue.constant(2 + 0j), ConstantValue.constant(3 + 0j))
        assert result.value == (6 + 0j)

    def test_complex_zero_falsy(self):
        """0j is falsy"""
        assert ConstantLattice.is_falsy(0j) is True
        assert ConstantLattice.is_falsy(1 + 0j) is False


class TestEdgeValues:
    """극한 값 (maxint, minint)"""

    def test_maxint_add(self):
        """매우 큰 정수 덧셈"""
        big = 10**100
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(big), ConstantValue.constant(1))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == big + 1

    def test_minint_subtract(self):
        """매우 작은 정수 뺄셈"""
        small = -(10**100)
        result = ConstantLattice.eval_binary("-", ConstantValue.constant(small), ConstantValue.constant(1))
        assert result.value == small - 1

    def test_huge_power_overflow(self):
        """거대 float 거듭제곱 → Infinity → Bottom"""
        result = ConstantLattice.eval_binary("**", ConstantValue.constant(10.0), ConstantValue.constant(1000))
        # 10.0 ** 1000 = inf (Float overflow)
        assert result.kind == LatticeValue.BOTTOM  # Infinity는 bottom!

    def test_huge_int_power_allowed(self):
        """거대 int 거듭제곱은 허용 (Python arbitrary precision)"""
        # Python int는 overflow 안 남 (메모리 허용 한)
        # 하지만 매우 느림
        result = ConstantLattice.eval_binary("**", ConstantValue.constant(2), ConstantValue.constant(100))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 2**100


class TestSpecialTypes:
    """특수 타입 (bytes, bytearray, frozenset)"""

    def test_bytes_falsy(self):
        """bytes 빈 값"""
        # bytes는 str이 아니므로 len() 체크 범위 밖
        # 하지만 == 비교로 falsy 판단 가능
        # 현재 구현은 isinstance 체크하므로 bytes는 기타로 분류
        assert ConstantLattice.is_falsy(b"") is False  # 기타 → False (보수적)

    def test_frozenset_empty(self):
        """frozenset 빈 값"""
        # frozenset은 set이 아니므로 isinstance 실패
        # 현재는 기타로 분류
        assert ConstantLattice.is_falsy(frozenset()) is False  # 보수적


class TestMeetEdgeCases:
    """Meet 극한 케이스"""

    def test_meet_with_none_constant(self):
        """None constant meet"""
        result = ConstantLattice.meet(ConstantValue.constant(None), ConstantValue.constant(None))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value is None

    def test_meet_none_with_zero(self):
        """None과 0 meet → Bottom"""
        result = ConstantLattice.meet(ConstantValue.constant(None), ConstantValue.constant(0))
        assert result.kind == LatticeValue.BOTTOM

    def test_meet_negative_zero(self):
        """-0.0과 0.0 meet"""
        result = ConstantLattice.meet(ConstantValue.constant(-0.0), ConstantValue.constant(0.0))
        # Python: -0.0 == 0.0 is True
        assert result.kind == LatticeValue.CONSTANT


class TestBoundaryConditions:
    """경계 조건 (Boundary)"""

    def test_empty_string_multiply(self):
        """Empty string multiply"""
        result = ConstantLattice.eval_binary("*", ConstantValue.constant(""), ConstantValue.constant(100))
        assert result.value == ""

    def test_list_add_empty(self):
        """[] + [] = []"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant([]), ConstantValue.constant([]))
        assert result.value == []

    def test_power_zero(self):
        """0 ** 0 = 1 (Python)"""
        result = ConstantLattice.eval_binary("**", ConstantValue.constant(0), ConstantValue.constant(0))
        assert result.value == 1

    def test_modulo_negative(self):
        """-5 % 3 = 1 (Python)"""
        result = ConstantLattice.eval_binary("%", ConstantValue.constant(-5), ConstantValue.constant(3))
        assert result.value == 1  # Python modulo


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
