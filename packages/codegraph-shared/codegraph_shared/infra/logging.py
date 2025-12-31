"""
Logging utilities - re-exports from observability.logging

This module exists for backward compatibility.
Canonical location: codegraph_shared.infra.observability.logging
"""

from codegraph_shared.infra.observability.logging import (
    get_logger,
    setup_logging,
)

__all__ = ["get_logger", "setup_logging"]
