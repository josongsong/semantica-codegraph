"""
Global Error Schema (RFC-SEM-022)

표준화된 에러 응답 형식.

모든 API 에러는 이 형식을 따름.
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """에러 상세 정보."""

    field: str | None = Field(None, description="문제가 된 필드")
    reason: str | None = Field(None, description="상세 이유")
    value: Any = Field(None, description="문제가 된 값")


class SemanticaError(BaseModel):
    """
    Global Error Schema.

    RFC-SEM-022 표준 에러 형식.

    Example:
        {
            "code": "err_common_invalid_argument",
            "message": "Invalid workspace_id",
            "details": {},
            "trace_id": "trace_abc"
        }
    """

    code: str = Field(..., description="에러 코드 (err_{domain}_{type})")
    message: str = Field(..., description="사람이 읽을 수 있는 메시지")
    details: dict[str, Any] = Field(default_factory=dict, description="추가 상세")
    trace_id: str | None = Field(None, description="추적 ID")

    model_config = {"frozen": True}


# ============================================================
# Error Code Definitions
# ============================================================

# Common Errors
ERR_INVALID_ARGUMENT = "err_common_invalid_argument"
ERR_NOT_FOUND = "err_common_not_found"
ERR_ALREADY_EXISTS = "err_common_already_exists"
ERR_PERMISSION_DENIED = "err_common_permission_denied"
ERR_INTERNAL = "err_common_internal"
ERR_TIMEOUT = "err_common_timeout"
ERR_RATE_LIMITED = "err_common_rate_limited"

# Workspace Errors
ERR_WORKSPACE_NOT_FOUND = "err_workspace_not_found"
ERR_WORKSPACE_IMMUTABLE = "err_workspace_immutable"
ERR_WORKSPACE_HAS_CHILDREN = "err_workspace_has_children"

# Execution Errors
ERR_EXECUTION_NOT_FOUND = "err_execution_not_found"
ERR_EXECUTION_FAILED = "err_execution_failed"
ERR_EXECUTION_CANCELLED = "err_execution_cancelled"

# Job Errors
ERR_JOB_NOT_FOUND = "err_job_not_found"
ERR_JOB_FAILED = "err_job_failed"
ERR_JOB_TIMEOUT = "err_job_timeout"

# Analysis Errors
ERR_ANALYSIS_INVALID_SPEC = "err_analysis_invalid_spec"
ERR_ANALYSIS_UNSUPPORTED = "err_analysis_unsupported"

# Graph Errors
ERR_GRAPH_SYMBOL_NOT_FOUND = "err_graph_symbol_not_found"
ERR_GRAPH_NO_PATH = "err_graph_no_path"

# Verification Errors
ERR_VERIFY_COMPILE_FAILED = "err_verify_compile_failed"
ERR_VERIFY_TYPE_FAILED = "err_verify_type_failed"
ERR_VERIFY_REGRESSION = "err_verify_regression"


# ============================================================
# Factory Functions
# ============================================================


def create_error(
    code: str,
    message: str,
    trace_id: str | None = None,
    **details: Any,
) -> SemanticaError:
    """표준 에러 생성."""
    return SemanticaError(
        code=code,
        message=message,
        details=details,
        trace_id=trace_id,
    )


def not_found_error(
    resource: str,
    resource_id: str,
    trace_id: str | None = None,
) -> SemanticaError:
    """Not Found 에러 생성."""
    return SemanticaError(
        code=ERR_NOT_FOUND,
        message=f"{resource} not found: {resource_id}",
        details={"resource": resource, "resource_id": resource_id},
        trace_id=trace_id,
    )


def invalid_argument_error(
    field: str,
    reason: str,
    value: Any = None,
    trace_id: str | None = None,
) -> SemanticaError:
    """Invalid Argument 에러 생성."""
    return SemanticaError(
        code=ERR_INVALID_ARGUMENT,
        message=f"Invalid {field}: {reason}",
        details={"field": field, "reason": reason, "value": value},
        trace_id=trace_id,
    )


def internal_error(
    message: str,
    trace_id: str | None = None,
    **details: Any,
) -> SemanticaError:
    """Internal Error 생성."""
    return SemanticaError(
        code=ERR_INTERNAL,
        message=message,
        details=details,
        trace_id=trace_id,
    )
