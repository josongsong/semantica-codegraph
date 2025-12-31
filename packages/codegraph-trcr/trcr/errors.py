"""
Standardized Error Handling for TRCR

Provides hierarchical exception classes with error codes and context.
"""

from typing import Any


class TRCRError(Exception):
    """Base exception for all TRCR errors.

    Includes error code for programmatic handling and context for debugging.

    Example:
        raise TRCRError(
            code="COMPILATION_FAILED",
            message="Failed to compile rule",
            rule_id="my.rule",
            original_error=e,
        )
    """

    def __init__(self, code: str, message: str, **context: Any) -> None:
        self.code = code
        self.message = message
        self.context = context
        super().__init__(f"[{code}] {message}")

    def __repr__(self) -> str:
        ctx_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, {ctx_str})"


# ==============================================================================
# Compilation Errors
# ==============================================================================


class CompilationError(TRCRError):
    """Error during rule compilation."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(code="COMPILATION_ERROR", message=message, **context)


class IRBuildError(CompilationError):
    """Error during IR building."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "IR_BUILD_ERROR"


class OptimizationError(CompilationError):
    """Error during optimization."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "OPTIMIZATION_ERROR"


# ==============================================================================
# Runtime Errors
# ==============================================================================


class RuntimeError(TRCRError):  # type: ignore[misc]
    """Error during rule execution."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(code="RUNTIME_ERROR", message=message, **context)


class IndexError(RuntimeError):  # type: ignore[misc]
    """Error in index operations."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "INDEX_ERROR"


class MatchError(RuntimeError):
    """Error during pattern matching."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "MATCH_ERROR"


# ==============================================================================
# Validation Errors
# ==============================================================================


class ValidationError(TRCRError):
    """Error in data validation."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(code="VALIDATION_ERROR", message=message, **context)


class YAMLValidationError(ValidationError):
    """Error validating YAML structure."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "YAML_VALIDATION_ERROR"


class SchemaError(ValidationError):
    """Error in schema validation."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "SCHEMA_ERROR"


# ==============================================================================
# Configuration Errors
# ==============================================================================


class ConfigurationError(TRCRError):
    """Error in configuration."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(code="CONFIGURATION_ERROR", message=message, **context)


# ==============================================================================
# Resource Errors
# ==============================================================================


class ResourceError(TRCRError):
    """Error accessing resources."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(code="RESOURCE_ERROR", message=message, **context)


class FileNotFoundError(ResourceError):  # type: ignore[misc]
    """File not found."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "FILE_NOT_FOUND"


class CacheError(ResourceError):
    """Error in cache operations."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message, **context)
        self.code = "CACHE_ERROR"


# ==============================================================================
# Exports
# ==============================================================================

__all__ = [
    # Base
    "TRCRError",
    # Compilation
    "CompilationError",
    "IRBuildError",
    "OptimizationError",
    # Runtime
    "RuntimeError",
    "IndexError",
    "MatchError",
    # Validation
    "ValidationError",
    "YAMLValidationError",
    "SchemaError",
    # Configuration
    "ConfigurationError",
    # Resource
    "ResourceError",
    "FileNotFoundError",
    "CacheError",
]
