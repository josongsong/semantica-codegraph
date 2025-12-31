"""
Semantic Contract Tests

SOTA-Level: Base + Edge Cases
Production-Grade: Zero assumptions
"""

import pytest

from codegraph_runtime.codegen_loop.domain.semantic_contract import SemanticContract


class TestSemanticContract:
    """SemanticContract 테스트 (Base Cases)"""

    def test_valid_contract(self):
        """Base: 유효한 계약"""
        contract = SemanticContract(
            function_name="process_payment",
            preconditions=["amount > 0", "account is not None"],
            postconditions=["transaction.status == 'completed'"],
            invariants=["balance >= 0"],
        )

        assert contract.function_name == "process_payment"
        assert len(contract.preconditions) == 2
        assert len(contract.postconditions) == 1
        assert len(contract.invariants) == 1

    def test_contract_with_no_invariants(self):
        """Base: invariant 없는 계약"""
        contract = SemanticContract(
            function_name="simple_func",
            preconditions=["x > 0"],
            postconditions=["result > 0"],
            invariants=[],
        )

        assert len(contract.invariants) == 0
        assert contract.has_invariants() is False

    def test_contract_with_invariants(self):
        """Base: invariant 있는 계약"""
        contract = SemanticContract(
            function_name="bank_transfer",
            preconditions=["amount > 0"],
            postconditions=["transfer.completed"],
            invariants=["total_balance constant", "no_negative_balance"],
        )

        assert contract.has_invariants()
        assert len(contract.invariants) == 2

    def test_empty_preconditions_allowed(self):
        """Edge: 빈 preconditions 허용 (아직 분석되지 않은 함수)"""
        contract = SemanticContract(
            function_name="func",
            preconditions=[],
            postconditions=["result ok"],
            invariants=[],
        )
        assert len(contract.preconditions) == 0

    def test_empty_postconditions_allowed(self):
        """Edge: 빈 postconditions 허용 (아직 분석되지 않은 함수)"""
        contract = SemanticContract(
            function_name="func",
            preconditions=["input ok"],
            postconditions=[],
            invariants=[],
        )
        assert len(contract.postconditions) == 0

    def test_all_empty_conditions_allowed(self):
        """Edge: 모든 조건 비어있음 허용 (minimal contract)"""
        contract = SemanticContract(
            function_name="minimal_func",
            preconditions=[],
            postconditions=[],
            invariants=[],
        )
        assert contract.function_name == "minimal_func"
        assert contract.validate()  # function_name만 있으면 valid

    def test_empty_function_name_raises(self):
        """Edge: 빈 function_name은 에러"""
        with pytest.raises(ValueError, match="function_name cannot be empty"):
            SemanticContract(
                function_name="",
                preconditions=["x > 0"],
                postconditions=["y > 0"],
                invariants=[],
            )


class TestSemanticContractEdgeCases:
    """Edge Cases"""

    def test_single_precondition(self):
        """Edge: 단일 precondition"""
        contract = SemanticContract(
            function_name="func",
            preconditions=["x > 0"],
            postconditions=["result > 0"],
            invariants=[],
        )

        assert len(contract.preconditions) == 1

    def test_single_postcondition(self):
        """Edge: 단일 postcondition"""
        contract = SemanticContract(
            function_name="func",
            preconditions=["input valid"],
            postconditions=["success"],
            invariants=[],
        )

        assert len(contract.postconditions) == 1

    def test_many_preconditions(self):
        """Edge: 많은 preconditions"""
        contract = SemanticContract(
            function_name="complex_func",
            preconditions=[f"check_{i}" for i in range(10)],
            postconditions=["result ok"],
            invariants=[],
        )

        assert len(contract.preconditions) == 10

    def test_many_postconditions(self):
        """Edge: 많은 postconditions"""
        contract = SemanticContract(
            function_name="complex_func",
            preconditions=["input ok"],
            postconditions=[f"guarantee_{i}" for i in range(10)],
            invariants=[],
        )

        assert len(contract.postconditions) == 10

    def test_many_invariants(self):
        """Edge: 많은 invariants"""
        contract = SemanticContract(
            function_name="stateful_func",
            preconditions=["input ok"],
            postconditions=["result ok"],
            invariants=[f"invariant_{i}" for i in range(10)],
        )

        assert len(contract.invariants) == 10
        assert contract.has_invariants()

    def test_unicode_conditions(self):
        """Edge: Unicode 조건"""
        contract = SemanticContract(
            function_name="한글함수",
            preconditions=["금액 > 0", "계좌 존재"],
            postconditions=["결과 성공"],
            invariants=["잔액 >= 0"],
        )

        assert "금액" in contract.preconditions[0]
        assert contract.function_name == "한글함수"

    def test_long_function_name(self):
        """Edge: 매우 긴 함수 이름"""
        long_name = "very_long_function_name_" * 10
        contract = SemanticContract(
            function_name=long_name,
            preconditions=["x > 0"],
            postconditions=["y > 0"],
            invariants=[],
        )

        assert contract.function_name == long_name
        assert len(contract.function_name) > 100

    def test_complex_condition_expressions(self):
        """Edge: 복잡한 조건식"""
        contract = SemanticContract(
            function_name="complex_validation",
            preconditions=[
                "(x > 0 AND x < 100) OR (y == 'special')",
                "len(items) >= min_count AND all(item.valid for item in items)",
            ],
            postconditions=[
                "result.status in ['success', 'partial']",
                "result.data is not None OR result.error is not None",
            ],
            invariants=["state.invariant_holds()"],
        )

        assert len(contract.preconditions) == 2
        assert "AND" in contract.preconditions[0]
        assert "OR" in contract.postconditions[1]


class TestSemanticContractIntegration:
    """Integration Tests"""

    def test_payment_contract(self):
        """Integration: 결제 함수 계약"""
        contract = SemanticContract(
            function_name="process_payment",
            preconditions=[
                "amount > 0",
                "account.balance >= amount",
                "account.status == 'active'",
            ],
            postconditions=[
                "transaction.completed == True",
                "account.balance == old_balance - amount",
                "receipt.generated == True",
            ],
            invariants=[
                "account.balance >= 0",
                "system.total_balance == constant",
            ],
        )

        assert contract.function_name == "process_payment"
        assert len(contract.preconditions) == 3
        assert len(contract.postconditions) == 3
        assert len(contract.invariants) == 2
        assert contract.has_invariants()

    def test_authentication_contract(self):
        """Integration: 인증 함수 계약"""
        contract = SemanticContract(
            function_name="authenticate_user",
            preconditions=[
                "username is not None",
                "password is not None",
                "len(password) >= 8",
            ],
            postconditions=[
                "result.authenticated == True OR result.reason != None",
                "session.created == result.authenticated",
            ],
            invariants=[
                "user.login_attempts <= MAX_ATTEMPTS",
            ],
        )

        assert contract.function_name == "authenticate_user"
        assert contract.has_invariants()

    def test_database_transaction_contract(self):
        """Integration: DB 트랜잭션 계약"""
        contract = SemanticContract(
            function_name="update_record",
            preconditions=[
                "connection.is_open()",
                "record.id exists in database",
                "user.has_permission('write')",
            ],
            postconditions=[
                "record.updated_at > old_updated_at",
                "record.version == old_version + 1",
                "transaction.committed OR transaction.rolled_back",
            ],
            invariants=[
                "database.consistency_maintained()",
                "no_orphan_records()",
            ],
        )

        assert len(contract.preconditions) == 3
        assert len(contract.postconditions) == 3
        assert len(contract.invariants) == 2
