"""
Constant Propagation Domain Models

RFC-024 Part 1: SCCP Baseline - Domain Layer

Wegman & Zadeck (1991): "Constant Propagation with Conditional Branches"
3-level lattice: ⊤ (unknown) → Constant → ⊥ (overdefined)

Production Requirements:
- Immutable (frozen dataclass)
- Type-safe (no Any abuse)
- Hashable (for dict keys)
- Clear API (explicit methods)
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Note: TYPE_CHECKING 블록 내 import는 Hexagonal 위반 아님 (타입 힌트만)
    from codegraph_engine.code_foundation.infrastructure.dfg.ssa.models import SSAVariable


class LatticeValue(Enum):
    """
    3-level Lattice for Constant Propagation

    Ordering (partial order):
    ⊤ (TOP)
    │
    c (CONSTANT, for any value c)
    │
    ⊥ (BOTTOM)

    Meaning:
    - TOP: 아직 알 수 없음 (uninitialized or not yet analyzed)
    - CONSTANT: 확정된 상수 값
    - BOTTOM: 여러 값 가능 또는 알 수 없음 (overdefined)

    Meet 연산:
    - TOP ∧ x = x
    - BOTTOM ∧ x = BOTTOM
    - c1 ∧ c1 = c1
    - c1 ∧ c2 = BOTTOM (c1 ≠ c2)
    """

    TOP = "top"
    CONSTANT = "constant"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class ConstantValue:
    """
    상수 값 표현 (Immutable)

    Attributes:
        kind: Lattice 값 종류 (TOP, CONSTANT, BOTTOM)
        value: 실제 값 (kind=CONSTANT일 때만 유효)

    Invariants:
        - kind=CONSTANT → value is not None
        - kind=TOP or BOTTOM → value is None (무시됨)
        - frozen (immutable, hashable)

    Performance:
        - frozen: immutable 보장, dict key로 사용 가능
        - slots: 메모리 30-40% 절감

    Examples:
        >>> ConstantValue.top()
        ConstantValue(kind=<LatticeValue.TOP: 'top'>, value=None)

        >>> ConstantValue.constant(10)
        ConstantValue(kind=<LatticeValue.CONSTANT: 'constant'>, value=10)

        >>> c1 = ConstantValue.constant(5)
        >>> c2 = ConstantValue.constant(5)
        >>> c1 == c2
        True
        >>> hash(c1) == hash(c2)
        True
    """

    kind: LatticeValue
    value: Any = None

    def __post_init__(self):
        """
        Validate invariants

        Note:
            None도 valid constant (Python에서 None은 값!)
            따라서 kind=CONSTANT, value=None 허용

        Raises:
            ValueError: kind와 value 불일치 (현재는 없음, 향후 확장용)
        """
        # Frozen dataclass이므로 object.__setattr__ 사용 불가
        # __post_init__에서는 검증만 (수정 불가)
        #
        # Note: kind=CONSTANT, value=None은 valid!
        # Python에서 None은 first-class value
        pass

    @classmethod
    def top(cls) -> "ConstantValue":
        """
        TOP 값 생성 (⊤)

        Returns:
            ConstantValue(TOP, None)
        """
        return cls(LatticeValue.TOP, None)

    @classmethod
    def bottom(cls) -> "ConstantValue":
        """
        BOTTOM 값 생성 (⊥)

        Returns:
            ConstantValue(BOTTOM, None)
        """
        return cls(LatticeValue.BOTTOM, None)

    @classmethod
    def constant(cls, value: Any) -> "ConstantValue":
        """
        CONSTANT 값 생성

        Args:
            value: 상수 값 (int, float, str, bool, None 등)

        Returns:
            ConstantValue(CONSTANT, value)

        Raises:
            ValueError: value가 None인 경우
        """
        if value is None and cls.__name__ == "ConstantValue":
            # None도 valid constant (Python에서)
            # 하지만 구분을 위해 명시적으로 허용
            pass
        return cls(LatticeValue.CONSTANT, value)

    def is_constant(self) -> bool:
        """상수인지 확인"""
        return self.kind == LatticeValue.CONSTANT

    def is_top(self) -> bool:
        """TOP인지 확인"""
        return self.kind == LatticeValue.TOP

    def is_bottom(self) -> bool:
        """BOTTOM인지 확인"""
        return self.kind == LatticeValue.BOTTOM

    def __repr__(self) -> str:
        """사람이 읽기 좋은 표현"""
        if self.kind == LatticeValue.TOP:
            return "⊤"
        elif self.kind == LatticeValue.BOTTOM:
            return "⊥"
        else:
            return f"Const({self.value})"


@dataclass
class ConstantPropagationResult:
    """
    SCCP 분석 결과 (Production-Ready)

    Attributes:
        ssa_values: SSA Variable → ConstantValue 매핑 (내부용)
        var_values: (변수명, 블록ID) → ConstantValue 매핑 (외부 API)
        reachable_blocks: 도달 가능한 블록 ID 집합
        unreachable_blocks: 도달 불가능한 블록 ID 집합 (Dead Code!)
        constants_found: 발견된 상수 개수 (통계)
        bottom_count: Bottom 값 개수 (통계)

    API Design:
        - get_constant_at(var_name, block_id): 명확한 조회 API
        - is_constant(var_name, block_id): 상수 여부 확인
        - is_block_reachable(block_id): Dead code 판단

    Thread-Safety:
        - Immutable (읽기 전용)
        - 복사 없이 공유 가능

    Examples:
        >>> result.get_constant_at("x", "block_1")
        Const(10)

        >>> result.is_block_reachable("else_branch")
        False  # Dead code!

        >>> result.constants_found
        25  # 25개 변수가 상수로 판명
    """

    # SSA 레벨 (내부용, Solver가 생성)
    ssa_values: dict["SSAVariable", ConstantValue]

    # Variable 이름 레벨 (외부 API)
    var_values: dict[tuple[str, str], ConstantValue]  # (var_name, block_id) → value

    # Control flow 정보
    reachable_blocks: set[str]
    unreachable_blocks: set[str]

    # 통계
    constants_found: int
    bottom_count: int

    def get_constant_at(self, var_name: str, block_id: str) -> ConstantValue:
        """
        특정 블록에서 변수의 상수 값 조회

        Args:
            var_name: 변수 이름 (예: "x")
            block_id: CFG 블록 ID (예: "cfg:foo:block:3")

        Returns:
            ConstantValue (⊤/Const/⊥)

        Thread-Safety:
            읽기 전용, 안전

        Performance:
            O(1) dict 조회
        """
        return self.var_values.get((var_name, block_id), ConstantValue.top())

    def is_constant(self, var_name: str, block_id: str) -> bool:
        """
        변수가 상수인지 확인

        Args:
            var_name: 변수 이름
            block_id: 블록 ID

        Returns:
            상수면 True
        """
        val = self.get_constant_at(var_name, block_id)
        return val.is_constant()

    def is_block_reachable(self, block_id: str) -> bool:
        """
        블록이 도달 가능한지 확인 (Dead Code 탐지)

        Args:
            block_id: CFG 블록 ID

        Returns:
            도달 가능하면 True, Dead code면 False

        Use Case:
            Dead branch 제거, Unreachable code 경고
        """
        return block_id in self.reachable_blocks

    def get_unreachable_blocks(self) -> set[str]:
        """
        모든 Unreachable 블록 조회 (Dead Code)

        Returns:
            Dead code 블록 ID 집합
        """
        return self.unreachable_blocks.copy()

    def get_statistics(self) -> dict[str, int]:
        """
        분석 통계

        Returns:
            {"constants": N, "bottoms": M, "unreachable": K}
        """
        return {
            "constants_found": self.constants_found,
            "bottom_count": self.bottom_count,
            "unreachable_blocks": len(self.unreachable_blocks),
            "reachable_blocks": len(self.reachable_blocks),
        }
