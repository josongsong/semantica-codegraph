"""
Structured Logging with structlog

Provides structured, contextual logging for production observability.
"""

import contextvars
import logging
import sys
import time
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars

# Thread-local context storage
_context_var: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_context")


def setup_logging(
    level: str = "INFO",
    format: str = "json",  # "json" or "console"
    include_timestamp: bool = True,
    include_caller: bool = True,
) -> None:
    """
    Setup structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format ("json" for production, "console" for development)
        include_timestamp: Include timestamp in logs
        include_caller: Include caller information (file, line, function)
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging to play nice with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Processors that work for all output formats
    shared_processors = [
        # Add context from contextvars
        merge_contextvars,
        # Add log level
        structlog.stdlib.add_log_level,
        # Add logger name
        structlog.stdlib.add_logger_name,
    ]

    if include_timestamp:
        # Add ISO timestamp
        shared_processors.append(structlog.processors.TimeStamper(fmt="iso"))

    if include_caller:
        # Add caller information
        shared_processors.append(structlog.processors.CallsiteParameterAdder())

    # Exception formatting
    shared_processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
    )

    # Output format processors
    if format == "json":
        # JSON output for production (machine-readable)
        output_processors = [
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console output for development (human-readable)
        output_processors = [
            structlog.dev.ConsoleRenderer(
                colors=sys.stdout.isatty(),  # Only use colors if output is a TTY
                exception_formatter=structlog.dev.RichTracebackFormatter(),
            )
        ]

    # Configure structlog
    structlog.configure(
        processors=shared_processors + output_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__ from calling module)

    Returns:
        Structured logger instance

    Example:
        ```python
        logger = get_logger(__name__)
        logger.info("user_logged_in", user_id=123, ip="192.168.1.1")
        ```
    """
    return structlog.get_logger(name)


def add_context(**kwargs: Any) -> None:
    """
    Add contextual data to all subsequent log messages in current context.

    This uses contextvars so it's safe for async and multi-threaded code.

    Args:
        **kwargs: Key-value pairs to add to logging context

    Example:
        ```python
        add_context(request_id="abc-123", user_id=456)
        logger.info("processing request")  # Will include request_id and user_id
        ```
    """
    current = _context_var.get()
    updated = {**current, **kwargs}
    _context_var.set(updated)
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context(*keys: str) -> None:
    """
    Clear specific keys from logging context.

    If no keys provided, clears all context.

    Args:
        *keys: Keys to remove from context

    Example:
        ```python
        add_context(a=1, b=2, c=3)
        clear_context("a", "b")  # Only 'c' remains
        clear_context()  # All cleared
        ```
    """
    if not keys:
        # Clear all
        _context_var.set({})
        structlog.contextvars.clear_contextvars()
    else:
        # Clear specific keys
        current = _context_var.get()
        for key in keys:
            current.pop(key, None)
        _context_var.set(current)
        structlog.contextvars.unbind_contextvars(*keys)


def log_error(
    logger: structlog.stdlib.BoundLogger,
    message: str,
    error: Exception | None = None,
    **extra: Any,
) -> None:
    """
    Log an error with consistent structure.

    Args:
        logger: Logger instance
        message: Error message
        error: Exception object (will extract type, message, traceback)
        **extra: Additional context

    Example:
        ```python
        try:
            risky_operation()
        except ValueError as e:
            log_error(logger, "operation failed", error=e, operation="risky_operation")
        ```
    """
    error_data = extra.copy()

    if error:
        error_data.update(
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
            }
        )
        # Note: structlog's format_exc_info processor will handle exception formatting
        # when an exception is active in the current context

    logger.error(message, **error_data)


def log_performance(
    logger: structlog.stdlib.BoundLogger,
    operation: str,
    duration_ms: float,
    **extra: Any,
) -> None:
    """
    Log performance metrics in consistent format.

    Args:
        logger: Logger instance
        operation: Operation name
        duration_ms: Duration in milliseconds
        **extra: Additional context (e.g., items_processed, cache_hit)

    Example:
        ```python
        start = time.time()
        process_batch()
        duration_ms = (time.time() - start) * 1000
        log_performance(logger, "batch_processing", duration_ms, items=100)
        ```
    """
    perf_data = {
        "operation": operation,
        "duration_ms": round(duration_ms, 2),
        "performance": True,  # Tag for filtering
        **extra,
    }

    # Categorize as slow if over threshold
    if duration_ms > 1000:  # 1 second
        perf_data["slow"] = True
        logger.warning("slow_operation", **perf_data)
    else:
        logger.info("operation_complete", **perf_data)


# Context manager for performance logging
class LogPerformance:
    """
    Context manager for automatic performance logging.

    Example:
        ```python
        logger = get_logger(__name__)
        with LogPerformance(logger, "database_query", query_id=123):
            execute_query()
        # Logs: operation_complete, duration_ms=..., query_id=123
        ```
    """

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        operation: str,
        **extra: Any,
    ):
        self.logger = logger
        self.operation = operation
        self.extra = extra
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, _exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000

        if exc_type is not None:
            # Operation failed
            log_error(
                self.logger,
                f"{self.operation}_failed",
                error=exc_val,
                duration_ms=round(duration_ms, 2),
                **self.extra,
            )
        else:
            # Operation succeeded
            log_performance(self.logger, self.operation, duration_ms, **self.extra)

        # Don't suppress exceptions
        return False


# Example usage and documentation
def _example_usage():
    """Example demonstrating structured logging usage."""
    # Setup logging (call once at app startup)
    setup_logging(level="INFO", format="json")

    # Get logger
    logger = get_logger(__name__)

    # Simple log
    logger.info("application started", version="1.0.0")

    # Add persistent context
    add_context(request_id="req-123", user_id=456)

    # All subsequent logs will include request_id and user_id
    logger.info("processing request", path="/api/users")
    logger.debug("cache lookup", key="user:456", cache_hit=True)

    # Log with additional fields
    logger.info(
        "query_executed",
        query_type="select",
        rows_returned=42,
        duration_ms=15.3,
    )

    # Error logging
    try:
        raise ValueError("Invalid input")
    except ValueError as e:
        log_error(logger, "validation failed", error=e, input_value="bad")

    # Performance logging
    start = time.time()
    # ... do work ...
    duration_ms = (time.time() - start) * 1000
    log_performance(logger, "data_processing", duration_ms, items_processed=100)

    # Or use context manager
    with LogPerformance(logger, "database_query", table="users"):
        # ... execute query ...
        pass

    # Clear context when request is done
    clear_context()


if __name__ == "__main__":
    _example_usage()
