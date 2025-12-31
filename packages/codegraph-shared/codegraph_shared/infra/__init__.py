"""Infrastructure layer adapters."""

# Re-export logging for backward compatibility
from codegraph_shared.infra.observability.logging import (
    get_logger,
    setup_logging,
)

__all__: list[str] = [
    "get_logger",
    "setup_logging",
]
