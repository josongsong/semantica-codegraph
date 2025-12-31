"""
Port Validator Tests

CRITICAL: 입력 검증 로직의 정확성 검증.

Testing Strategy:
1. Base Case: 정상 입력
2. Edge Case: 경계값 (0, 최대값)
3. Corner Case: 잘못된 타입, None
4. Extreme Case: 매우 큰 값, 매우 작은 값

SOTA-Level: No Fake, No Stub.
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.validators import (
    AtomMatcherValidator,
    ConstraintValidatorValidator,
    PortInputValidator,
    QueryEngineValidator,
)


class TestPortInputValidator:
    """PortInputValidator 베이스 검증."""

    def test_base_validate_max_paths_valid(self):
        """Base: 정상 max_paths."""
        PortInputValidator.validate_max_paths(100)
        PortInputValidator.validate_max_paths(1)
        PortInputValidator.validate_max_paths(1000)

    def test_edge_validate_max_paths_boundary(self):
        """Edge: 경계값 테스트."""
        # Min boundary
        PortInputValidator.validate_max_paths(1)

        # Max boundary (hard limit)
        PortInputValidator.validate_max_paths(10000)

    def test_corner_validate_max_paths_zero(self):
        """Corner: 0은 거부."""
        with pytest.raises(ValueError, match="must be > 0"):
            PortInputValidator.validate_max_paths(0)

    def test_corner_validate_max_paths_negative(self):
        """Corner: 음수는 거부."""
        with pytest.raises(ValueError, match="must be > 0"):
            PortInputValidator.validate_max_paths(-1)

    def test_corner_validate_max_paths_exceeds_hard_limit(self):
        """Corner: Hard limit 초과 거부."""
        with pytest.raises(ValueError, match="exceeds hard limit"):
            PortInputValidator.validate_max_paths(10001)

    def test_corner_validate_max_paths_wrong_type(self):
        """Corner: 잘못된 타입 거부."""
        with pytest.raises(ValueError, match="must be int"):
            PortInputValidator.validate_max_paths("100")

        with pytest.raises(ValueError, match="must be int"):
            PortInputValidator.validate_max_paths(100.5)

    def test_edge_validate_max_paths_strict_mode(self):
        """Edge: strict 모드는 recommended limit 강제."""
        # Recommended limit 내에서는 OK
        PortInputValidator.validate_max_paths(1000, strict=True)

        # Recommended limit 초과는 거부
        with pytest.raises(ValueError, match="exceeds recommended limit"):
            PortInputValidator.validate_max_paths(1001, strict=True)

    def test_base_validate_max_depth_valid(self):
        """Base: 정상 max_depth."""
        PortInputValidator.validate_max_depth(10)
        PortInputValidator.validate_max_depth(50)

    def test_edge_validate_max_depth_boundary(self):
        """Edge: 경계값."""
        PortInputValidator.validate_max_depth(1)
        PortInputValidator.validate_max_depth(100)

    def test_corner_validate_max_depth_invalid(self):
        """Corner: 잘못된 max_depth."""
        with pytest.raises(ValueError, match="must be > 0"):
            PortInputValidator.validate_max_depth(0)

        with pytest.raises(ValueError, match="exceeds hard limit"):
            PortInputValidator.validate_max_depth(101)

    def test_base_validate_timeout_valid(self):
        """Base: 정상 timeout."""
        PortInputValidator.validate_timeout(60.0)
        PortInputValidator.validate_timeout(30)
        PortInputValidator.validate_timeout(1.5)

    def test_edge_validate_timeout_boundary(self):
        """Edge: timeout 경계값."""
        PortInputValidator.validate_timeout(0.1)  # Min
        PortInputValidator.validate_timeout(300.0)  # Max

    def test_corner_validate_timeout_invalid(self):
        """Corner: 잘못된 timeout."""
        with pytest.raises(ValueError, match="too small"):
            PortInputValidator.validate_timeout(0.05)

        with pytest.raises(ValueError, match="too large"):
            PortInputValidator.validate_timeout(301.0)

        with pytest.raises(ValueError, match="must be numeric"):
            PortInputValidator.validate_timeout("60")

    def test_base_validate_compiled_policy_valid(self):
        """Base: 정상 compiled_policy."""

        class MockCompiledPolicy:
            flow_query = "query"

        PortInputValidator.validate_compiled_policy(MockCompiledPolicy())

    def test_corner_validate_compiled_policy_none(self):
        """Corner: None policy 거부."""
        with pytest.raises(ValueError, match="cannot be None"):
            PortInputValidator.validate_compiled_policy(None)

    def test_corner_validate_compiled_policy_missing_attr(self):
        """Corner: flow_query 속성 없으면 거부."""

        class InvalidPolicy:
            pass

        with pytest.raises(ValueError, match="must have 'flow_query'"):
            PortInputValidator.validate_compiled_policy(InvalidPolicy())

    def test_base_validate_ir_document_valid(self):
        """Base: 정상 IR document."""

        class MockIRDoc:
            def get_all_expressions(self):
                return []

        PortInputValidator.validate_ir_document(MockIRDoc())

    def test_corner_validate_ir_document_none(self):
        """Corner: None ir_doc 거부."""
        with pytest.raises(ValueError, match="cannot be None"):
            PortInputValidator.validate_ir_document(None)

    def test_corner_validate_ir_document_missing_method(self):
        """Corner: get_all_expressions 없으면 거부."""

        class InvalidIRDoc:
            pass

        with pytest.raises(ValueError, match="must have 'get_all_expressions'"):
            PortInputValidator.validate_ir_document(InvalidIRDoc())

    def test_base_validate_path_valid(self):
        """Base: 정상 path."""

        class MockPath:
            pass

        PortInputValidator.validate_path(MockPath())

    def test_corner_validate_path_none(self):
        """Corner: None path 거부."""
        with pytest.raises(ValueError, match="cannot be None"):
            PortInputValidator.validate_path(None)

    def test_base_validate_constraints_valid(self):
        """Base: 정상 constraints."""
        PortInputValidator.validate_constraints({})
        PortInputValidator.validate_constraints({"max_length": 50})
        PortInputValidator.validate_constraints({"max_length": 50, "min_confidence": 0.8, "require_sanitizer": True})

    def test_corner_validate_constraints_unknown_key(self):
        """Corner: 알 수 없는 constraint key 거부."""
        with pytest.raises(KeyError, match="Unknown constraint"):
            PortInputValidator.validate_constraints({"unknown_key": True})

    def test_corner_validate_constraints_wrong_type(self):
        """Corner: 잘못된 타입 거부."""
        with pytest.raises(TypeError, match="must be int"):
            PortInputValidator.validate_constraints({"max_length": "50"})

        with pytest.raises(TypeError, match="must be numeric"):
            PortInputValidator.validate_constraints({"min_confidence": "0.8"})

        with pytest.raises(TypeError, match="must be bool"):
            PortInputValidator.validate_constraints({"require_sanitizer": "true"})


class TestQueryEngineValidator:
    """QueryEngineValidator 검증."""

    def test_base_validate_all_valid(self):
        """Base: 모든 파라미터 정상."""

        class MockPolicy:
            flow_query = "query"

        QueryEngineValidator.validate_all(
            compiled_policy=MockPolicy(),
            max_paths=100,
            max_depth=20,
            timeout_seconds=60.0,
        )

    def test_corner_validate_all_any_invalid_fails(self):
        """Corner: 하나라도 잘못되면 실패."""

        class MockPolicy:
            flow_query = "query"

        # Invalid max_paths
        with pytest.raises(ValueError):
            QueryEngineValidator.validate_all(
                compiled_policy=MockPolicy(),
                max_paths=0,  # Invalid
                max_depth=20,
                timeout_seconds=60.0,
            )

        # Invalid timeout
        with pytest.raises(ValueError):
            QueryEngineValidator.validate_all(
                compiled_policy=MockPolicy(),
                max_paths=100,
                max_depth=20,
                timeout_seconds=0.01,  # Too small
            )


class TestAtomMatcherValidator:
    """AtomMatcherValidator 검증."""

    def test_base_validate_all_valid(self):
        """Base: 정상 파라미터."""

        class MockIRDoc:
            def get_all_expressions(self):
                return []

        AtomMatcherValidator.validate_all(ir_doc=MockIRDoc(), atoms=[])

    def test_corner_validate_all_none_ir_doc(self):
        """Corner: None ir_doc 거부."""
        with pytest.raises(ValueError, match="cannot be None"):
            AtomMatcherValidator.validate_all(ir_doc=None, atoms=[])

    def test_corner_validate_all_atoms_not_list(self):
        """Corner: atoms가 list가 아니면 거부."""

        class MockIRDoc:
            def get_all_expressions(self):
                return []

        with pytest.raises(ValueError, match="must be list"):
            AtomMatcherValidator.validate_all(ir_doc=MockIRDoc(), atoms="not a list")


class TestConstraintValidatorValidator:
    """ConstraintValidatorValidator 검증."""

    def test_base_validate_all_valid(self):
        """Base: 정상 파라미터."""

        class MockPath:
            pass

        ConstraintValidatorValidator.validate_all(path=MockPath(), constraints={})
        ConstraintValidatorValidator.validate_all(path=MockPath(), constraints={"max_length": 50})

    def test_corner_validate_all_none_path(self):
        """Corner: None path 거부."""
        with pytest.raises(ValueError, match="cannot be None"):
            ConstraintValidatorValidator.validate_all(path=None, constraints={})

    def test_corner_validate_all_constraints_not_dict(self):
        """Corner: constraints가 dict가 아니면 거부."""

        class MockPath:
            pass

        with pytest.raises(ValueError, match="must be dict"):
            ConstraintValidatorValidator.validate_all(path=MockPath(), constraints=[])


class TestValidatorExtreme:
    """Extreme case 검증."""

    def test_extreme_max_paths_boundary_values(self):
        """Extreme: max_paths 극한 경계값."""
        # INT_MAX 같은 극한값
        with pytest.raises(ValueError, match="exceeds hard limit"):
            PortInputValidator.validate_max_paths(2**31 - 1)

    def test_extreme_timeout_precision(self):
        """Extreme: timeout 소수점 정밀도."""
        # 극히 작은 timeout
        PortInputValidator.validate_timeout(0.1)

        # 극히 큰 timeout
        PortInputValidator.validate_timeout(300.0)

    def test_extreme_constraints_all_keys(self):
        """Extreme: 모든 constraint 동시 사용."""
        PortInputValidator.validate_constraints(
            {
                "max_length": 100,
                "min_confidence": 0.9,
                "require_sanitizer": True,
                "max_paths": 50,
                "max_depth": 30,
            }
        )
