"""
Codegraph Exception Hierarchy

표준화된 예외 계층으로 일관된 에러 처리를 제공합니다.

사용 가이드:
    1. 복구 가능한 에러 → 로그 후 계속
    2. 복구 불가능한 에러 → 로그 후 재발생
    3. 외부 에러 → 커스텀 예외로 래핑

예시:
    try:
        result = external_service.call()
    except ExternalError as e:
        raise InfrastructureError("External service failed") from e
"""

from typing import Any


class CodegraphError(Exception):
    """Base exception for all Codegraph errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """
        Initialize Codegraph error.

        Args:
            message: Human-readable error message
            details: Optional additional details for debugging
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


# ============================================================
# Infrastructure Errors
# ============================================================


class InfrastructureError(CodegraphError):
    """Infrastructure failures (database, cache, external services)."""

    pass


class DatabaseError(InfrastructureError):
    """Database operation failures."""

    pass


class CacheError(InfrastructureError):
    """Cache operation failures."""

    pass


class ExternalServiceError(InfrastructureError):
    """External service failures (LLM, embedding, etc.)."""

    pass


class ConnectionError(InfrastructureError):
    """Connection failures (network, database, etc.)."""

    pass


# ============================================================
# Validation Errors
# ============================================================


class ValidationError(CodegraphError):
    """Input validation failures."""

    pass


class InvalidInputError(ValidationError):
    """Invalid user input."""

    pass


class InvalidConfigurationError(ValidationError):
    """Invalid configuration."""

    pass


# ============================================================
# Indexing Errors
# ============================================================


class IndexingError(CodegraphError):
    """Indexing operation failures."""

    pass


class ParsingError(IndexingError):
    """Code parsing failures."""

    pass


class IRGenerationError(IndexingError):
    """IR generation failures."""

    pass


class GraphBuildingError(IndexingError):
    """Graph building failures."""

    pass


class ChunkingError(IndexingError):
    """Chunking failures."""

    pass


# ============================================================
# Retrieval Errors
# ============================================================


class RetrievalError(CodegraphError):
    """Retrieval/search operation failures."""

    pass


class SearchError(RetrievalError):
    """Search operation failures."""

    pass


class IntentAnalysisError(RetrievalError):
    """Intent analysis failures."""

    pass


class ScopeSelectionError(RetrievalError):
    """Scope selection failures."""

    pass


# ============================================================
# Agent Errors
# ============================================================


class AgentError(CodegraphError):
    """Agent operation failures."""

    pass


class ModeExecutionError(AgentError):
    """Agent mode execution failures."""

    pass


class WorkflowError(AgentError):
    """Workflow execution failures."""

    pass


class ApprovalError(AgentError):
    """Approval workflow failures."""

    pass


# ============================================================
# Session Errors
# ============================================================


class SessionError(CodegraphError):
    """Session management failures."""

    pass


class SessionNotFoundError(SessionError):
    """Session not found."""

    pass


class SessionExpiredError(SessionError):
    """Session expired."""

    pass


# ============================================================
# Helper Functions
# ============================================================


def wrap_external_error(
    error: Exception,
    message: str,
    error_type: type[InfrastructureError] | None = None,
) -> InfrastructureError:
    """
    Wrap external library errors in Codegraph exceptions.

    Args:
        error: Original exception
        message: Human-readable message
        error_type: Type of exception to raise (default: ExternalServiceError)

    Returns:
        Wrapped exception

    Example:
        try:
            result = httpx.get(url)
        except httpx.HTTPError as e:
            raise wrap_external_error(e, f"Failed to fetch {url}")
    """
    if error_type is None:
        error_type = ExternalServiceError

    exc = error_type(message, details={"original_error": str(error)})
    exc.__cause__ = error
    return exc
