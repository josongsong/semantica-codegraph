"""
Global Error Schema 테스트 (RFC-SEM-022)

Test Coverage:
- Base Case: 기본 에러 생성
- Edge Case: 특수 문자, 긴 메시지
- Corner Case: None 값, 빈 문자열
- Extreme Case: 매우 긴 메시지, 깊은 중첩
"""

import pytest

from codegraph_engine.shared_kernel.contracts import (
    ERR_INTERNAL,
    ERR_INVALID_ARGUMENT,
    ERR_NOT_FOUND,
    SemanticaError,
    create_error,
    internal_error,
    invalid_argument_error,
    not_found_error,
)


class TestSemanticaError:
    """SemanticaError 모델 테스트."""

    def test_base_case_creation(self):
        """Base Case: 기본 생성."""
        error = SemanticaError(
            code="err_test_example",
            message="Test error message",
            details={"key": "value"},
            trace_id="trace_123",
        )

        assert error.code == "err_test_example"
        assert error.message == "Test error message"
        assert error.details == {"key": "value"}
        assert error.trace_id == "trace_123"

    def test_minimal_creation(self):
        """Corner Case: 최소 필드."""
        error = SemanticaError(
            code="err_minimal",
            message="Minimal",
        )

        assert error.code == "err_minimal"
        assert error.details == {}
        assert error.trace_id is None

    def test_empty_message(self):
        """Edge Case: 빈 메시지."""
        error = SemanticaError(
            code="err_empty",
            message="",
        )
        assert error.message == ""

    def test_unicode_message(self):
        """Edge Case: 유니코드 메시지."""
        error = SemanticaError(
            code="err_unicode",
            message="에러: 파일을 찾을 수 없습니다 🔍",
            details={"path": "경로/파일.txt"},
        )

        assert "에러" in error.message
        assert "🔍" in error.message
        assert error.details["path"] == "경로/파일.txt"

    def test_long_message(self):
        """Extreme Case: 긴 메시지."""
        long_message = "Error: " + "x" * 10000
        error = SemanticaError(
            code="err_long",
            message=long_message,
        )

        assert len(error.message) > 10000

    def test_nested_details(self):
        """Extreme Case: 깊은 중첩 details."""
        nested = {"level1": {"level2": {"level3": {"level4": "deep"}}}}
        error = SemanticaError(
            code="err_nested",
            message="Nested",
            details=nested,
        )

        assert error.details["level1"]["level2"]["level3"]["level4"] == "deep"

    def test_special_characters_in_code(self):
        """Edge Case: 코드에 특수 문자."""
        error = SemanticaError(
            code="err_special-chars_123",
            message="Special",
        )
        assert error.code == "err_special-chars_123"

    def test_immutability(self):
        """Edge Case: Frozen 확인."""
        error = SemanticaError(
            code="err_frozen",
            message="Frozen test",
        )

        with pytest.raises(Exception):
            error.code = "changed"


