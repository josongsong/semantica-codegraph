"""
Structured Logging for TRCR

Provides consistent, structured logging across the codebase.
Compatible with JSON logging for production environments.
"""

import logging
import sys
from typing import Any

# ==============================================================================
# Logger Configuration
# ==============================================================================


def setup_logger(
    name: str = "trcr",
    level: int = logging.INFO,
    structured: bool = False,
) -> logging.Logger:
    """Setup logger with optional structured logging.

    Args:
        name: Logger name
        level: Logging level
        structured: Use JSON structured logging

    Returns:
        Configured logger

    Example:
        logger = setup_logger("trcr.compiler", level=logging.DEBUG)
        logger.info("Rule compiled", extra={"rule_id": "my.rule", "tier": "tier1"})
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers = []

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Set formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        import json

        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)  # type: ignore[arg-type]

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


# ==============================================================================
# Context Manager for Logging
# ==============================================================================


class LogContext:
    """Context manager for adding context to logs.

    Example:
        with LogContext(logger, rule_id="my.rule", tier="tier1"):
            logger.info("Compiling rule")
            # Logs: {"message": "Compiling rule", "rule_id": "my.rule", "tier": "tier1"}
    """

    def __init__(self, logger: logging.Logger, **context: Any) -> None:
        self.logger = logger
        self.context = context
        self.old_factory = logging.getLogRecordFactory()

    def __enter__(self) -> None:
        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = self.old_factory(*args, **kwargs)
            record.extra = self.context  # type: ignore[attr-defined]
            return record

        logging.setLogRecordFactory(record_factory)

    def __exit__(self, *args: Any) -> None:
        logging.setLogRecordFactory(self.old_factory)


# ==============================================================================
# Helper Functions
# ==============================================================================


def log_duration(logger: logging.Logger, message: str, **context: Any) -> Any:
    """Decorator to log function duration.

    Example:
        @log_duration(logger, "Rule compilation")
        def compile_rule(rule_id):
            ...
    """
    import time
    from collections.abc import Callable
    from functools import wraps
    from typing import TypeVar

    T = TypeVar("T")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    f"{message} completed",
                    extra={"duration_ms": duration_ms, **context},
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.error(
                    f"{message} failed",
                    extra={"duration_ms": duration_ms, "error": str(e), **context},
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


# ==============================================================================
# Default Logger
# ==============================================================================


# Create default logger
default_logger = setup_logger()


def get_logger(name: str | None = None) -> logging.Logger:
    """Get logger instance.

    Args:
        name: Logger name (defaults to "trcr")

    Returns:
        Logger instance
    """
    if name is None:
        return default_logger
    return logging.getLogger(f"trcr.{name}")


# ==============================================================================
# Exports
# ==============================================================================

__all__ = [
    "setup_logger",
    "get_logger",
    "LogContext",
    "log_duration",
    "StructuredFormatter",
]
