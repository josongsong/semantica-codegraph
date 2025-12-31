"""
Factory Helper Functions

Provides utilities for safe factory function execution.
"""

from collections.abc import Callable
from typing import TypeVar

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class FactoryError(Exception):
    """Exception raised when factory function fails."""

    pass


def safe_factory_call(
    factory: Callable[[], T],
    factory_name: str = "factory",
    default: T | None = None,
    reraise: bool = False,
) -> T | None:
    """
    Safely call a factory function with error handling.

    Args:
        factory: Factory function to call
        factory_name: Name for logging purposes
        default: Default value to return on error (None if not provided)
        reraise: Whether to re-raise exceptions after logging

    Returns:
        Result from factory or default value on error

    Raises:
        FactoryError: If reraise=True and factory fails
    """
    if factory is None:
        logger.warning(f"{factory_name} is None")
        return default

    if not callable(factory):
        error_msg = f"{factory_name} is not callable: {type(factory)}"
        logger.error(error_msg)
        if reraise:
            raise FactoryError(error_msg)
        return default

    try:
        result = factory()
        if result is None:
            logger.warning(f"{factory_name} returned None")
        return result
    except Exception as e:
        logger.error(f"{factory_name} failed: {type(e).__name__}: {e}", exc_info=True)
        if reraise:
            raise FactoryError(f"{factory_name} failed: {e}") from e
        return default


def validate_factory(factory: Callable[[], T] | None, name: str, required: bool = True) -> None:
    """
    Validate factory function.

    Args:
        factory: Factory function to validate
        name: Factory name for error messages
        required: Whether factory is required (raises if None)

    Raises:
        ValueError: If validation fails
    """
    if factory is None:
        if required:
            raise ValueError(f"{name} is required but was None")
        return

    if not callable(factory):
        raise TypeError(f"{name} must be callable, got {type(factory)}")


def lazy_factory_cache(factory: Callable[[], T]) -> Callable[[], T]:
    """
    Create a cached wrapper for factory function.

    The factory will only be called once, and the result is cached.

    Args:
        factory: Factory function to wrap

    Returns:
        Cached factory function
    """
    cache: dict[str, T] = {}

    def cached_factory() -> T:
        if "value" not in cache:
            cache["value"] = factory()
        return cache["value"]

    return cached_factory
