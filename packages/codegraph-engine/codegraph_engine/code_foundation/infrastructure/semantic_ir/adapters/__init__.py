"""
Semantic IR Adapters (Hexagonal Architecture)

Infrastructure implementations of domain ports.
"""

from .body_hash_adapter import SHA256BodyHashAdapter
from .config_adapter import (
    EnvConfigProvider,
    StructlogBatchLogger,
    create_default_batch_logger,
    create_default_config,
)
from .metrics_adapter import (
    NoOpMetricsAdapter,
    ObservabilityMetricsAdapter,
    create_default_metrics_adapter,
)

__all__ = [
    # Body Hash
    "SHA256BodyHashAdapter",
    # Config
    "EnvConfigProvider",
    "StructlogBatchLogger",
    "create_default_config",
    "create_default_batch_logger",
    # Metrics
    "ObservabilityMetricsAdapter",
    "NoOpMetricsAdapter",
    "create_default_metrics_adapter",
]
