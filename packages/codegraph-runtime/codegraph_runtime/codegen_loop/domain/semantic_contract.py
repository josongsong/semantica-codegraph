"""
Semantic Contract Validation

순수 로직 기반 계약 검증
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticContract:
    """
    의미적 계약

    순수 데이터, 외부 의존 없음
    """

    function_name: str
    preconditions: list[str]
    postconditions: list[str]
    invariants: list[str]

    def __post_init__(self):
        """Production-Grade Validation"""
        if not self.function_name:
            raise ValueError("function_name cannot be empty")
        # 빈 pre/postconditions 허용 (아직 분석되지 않은 함수)

    def has_invariants(self) -> bool:
        """Invariant 존재 여부"""
        return len(self.invariants) > 0

    def validate(self) -> bool:
        """
        계약 유효성 검증

        TODO: 추후 HCG 기반 실제 검증으로 확장
        """
        return bool(self.function_name)


@dataclass
class ContractViolation:
    """계약 위반"""

    contract: SemanticContract
    violated_condition: str
    reason: str


class ContractValidator:
    """
    계약 검증기 (순수 로직)

    외부 의존 없음
    """

    def validate_contract(self, contract: SemanticContract) -> ContractViolation | None:
        """
        계약 검증

        Returns:
            None if valid, ContractViolation if invalid
        """
        if not contract.validate():
            return ContractViolation(
                contract=contract, violated_condition="structure", reason="Invalid contract structure"
            )

        return None
