"""
Common utilities shared across all layers.

This module provides cross-cutting concerns that can be used by any layer
without creating circular dependencies.
"""

from src.common.observability import (
    get_logger,
    record_counter,
    record_gauge,
    record_histogram,
)

__all__ = [
    "get_logger",
    "record_counter",
    "record_gauge",
    "record_histogram",
]
