"""
Common observability utilities.

This module re-exports observability functions from infra layer
to break circular dependencies. All layers can safely import from here.

Design: Cross-cutting concerns (logging, metrics, tracing) are allowed
to be imported by all layers including foundation/domain layer.
"""

# Re-export from infra.observability
from src.infra.observability import (
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
