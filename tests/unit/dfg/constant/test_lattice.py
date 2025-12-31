"""
Constant Lattice Tests

RFC-024 Part 1: SCCP Baseline - Production-Ready Tests

Coverage:
- Meet 연산 (모든 조합)
- Binary 연산 (산술, 비트, 비교)
- Python truthiness
- Error handling (ZeroDivision, TypeError, Overflow)
"""

import pytest

from codegraph_engine.code_foundation.domain.constant_propagation.models import (
    ConstantValue,
    LatticeValue,
)
from codegraph_engine.code_foundation.infrastructure.dfg.constant.lattice import ConstantLattice


class TestConstantValue:
    """ConstantValue 기본 테스트"""

    def test_top_creation(self):
        """TOP 생성"""
        val = ConstantValue.top()
        assert val.kind == LatticeValue.TOP
        assert val.value is None
        assert val.is_top()
        assert not val.is_constant()
        assert not val.is_bottom()

    def test_bottom_creation(self):
        """BOTTOM 생성"""
        val = ConstantValue.bottom()
        assert val.kind == LatticeValue.BOTTOM
        assert val.value is None
        assert val.is_bottom()
        assert not val.is_constant()
        assert not val.is_top()

    def test_constant_creation(self):
        """CONSTANT 생성"""
        val = ConstantValue.constant(10)
        assert val.kind == LatticeValue.CONSTANT
        assert val.value == 10
        assert val.is_constant()
        assert not val.is_top()
        assert not val.is_bottom()

    def test_constant_none_value(self):
        """None도 valid constant"""
        val = ConstantValue.constant(None)
        assert val.kind == LatticeValue.CONSTANT
        assert val.value is None  # None is a constant!

    def test_frozen_immutable(self):
        """frozen dataclass (immutable)"""
        val = ConstantValue.constant(5)
        with pytest.raises(Exception):  # FrozenInstanceError
            val.value = 10  # type: ignore

    def test_hashable(self):
        """hashable (dict key로 사용 가능)"""
        val1 = ConstantValue.constant(5)
        val2 = ConstantValue.constant(5)
        val3 = ConstantValue.constant(10)

        # 같은 값은 같은 hash
        assert hash(val1) == hash(val2)
        assert val1 == val2

        # 다른 값은 다른 hash (일반적으로)
        assert val1 != val3

        # dict key로 사용 가능
        d = {val1: "a", val3: "b"}
        assert d[val2] == "a"  # val1 == val2

    def test_repr_readable(self):
        """사람이 읽기 좋은 표현"""
        assert repr(ConstantValue.top()) == "⊤"
        assert repr(ConstantValue.bottom()) == "⊥"
        assert repr(ConstantValue.constant(10)) == "Const(10)"


class TestLatticeMeet:
    """Lattice meet 연산 테스트"""

    def test_meet_top_with_constant(self):
        """⊤ ∧ c = c"""
        result = ConstantLattice.meet(ConstantValue.top(), ConstantValue.constant(5))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 5

    def test_meet_constant_with_top(self):
        """c ∧ ⊤ = c (commutative)"""
        result = ConstantLattice.meet(ConstantValue.constant(5), ConstantValue.top())
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 5

    def test_meet_bottom_with_constant(self):
        """⊥ ∧ c = ⊥"""
        result = ConstantLattice.meet(ConstantValue.bottom(), ConstantValue.constant(5))
        assert result.kind == LatticeValue.BOTTOM

    def test_meet_same_constants(self):
        """c ∧ c = c (idempotent)"""
        result = ConstantLattice.meet(ConstantValue.constant(5), ConstantValue.constant(5))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 5

    def test_meet_different_constants(self):
        """c1 ∧ c2 = ⊥ (c1 ≠ c2)"""
        result = ConstantLattice.meet(ConstantValue.constant(5), ConstantValue.constant(10))
        assert result.kind == LatticeValue.BOTTOM

    def test_meet_all_same(self):
        """meet_all([c, c, c]) = c"""
        result = ConstantLattice.meet_all(
            [
                ConstantValue.constant(5),
                ConstantValue.constant(5),
                ConstantValue.constant(5),
            ]
        )
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 5

    def test_meet_all_different(self):
        """meet_all([c1, c2]) = ⊥"""
        result = ConstantLattice.meet_all(
            [
                ConstantValue.constant(5),
                ConstantValue.constant(10),
            ]
        )
        assert result.kind == LatticeValue.BOTTOM

    def test_meet_all_empty(self):
        """meet_all([]) = ⊤"""
        result = ConstantLattice.meet_all([])
        assert result.kind == LatticeValue.TOP


