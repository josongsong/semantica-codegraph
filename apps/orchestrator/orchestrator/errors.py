"""
Agent Error Hierarchy

SOTA-level error classification for precise error handling.
"""


class AgentError(Exception):
    """Base agent error with HTTP status code mapping"""

    http_status_code: int = 500  # Default: Internal Server Error

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.details: dict = details or {}


class ValidationError(AgentError):
    """Config/data validation error

    HTTP Status: 422 Unprocessable Entity

    Example:
        >>> raise ValidationError("Invalid max_iterations: -1", {"field": "max_iterations"})
    """

    http_status_code = 422


class InitializationError(AgentError):
    """Component initialization failed

    HTTP Status: 503 Service Unavailable

    Example:
        >>> raise InitializationError("LLM provider unavailable", {"provider": "openai"})
    """

    http_status_code = 503


class ExecutionError(AgentError):
    """Task execution failed

    HTTP Status: 500 Internal Server Error

    Example:
        >>> raise ExecutionError("Code generation timeout", {"task_id": "123"})
    """

    http_status_code = 500


class ReflectionError(AgentError):
    """Self-reflection process failed

    HTTP Status: 500 Internal Server Error

    Example:
        >>> raise ReflectionError("Invalid reflection verdict", {"verdict": "unknown"})
    """

    http_status_code = 500


class FallbackError(AgentError):
    """All fallback attempts failed

    HTTP Status: 503 Service Unavailable

    Example:
        >>> raise FallbackError("V8 and V7 both failed", {"attempts": 2})
    """

    http_status_code = 503


class ConfigurationError(AgentError):
    """Invalid configuration

    HTTP Status: 400 Bad Request

    Example:
        >>> raise ConfigurationError("Missing required config", {"missing": ["api_key"]})
    """

    http_status_code = 400


class TimeoutError(AgentError):
    """Operation timeout

    HTTP Status: 504 Gateway Timeout

    Example:
        >>> raise TimeoutError("Task exceeded timeout", {"timeout_seconds": 300})
    """

    http_status_code = 504


__all__ = [
    "AgentError",
    "ValidationError",
    "InitializationError",
    "ExecutionError",
    "ReflectionError",
    "FallbackError",
    "ConfigurationError",
    "TimeoutError",
]