class TestErrorFactories:
    """에러 팩토리 함수 테스트."""

    def test_create_error_base(self):
        """Base Case: create_error."""
        error = create_error(
            code="err_custom",
            message="Custom error",
            trace_id="trace_1",
            extra="value",
        )

        assert error.code == "err_custom"
        assert error.message == "Custom error"
        assert error.trace_id == "trace_1"
        assert error.details["extra"] == "value"

    def test_not_found_error(self):
        """Base Case: not_found_error."""
        error = not_found_error("Workspace", "ws_123", "trace_abc")

        assert error.code == ERR_NOT_FOUND
        assert "Workspace" in error.message
        assert "ws_123" in error.message
        assert error.details["resource"] == "Workspace"
        assert error.details["resource_id"] == "ws_123"

    def test_not_found_without_trace(self):
        """Corner Case: trace_id 없이."""
        error = not_found_error("User", "user_456")

        assert error.trace_id is None

    def test_invalid_argument_error(self):
        """Base Case: invalid_argument_error."""
        error = invalid_argument_error(
            field="email",
            reason="Invalid format",
            value="not-an-email",
            trace_id="trace_def",
        )

        assert error.code == ERR_INVALID_ARGUMENT
        assert "email" in error.message
        assert "Invalid format" in error.message
        assert error.details["field"] == "email"
        assert error.details["value"] == "not-an-email"

    def test_invalid_argument_null_value(self):
        """Corner Case: None 값."""
        error = invalid_argument_error(
            field="name",
            reason="Required",
            value=None,
        )

        assert error.details["value"] is None

    def test_internal_error(self):
        """Base Case: internal_error."""
        error = internal_error(
            message="Database connection failed",
            trace_id="trace_ghi",
            retry_after=30,
        )

        assert error.code == ERR_INTERNAL
        assert "Database" in error.message
        assert error.details["retry_after"] == 30

    def test_internal_error_minimal(self):
        """Corner Case: 최소 파라미터."""
        error = internal_error("Unknown error")

        assert error.code == ERR_INTERNAL
        assert error.trace_id is None


class TestErrorCodes:
    """에러 코드 상수 테스트."""

    def test_error_code_format(self):
        """Base Case: 코드 형식 검증."""
        codes = [ERR_NOT_FOUND, ERR_INVALID_ARGUMENT, ERR_INTERNAL]

        for code in codes:
            # err_ prefix
            assert code.startswith("err_")
            # underscore separated
            parts = code.split("_")
            assert len(parts) >= 3  # err_domain_type

    def test_error_codes_unique(self):
        """Edge Case: 코드 중복 없음."""
        from codegraph_engine.shared_kernel.contracts.errors import (
            ERR_ALREADY_EXISTS,
            ERR_ANALYSIS_INVALID_SPEC,
            ERR_ANALYSIS_UNSUPPORTED,
            ERR_EXECUTION_CANCELLED,
            ERR_EXECUTION_FAILED,
            ERR_EXECUTION_NOT_FOUND,
            ERR_GRAPH_NO_PATH,
            ERR_GRAPH_SYMBOL_NOT_FOUND,
            ERR_JOB_FAILED,
            ERR_JOB_NOT_FOUND,
            ERR_JOB_TIMEOUT,
            ERR_PERMISSION_DENIED,
            ERR_RATE_LIMITED,
            ERR_TIMEOUT,
            ERR_VERIFY_COMPILE_FAILED,
            ERR_VERIFY_REGRESSION,
            ERR_VERIFY_TYPE_FAILED,
            ERR_WORKSPACE_HAS_CHILDREN,
            ERR_WORKSPACE_IMMUTABLE,
            ERR_WORKSPACE_NOT_FOUND,
        )

        all_codes = [
            ERR_NOT_FOUND,
            ERR_INVALID_ARGUMENT,
            ERR_INTERNAL,
            ERR_ALREADY_EXISTS,
            ERR_PERMISSION_DENIED,
            ERR_TIMEOUT,
            ERR_RATE_LIMITED,
            ERR_WORKSPACE_NOT_FOUND,
            ERR_WORKSPACE_IMMUTABLE,
            ERR_WORKSPACE_HAS_CHILDREN,
            ERR_EXECUTION_NOT_FOUND,
            ERR_EXECUTION_FAILED,
            ERR_EXECUTION_CANCELLED,
            ERR_JOB_NOT_FOUND,
            ERR_JOB_FAILED,
            ERR_JOB_TIMEOUT,
            ERR_ANALYSIS_INVALID_SPEC,
            ERR_ANALYSIS_UNSUPPORTED,
            ERR_GRAPH_SYMBOL_NOT_FOUND,
            ERR_GRAPH_NO_PATH,
            ERR_VERIFY_COMPILE_FAILED,
            ERR_VERIFY_TYPE_FAILED,
            ERR_VERIFY_REGRESSION,
        ]

        assert len(all_codes) == len(set(all_codes)), "Duplicate error codes found!"