class TestBinaryOperations:
    """이항 연산 테스트 (Production-Ready)"""

    # 산술 연산
    def test_add(self):
        """덧셈"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(1), ConstantValue.constant(2))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 3

    def test_subtract(self):
        """뺄셈"""
        result = ConstantLattice.eval_binary("-", ConstantValue.constant(10), ConstantValue.constant(3))
        assert result.value == 7

    def test_multiply(self):
        """곱셈"""
        result = ConstantLattice.eval_binary("*", ConstantValue.constant(3), ConstantValue.constant(4))
        assert result.value == 12

    def test_divide(self):
        """나눗셈"""
        result = ConstantLattice.eval_binary("/", ConstantValue.constant(10), ConstantValue.constant(2))
        assert result.value == 5.0

    def test_floor_divide(self):
        """몫 나눗셈"""
        result = ConstantLattice.eval_binary("//", ConstantValue.constant(10), ConstantValue.constant(3))
        assert result.value == 3

    def test_modulo(self):
        """나머지"""
        result = ConstantLattice.eval_binary("%", ConstantValue.constant(10), ConstantValue.constant(3))
        assert result.value == 1

    def test_power(self):
        """거듭제곱"""
        result = ConstantLattice.eval_binary("**", ConstantValue.constant(2), ConstantValue.constant(3))
        assert result.value == 8

    # 비트 연산
    def test_bitwise_and(self):
        """비트 AND"""
        result = ConstantLattice.eval_binary("&", ConstantValue.constant(5), ConstantValue.constant(3))
        assert result.value == 1  # 0b101 & 0b011 = 0b001

    def test_bitwise_or(self):
        """비트 OR"""
        result = ConstantLattice.eval_binary("|", ConstantValue.constant(5), ConstantValue.constant(3))
        assert result.value == 7  # 0b101 | 0b011 = 0b111

    def test_bitwise_xor(self):
        """비트 XOR"""
        result = ConstantLattice.eval_binary("^", ConstantValue.constant(5), ConstantValue.constant(3))
        assert result.value == 6  # 0b101 ^ 0b011 = 0b110

    def test_left_shift(self):
        """왼쪽 시프트"""
        result = ConstantLattice.eval_binary("<<", ConstantValue.constant(1), ConstantValue.constant(3))
        assert result.value == 8  # 1 << 3 = 8

    def test_right_shift(self):
        """오른쪽 시프트"""
        result = ConstantLattice.eval_binary(">>", ConstantValue.constant(8), ConstantValue.constant(2))
        assert result.value == 2  # 8 >> 2 = 2

    # 비교 연산
    def test_equal(self):
        """같음"""
        result = ConstantLattice.eval_binary("==", ConstantValue.constant(5), ConstantValue.constant(5))
        assert result.value is True

        result = ConstantLattice.eval_binary("==", ConstantValue.constant(5), ConstantValue.constant(10))
        assert result.value is False

    def test_not_equal(self):
        """다름"""
        result = ConstantLattice.eval_binary("!=", ConstantValue.constant(5), ConstantValue.constant(10))
        assert result.value is True

    def test_less_than(self):
        """작음"""
        result = ConstantLattice.eval_binary("<", ConstantValue.constant(5), ConstantValue.constant(10))
        assert result.value is True

    def test_less_equal(self):
        """작거나 같음"""
        result = ConstantLattice.eval_binary("<=", ConstantValue.constant(5), ConstantValue.constant(5))
        assert result.value is True

    def test_greater_than(self):
        """큼"""
        result = ConstantLattice.eval_binary(">", ConstantValue.constant(10), ConstantValue.constant(5))
        assert result.value is True

    def test_greater_equal(self):
        """크거나 같음"""
        result = ConstantLattice.eval_binary(">=", ConstantValue.constant(10), ConstantValue.constant(10))
        assert result.value is True


class TestErrorHandling:
    """에러 처리 테스트 (Production-Ready)"""

    def test_zero_division(self):
        """0으로 나누기 → BOTTOM"""
        result = ConstantLattice.eval_binary("/", ConstantValue.constant(1), ConstantValue.constant(0))
        assert result.kind == LatticeValue.BOTTOM

    def test_zero_division_floor(self):
        """0으로 몫 나누기 → BOTTOM"""
        result = ConstantLattice.eval_binary("//", ConstantValue.constant(1), ConstantValue.constant(0))
        assert result.kind == LatticeValue.BOTTOM

    def test_type_error(self):
        """타입 불일치 → BOTTOM"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(1), ConstantValue.constant("a"))
        assert result.kind == LatticeValue.BOTTOM

    def test_overflow(self):
        """오버플로우 → BOTTOM"""
        result = ConstantLattice.eval_binary("**", ConstantValue.constant(2), ConstantValue.constant(10000))
        # 너무 큰 수 → OverflowError or 성공
        # 실패 시 BOTTOM
        assert result.kind in [LatticeValue.CONSTANT, LatticeValue.BOTTOM]

    def test_unknown_operator(self):
        """알 수 없는 연산자 → BOTTOM"""
        result = ConstantLattice.eval_binary("???", ConstantValue.constant(1), ConstantValue.constant(2))
        assert result.kind == LatticeValue.BOTTOM

    def test_top_operand(self):
        """TOP 피연산자 → TOP"""
        result = ConstantLattice.eval_binary("+", ConstantValue.top(), ConstantValue.constant(5))
        assert result.kind == LatticeValue.TOP

    def test_bottom_operand(self):
        """BOTTOM 피연산자 → BOTTOM"""
        result = ConstantLattice.eval_binary("+", ConstantValue.bottom(), ConstantValue.constant(5))
        assert result.kind == LatticeValue.BOTTOM


class TestTypeCoercion:
    """타입 변환 테스트 (Python 의미론)"""

    def test_int_plus_float(self):
        """int + float → float"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(1), ConstantValue.constant(1.5))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 2.5
        assert isinstance(result.value, float)

    def test_string_multiply(self):
        """str * int"""
        result = ConstantLattice.eval_binary("*", ConstantValue.constant("a"), ConstantValue.constant(3))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == "aaa"

    def test_string_concat(self):
        """str + str"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant("hello"), ConstantValue.constant(" world"))
        assert result.value == "hello world"


class TestPythonTruthiness:
    """Python truthiness 테스트 (정확한 구현!)"""

    def test_falsy_none(self):
        """None is falsy"""
        assert ConstantLattice.is_falsy(None) is True
        assert ConstantLattice.is_truthy(None) is False

    def test_falsy_false(self):
        """False is falsy"""
        assert ConstantLattice.is_falsy(False) is True

    def test_falsy_zero_int(self):
        """0 (int) is falsy"""
        assert ConstantLattice.is_falsy(0) is True

    def test_falsy_zero_float(self):
        """0.0 (float) is falsy"""
        assert ConstantLattice.is_falsy(0.0) is True

    def test_falsy_zero_complex(self):
        """0j (complex) is falsy"""
        assert ConstantLattice.is_falsy(0j) is True

    def test_falsy_empty_string(self):
        """Empty string is falsy"""
        assert ConstantLattice.is_falsy("") is True

    def test_falsy_empty_list(self):
        """[] is falsy"""
        assert ConstantLattice.is_falsy([]) is True

    def test_falsy_empty_dict(self):
        """{} is falsy"""
        assert ConstantLattice.is_falsy({}) is True

    def test_falsy_empty_set(self):
        """set() is falsy"""
        assert ConstantLattice.is_falsy(set()) is True

    def test_falsy_empty_tuple(self):
        """() is falsy"""
        assert ConstantLattice.is_falsy(()) is True

    def test_truthy_one(self):
        """1 is truthy"""
        assert ConstantLattice.is_truthy(1) is True
        assert ConstantLattice.is_falsy(1) is False

    def test_truthy_string(self):
        """Non-empty string is truthy"""
        assert ConstantLattice.is_truthy("a") is True

    def test_truthy_list(self):
        """[1] is truthy"""
        assert ConstantLattice.is_truthy([1]) is True

    def test_truthy_negative(self):
        """-1 is truthy"""
        assert ConstantLattice.is_truthy(-1) is True


# Boundary cases
class TestEdgeCases:
    """엣지 케이스 (Production-Ready)"""

    def test_very_large_number(self):
        """매우 큰 수"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(10**100), ConstantValue.constant(1))
        assert result.kind == LatticeValue.CONSTANT
        assert result.value == 10**100 + 1

    def test_negative_numbers(self):
        """음수"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(-5), ConstantValue.constant(-3))
        assert result.value == -8

    def test_float_precision(self):
        """Float 정밀도"""
        result = ConstantLattice.eval_binary("+", ConstantValue.constant(0.1), ConstantValue.constant(0.2))
        assert result.kind == LatticeValue.CONSTANT
        # Float 오차 허용
        assert abs(result.value - 0.3) < 1e-9

    def test_negative_shift(self):
        """음수 시프트 → ValueError → BOTTOM"""
        result = ConstantLattice.eval_binary("<<", ConstantValue.constant(1), ConstantValue.constant(-1))
        assert result.kind == LatticeValue.BOTTOM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
